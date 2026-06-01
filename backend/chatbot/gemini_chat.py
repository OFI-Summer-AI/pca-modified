"""Compliance co-pilot — all responses go through Ollama (local AI).

Flow:
  1. Structured intents (delay, source, ranking, etc.) → pandas computes facts first
  2. AI receives those facts as context → writes a natural-language response
  3. Open-ended / greeting → AI responds directly with dataset summary as context

This means every user message gets an AI response. Pandas is just a data-gathering
layer so the AI has accurate numbers to talk about.
"""

import json
import logging
import threading

from pipeline.ai_client import call_ai, stream_ai

logger = logging.getLogger(__name__)


# ── Dataset context builder ────────────────────────────────────────────────────

def _dataset_context(session_data: dict) -> dict:
    """Compact dataset snapshot — fits in ~400 tokens for qwen2.5:1.5b."""
    orders   = session_data.get("orders", [])
    domain   = session_data.get("domain", "logistics")
    summary  = session_data.get("summary", {})

    total    = len(orders)
    blocked  = sum(1 for o in orders if o.get("Process_Status") == "BLOCKED")
    alert    = sum(1 for o in orders if o.get("Process_Status") == "ALERT")
    passed   = total - blocked - alert

    dev_counts: dict = {}
    for o in orders:
        for d in (o.get("Deviations") or []):
            label = d.get("rule_id") or d.get("type") or "?"
            dev_counts[label] = dev_counts.get(label, 0) + 1
    top_devs = sorted(dev_counts.items(), key=lambda x: -x[1])[:5]

    top_orders = sorted(orders, key=lambda x: x.get("Deviation_Score", 0), reverse=True)[:5]
    top_simplified = [
        {
            "id": o.get("Order_Number"),
            "status": o.get("Process_Status"),
            "score": o.get("Deviation_Score"),
            "issues": [d.get("rule_id") or d.get("type") for d in (o.get("Deviations") or [])][:3],
        }
        for o in top_orders
    ]

    return {
        "domain": domain,
        "total_orders": total,
        "blocked": blocked,
        "alert": alert,
        "pass": passed,
        "adherence_pct": round(passed / total * 100, 1) if total else 0,
        "top_deviation_types": [{"type": k, "count": v} for k, v in top_devs],
        "top_risk_orders": top_simplified,
        "avg_deviation_score": round(summary.get("avgDeviationScore", 0), 1),
    }


# ── Prompt builders ────────────────────────────────────────────────────────────

def _prompt_with_data(question: str, pandas_result: dict, session_data: dict) -> str:
    """Used when pandas already computed structured data — AI narrates it."""
    ctx    = _dataset_context(session_data)
    answer = pandas_result.get("answer", "")
    table  = pandas_result.get("data", {}).get("table") if pandas_result.get("data") else None

    rows_block = ""
    if table:
        rows_block = "\n\nData:\n" + json.dumps(table[:10], indent=2)

    return f"""You are a compliance co-pilot for a {ctx['domain']} operations dashboard.

The user asked: "{question}"

Pre-computed answer:
{answer}{rows_block}

Instructions:
- Write 1-3 concise, professional sentences summarising the result above.
- Lead with the #1 finding (e.g. "UA01 has the most delays at 28,195 orders").
- Use ONLY the numbers shown above — do not introduce any other statistics.
- Do not open with "The dataset reveals", "Based on the data", or similar filler.
- Do not mention overall BLOCKED/ALERT/PASS totals unless they appear in the data above."""


def _prompt_order(question: str, order: dict, session_data: dict) -> str:
    """Used for specific order lookups — AI writes a narrative about the order."""
    ctx        = _dataset_context(session_data)
    deviations = order.get("Deviations") or []
    meta       = order.get("metadata") or {}
    flow       = order.get("Actual_Flow") or []

    order_facts = {
        "order_id":     order.get("Order_Number"),
        "status":       order.get("Process_Status"),
        "risk":         order.get("Risk_Level"),
        "score":        order.get("Deviation_Score"),
        "movement":     flow[0] if flow else None,
        "actual_date":  meta.get("WADAT_IST") or meta.get("actual_date"),
        "sched_date":   meta.get("EINDT") or meta.get("scheduled_date"),
        "source_used":  meta.get("CHANGED_FROM"),
        "optimal_src":  meta.get("OPTIMAL_SOURCE_LOCATION"),
        "deviations":   [{"type": d.get("rule_id") or d.get("type"), "severity": d.get("severity")} for d in deviations],
        "root_cause":   order.get("root_cause"),
    }

    return f"""You are a compliance analyst co-pilot for a {ctx['domain']} operations dashboard.

Overall dataset: {ctx['total_orders']:,} orders, {ctx['adherence_pct']}% compliance rate.

Order details:
{json.dumps(order_facts, indent=2)}

User asked: "{question}"

Write a clear, professional 3-5 sentence summary of this order's compliance status.
Cover: what happened (the movement), what went wrong, severity, and what should be done.
Be specific — use the actual location codes and dates from the data above."""


def _prompt_open(question: str, session_data: dict) -> str:
    """Used for open-ended conversational questions."""
    ctx = _dataset_context(session_data)

    return f"""You are a professional compliance co-pilot for a {ctx['domain']} operations dashboard.

Dataset snapshot:
{json.dumps(ctx, indent=2)}

User: "{question}"

Respond professionally in 2-5 sentences. Use numbers from the snapshot where relevant.
If the question is conversational (greeting, thanks, etc.), respond warmly and briefly mention what you can help with.
Do not invent data not shown above."""


# ── Public API ─────────────────────────────────────────────────────────────────

# ── Streaming helpers ─────────────────────────────────────────────────────────

def _make_stream(prompt: str, loop, queue):
    """Run stream_ai in a background thread, put chunks into asyncio queue."""
    try:
        for chunk in stream_ai(prompt, num_predict=256):
            loop.call_soon_threadsafe(queue.put_nowait, chunk)
    finally:
        loop.call_soon_threadsafe(queue.put_nowait, None)   # sentinel = done


# ── Public streaming API ───────────────────────────────────────────────────────

def get_stream_for_data(question: str, pandas_result: dict, session_data: dict):
    """Return (prompt, table_data) for a structured-query stream."""
    return _prompt_with_data(question, pandas_result, session_data), pandas_result.get("data")


def get_stream_for_order(question: str, order: dict, session_data: dict):
    """Return (prompt, None) for an order-lookup stream."""
    return _prompt_order(question, order, session_data), None


def get_stream_for_open(question: str, session_data: dict):
    """Return (prompt, None) for an open/greeting stream."""
    return _prompt_open(question, session_data), None


def build_stream_generator(prompt: str, table_data, loop):
    """Async generator that streams SSE events for a given prompt.

    Yields byte strings in SSE format:
      data: {"type": "data",  "payload": <table>}   (once, if table present)
      data: {"type": "chunk", "text": "<tok>"}       (many)
      data: {"type": "done",  "source": "ai"}        (once)
    """
    import asyncio

    async def _gen():
        if table_data:
            yield _sse({"type": "data", "payload": table_data})

        queue: asyncio.Queue = asyncio.Queue()
        t = threading.Thread(target=_make_stream, args=(prompt, loop, queue), daemon=True)
        t.start()

        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield _sse({"type": "chunk", "text": chunk})

        yield _sse({"type": "done", "source": "ai"})

    return _gen()


def _sse(obj: dict) -> bytes:
    return (f"data: {json.dumps(obj)}\n\n").encode()


# ── Non-streaming fallbacks (used for pipeline / contextual RCA) ───────────────

def ask_with_data(question: str, pandas_result: dict, session_data: dict) -> dict:
    """Blocking AI narration — used as fallback only."""
    prompt = _prompt_with_data(question, pandas_result, session_data)
    try:
        answer = call_ai(prompt, expect_json=False, num_predict=256)
        return {"answer": str(answer).strip(), "data": pandas_result.get("data"), "source": "ai"}
    except Exception as e:
        logger.warning("Chat AI (with data) failed: %s", e)
        return {"answer": pandas_result.get("answer", ""), "data": pandas_result.get("data"), "source": "structured"}


def ask_about_order(question: str, order: dict, session_data: dict) -> dict:
    prompt = _prompt_order(question, order, session_data)
    try:
        answer = call_ai(prompt, expect_json=False, num_predict=256)
        return {"answer": str(answer).strip(), "data": None, "source": "ai"}
    except Exception as e:
        logger.warning("Chat AI (order) failed: %s", e)
        return {"answer": None, "data": None, "source": "error"}


def ask_open(question: str, session_data: dict) -> dict:
    prompt = _prompt_open(question, session_data)
    try:
        answer = call_ai(prompt, expect_json=False, num_predict=256)
        return {"answer": str(answer).strip(), "data": None, "source": "ai"}
    except Exception as e:
        logger.warning("Chat AI (open) failed: %s", e)
        return {"answer": "I couldn't process that right now — please try again.", "data": None, "source": "error"}

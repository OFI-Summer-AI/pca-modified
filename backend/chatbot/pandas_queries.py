"""Structured pandas queries on analyzed orders. No AI calls."""
import random
import re

import pandas as pd

from .intent_classifier import extract_order_id


def _risk_index(raw_score: int, status: str, risk: str) -> int:
    """
    Convert raw deviation score → business risk index (0–100).
    Raw scores use CRITICAL=40, HIGH=25, MEDIUM=10, LOW=5 weights.
    Business users expect: BLOCKED = very high, LOW = low.
    """
    s, r = (status or "").upper(), (risk or "").upper()
    if s == "BLOCKED" and r == "CRITICAL":
        return min(90 + (raw_score - 40) // 5, 100)
    if s == "BLOCKED":
        return min(75 + max(raw_score - 40, 0) // 4, 89)
    if s == "ALERT":
        return min(45 + max(raw_score - 20, 0) // 2, 74)
    return max(min(raw_score * 2, 39), 5)


def _risk_label(status: str, risk: str) -> str:
    s, r = (status or "").upper(), (risk or "").upper()
    if s == "BLOCKED" and r == "CRITICAL":
        return "CRITICAL — Immediate action required"
    if s == "BLOCKED":
        return "HIGH RISK — Blocked from process"
    if s == "ALERT":
        return "MEDIUM RISK — Under review"
    return "LOW RISK — Compliant"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_df(orders: list) -> pd.DataFrame:
    return pd.DataFrame(orders)


def _clean(v) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in ("none", "nan", "null", "") else s


# ── Greeting ───────────────────────────────────────────────────────────────────

_GREETINGS = [
    "Hello! I'm your compliance co-pilot. Ask me about specific orders, deviation patterns, "
    "delay trends, source routing issues, or overall compliance status.",
    "Hi there! I can help you explore the logistics data. Try asking: "
    "\"Show me the top risk orders\", \"Which locations had the most delays?\", "
    "or \"Tell me about order [number]\".",
    "Hey! Ready to help. I can look up specific orders, summarise compliance status, "
    "analyse delay patterns, or break down deviation types — just ask.",
]

_THANKS = [
    "You're welcome! Let me know if you have more questions about the data.",
    "Happy to help. Anything else you'd like to explore?",
    "Sure thing! Ask me anything about the compliance data.",
]


def greeting_response(question: str) -> dict:
    q = question.lower()
    if any(w in q for w in ("thank", "thanks", "cheers")):
        return {"answer": random.choice(_THANKS), "data": None}
    if any(w in q for w in ("what can you do", "help", "who are you", "what are you")):
        return {
            "answer": (
                "I'm the Compliance Assistant — your co-pilot for this logistics dataset.\n\n"
                "I can:\n"
                "- **Look up any order** by number (e.g. \"show order 22376390\")\n"
                "- **Summarise compliance** — overall status, blocked/alert/pass counts\n"
                "- **Analyse delays** — which locations have the most late deliveries\n"
                "- **Source routing issues** — orders using wrong source locations\n"
                "- **Deviation breakdown** — most common compliance violations\n"
                "- **Rank risk orders** — top 10 highest-risk orders\n\n"
                "Just ask in plain English."
            ),
            "data": None,
        }
    return {"answer": random.choice(_GREETINGS), "data": None}


# ── Order lookup ───────────────────────────────────────────────────────────────

def order_lookup(orders: list, question: str) -> dict:
    order_id = extract_order_id(question)
    if not order_id:
        return {"answer": "I couldn't find an order number in your question. Try: \"show order 22376390\".", "data": None}

    order = next((o for o in orders if str(o.get("Order_Number", "")) == order_id), None)
    if not order:
        return {"answer": f"Order **{order_id}** was not found in the current session.", "data": None}

    status    = order.get("Process_Status", "—")
    risk      = order.get("Risk_Level", "—")
    score     = order.get("Deviation_Score", 0)
    ridx      = _risk_index(score, status, risk)
    rlabel    = _risk_label(status, risk)
    deviations = order.get("Deviations") or []
    actual_flow = order.get("Actual_Flow") or []
    meta      = order.get("metadata") or {}

    actual_date   = _clean(meta.get("WADAT_IST")) or _clean(meta.get("actual_date")) or "—"
    sched_date    = _clean(meta.get("EINDT")) or _clean(meta.get("scheduled_date")) or "—"
    actual_src    = _clean(meta.get("CHANGED_FROM")) or "—"
    optimal_src   = _clean(meta.get("OPTIMAL_SOURCE_LOCATION")) or "—"

    # Build answer text
    lines = [f"**Order {order_id}** — {rlabel} · Risk Index: {ridx}/100"]

    if actual_date != "—":
        lines.append(f"- Actual date: {actual_date}" + (f" | Scheduled: {sched_date}" if sched_date != "—" else ""))
    if actual_src != "—":
        lines.append(f"- Source used: {actual_src}" + (f" | Required: {optimal_src}" if optimal_src not in ("—", actual_src) else ""))
    if actual_flow:
        lines.append(f"- Movement: {actual_flow[0]}")

    if deviations:
        dev_labels = [d.get("rule_id") or d.get("type", "?") for d in deviations]
        lines.append(f"- Deviations ({len(deviations)}): {', '.join(dev_labels)}")
        # Primary RCA
        rc = order.get("root_cause")
        if rc:
            lines.append(f"- Root cause: {rc}")
    else:
        lines.append("- No deviations — fully compliant.")

    return {"answer": "\n".join(lines), "data": None}


# ── Delay analysis ─────────────────────────────────────────────────────────────

def delay_analysis(orders: list, question: str) -> dict:
    df = _to_df(orders)
    delayed = df[df["Deviations"].apply(
        lambda ds: any(d.get("type") in ("DELAYED", "DELAY_FLAG") for d in (ds or []))
    )]

    if delayed.empty:
        return {"answer": "No delayed orders found in the analysed data.", "data": None}

    total = len(df)
    count = len(delayed)
    pct   = count / total * 100

    # Group by source location if available
    meta_col = None
    for col in ("CHANGED_FROM", "WERKS", "ALL_PRODUCTION_PLANT"):
        extracted = delayed["metadata"].apply(lambda m: (m or {}).get(col))
        if extracted.notna().sum() > 10:
            meta_col = col
            delayed = delayed.copy()
            delayed[col] = extracted
            break

    if meta_col:
        grouped = (
            delayed.groupby(meta_col).size()
            .reset_index(name="delayed_orders")
            .sort_values("delayed_orders", ascending=False)
            .head(10)
        )
        table = grouped.to_dict("records")
        answer = (
            f"**{count} orders** ({pct:.1f}%) have delivery delays out of {total} total.\n"
            f"Top locations by delay count (grouped by {meta_col}):"
        )
        return {"answer": answer, "data": {"table": table, "chart_type": "bar", "x": meta_col, "y": "delayed_orders"}}

    return {
        "answer": f"**{count} orders** ({pct:.1f}%) have delivery delays out of {total} total.",
        "data": None,
    }


# ── Source analysis ────────────────────────────────────────────────────────────

def source_analysis(orders: list, question: str) -> dict:
    df = _to_df(orders)
    violated = df[df["Deviations"].apply(
        lambda ds: any(
            d.get("rule_id") == "WRONG_SOURCE" or d.get("type") == "DOMAIN_RULE_VIOLATION"
            for d in (ds or [])
        )
    )]

    if violated.empty:
        return {"answer": "No wrong-source violations found in the analysed data.", "data": None}

    total = len(df)
    count = len(violated)
    pct   = count / total * 100

    rows = []
    for _, row in violated.head(15).iterrows():
        meta = row.get("metadata") or {}
        actual = _clean(meta.get("CHANGED_FROM")) or "N/A"
        optimal = _clean(meta.get("OPTIMAL_SOURCE_LOCATION")) or "N/A"
        rows.append({
            "Order": row.get("Order_Number"),
            "Used": actual,
            "Required": optimal,
            "Status": row.get("Process_Status"),
            "Score": row.get("Deviation_Score", 0),
        })

    answer = (
        f"**{count} orders** ({pct:.1f}%) used a non-optimal source location.\n"
        f"Showing top 15 by deviation score:"
    )
    return {"answer": answer, "data": {"table": rows, "chart_type": "table"}}


# ── Plant / location analysis ──────────────────────────────────────────────────

def plant_analysis(orders: list, question: str) -> dict:
    df = _to_df(orders)
    q  = question.lower()

    meta_col = "CHANGED_FROM" if ("source" in q or "from" in q) else \
               "CHANGED_TO"   if ("destination" in q or "to" in q) else "WERKS"

    extracted = df["metadata"].apply(lambda m: (m or {}).get(meta_col))
    if extracted.notna().sum() < 5:
        # Try fallback columns
        for col in ("CHANGED_FROM", "WERKS", "CHANGED_TO"):
            extracted = df["metadata"].apply(lambda m: (m or {}).get(col))
            if extracted.notna().sum() > 5:
                meta_col = col
                break

    df = df.copy()
    df[meta_col] = extracted

    grouped = (
        df.groupby(meta_col)
        .agg(
            orders=("Order_Number", "count"),
            blocked=("Process_Status", lambda x: (x == "BLOCKED").sum()),
            alert=("Process_Status", lambda x: (x == "ALERT").sum()),
        )
        .reset_index()
        .sort_values("orders", ascending=False)
        .head(10)
    )

    table  = grouped.to_dict("records")
    answer = f"Order distribution by **{meta_col}** (top 10 locations):"
    return {"answer": answer, "data": {"table": table, "chart_type": "bar", "x": meta_col, "y": "orders"}}


# ── Material analysis ──────────────────────────────────────────────────────────

def material_analysis(orders: list, question: str) -> dict:
    df = _to_df(orders)

    matnr_col = None
    for col in ("MATNR", "material", "Material"):
        extracted = df["metadata"].apply(lambda m: (m or {}).get(col))
        if extracted.notna().sum() > 5:
            matnr_col = col
            df = df.copy()
            df[col] = extracted
            break

    if not matnr_col:
        return {"answer": "Material-level information is not available in this dataset.", "data": None}

    grouped = (
        df.groupby(matnr_col)
        .agg(
            orders=("Order_Number", "count"),
            blocked=("Process_Status", lambda x: (x == "BLOCKED").sum()),
            avg_score=("Deviation_Score", "mean"),
        )
        .reset_index()
        .sort_values("orders", ascending=False)
        .head(10)
    )
    grouped["avg_score"] = grouped["avg_score"].round(1)

    return {
        "answer": "Top materials by order volume:",
        "data": {"table": grouped.to_dict("records"), "chart_type": "table"},
    }


# ── Status / compliance overview ──────────────────────────────────────────────

def status_query(orders: list, question: str) -> dict:
    df    = _to_df(orders)
    total = len(df)
    if total == 0:
        return {"answer": "No orders in current session.", "data": None}

    blocked = (df["Process_Status"] == "BLOCKED").sum()
    alert   = (df["Process_Status"] == "ALERT").sum()
    passed  = (df["Process_Status"] == "PASS").sum()
    adherence = passed / total * 100

    table = [
        {"Status": "BLOCKED", "Count": int(blocked), "Share": f"{blocked/total*100:.1f}%"},
        {"Status": "ALERT",   "Count": int(alert),   "Share": f"{alert/total*100:.1f}%"},
        {"Status": "PASS",    "Count": int(passed),  "Share": f"{passed/total*100:.1f}%"},
    ]

    answer = (
        f"**{total:,} orders** analysed.\n"
        f"- PASS: {passed:,} ({adherence:.1f}% adherence)\n"
        f"- ALERT: {alert:,} ({alert/total*100:.1f}%)\n"
        f"- BLOCKED: {blocked:,} ({blocked/total*100:.1f}%)"
    )
    return {"answer": answer, "data": {"table": table, "chart_type": "pie"}}


# ── Ranking ────────────────────────────────────────────────────────────────────

def ranking_query(orders: list, question: str) -> dict:
    df = _to_df(orders)
    q  = question.lower()

    if "pass" in q or "compliant" in q:
        filtered = df[df["Process_Status"] == "PASS"].head(10)
        label = "Top compliant orders (PASS status)"
    else:
        filtered = df.sort_values("Deviation_Score", ascending=False).head(10)
        label = "Top 10 highest-risk orders"

    cols  = [c for c in ("Order_Number", "Process_Status", "Risk_Level", "Deviation_Score") if c in filtered.columns]
    rows  = filtered[cols].to_dict("records")

    # Build display table with normalized risk index instead of raw score
    table = [
        {
            "Order":      r.get("Order_Number"),
            "Status":     r.get("Process_Status"),
            "Risk":       r.get("Risk_Level"),
            "Risk Index": f"{_risk_index(r.get('Deviation_Score', 0), r.get('Process_Status', ''), r.get('Risk_Level', ''))}/100",
            "Assessment": _risk_label(r.get("Process_Status", ""), r.get("Risk_Level", "")),
        }
        for r in rows
    ]

    return {"answer": f"**{label}:**", "data": {"table": table, "chart_type": "table"}}


# ── Deviation breakdown ────────────────────────────────────────────────────────

def deviation_query(orders: list, question: str) -> dict:
    counter: dict = {}
    total_orders_with_devs = 0
    for o in orders:
        devs = o.get("Deviations") or []
        if devs:
            total_orders_with_devs += 1
        for d in devs:
            label = d.get("rule_id") or d.get("type") or "UNKNOWN"
            counter[label] = counter.get(label, 0) + 1

    if not counter:
        return {"answer": "No deviations found in the analysed data.", "data": None}

    table  = [{"Type": k, "Count": v} for k, v in sorted(counter.items(), key=lambda x: -x[1])]
    top    = table[0]
    answer = (
        f"**{sum(counter.values())} total deviations** across {total_orders_with_devs} non-compliant orders.\n"
        f"Most common: **{top['Type']}** ({top['Count']} occurrences)."
    )
    return {"answer": answer, "data": {"table": table, "chart_type": "bar", "x": "Type", "y": "Count"}}


# ── Summary ────────────────────────────────────────────────────────────────────

def summary_query(orders: list, session_data: dict) -> dict:
    df      = _to_df(orders)
    total   = len(df)
    if total == 0:
        return {"answer": "No orders in current session.", "data": None}

    blocked   = (df["Process_Status"] == "BLOCKED").sum()
    alert     = (df["Process_Status"] == "ALERT").sum()
    passed    = (df["Process_Status"] == "PASS").sum()
    adherence = passed / total * 100
    avg_score = df["Deviation_Score"].mean()

    # Most common deviation
    counter: dict = {}
    for o in orders:
        for d in (o.get("Deviations") or []):
            label = d.get("rule_id") or d.get("type") or "?"
            counter[label] = counter.get(label, 0) + 1
    top_dev = max(counter, key=counter.get) if counter else "none"
    top_dev_count = counter.get(top_dev, 0)

    domain = session_data.get("domain", "logistics")

    answer = (
        f"**Compliance Summary — {domain.title()} dataset**\n\n"
        f"- **{total:,} orders** analysed\n"
        f"- Adherence rate: **{adherence:.1f}%** ({passed:,} PASS)\n"
        f"- Non-compliant: {blocked + alert:,} orders "
        f"({blocked:,} BLOCKED, {alert:,} ALERT)\n"
        f"- Average deviation score: **{avg_score:.1f}**\n"
        f"- Most common issue: **{top_dev}** ({top_dev_count:,} occurrences)\n\n"
        f"Ask me to drill down into delays, source routing, specific orders, or risk rankings."
    )
    return {"answer": answer, "data": None}


# ── Dispatch table ─────────────────────────────────────────────────────────────

INTENT_HANDLERS = {
    "DELAY_ANALYSIS":   delay_analysis,
    "SOURCE_ANALYSIS":  source_analysis,
    "PLANT_ANALYSIS":   plant_analysis,
    "MATERIAL_ANALYSIS":material_analysis,
    "STATUS_QUERY":     status_query,
    "RANKING_QUERY":    ranking_query,
    "DEVIATION_QUERY":  deviation_query,
}


def run_query(intent: str, orders: list, question: str, session_data: dict = None) -> dict:
    if intent == "SUMMARY_REQUEST":
        return summary_query(orders, session_data or {})
    handler = INTENT_HANDLERS.get(intent)
    if handler:
        return handler(orders, question)
    return {"answer": None, "data": None}

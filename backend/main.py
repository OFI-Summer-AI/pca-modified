import asyncio
import logging
import math
import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)

DATA_DIR = Path(__file__).parent / "data"

from chatbot.gemini_chat import (ask_with_data, ask_about_order, ask_open,
                                  get_stream_for_data, get_stream_for_order,
                                  get_stream_for_open, build_stream_generator, _sse)
from chatbot.intent_classifier import classify, extract_order_id
from chatbot.pandas_queries import run_query
from pipeline.deviation_engine import run_all_orders
from pipeline.email_service import send_alerts_for_blocked
from pipeline.executive_summary import generate_summary
from pipeline.flow_builder import build_step_frequencies, get_top_sequences
from pipeline.flow_inferrer import infer_flow
from pipeline.formatter import _safe, format_final_output  # _safe used once here, not in formatter
from pipeline.parser import apply_domain_rules, build_orders_map, parse_file
from pipeline.cluster_insights import generate_cluster_insights
from pipeline.contextual_rca import generate_contextual_rca
from pipeline.rca_engine import enrich_with_rca
from pipeline.schema_detector import detect_schema
from session_store import store

app = FastAPI(title="PCA — Process Compliance Agent", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/upload-file")
async def upload_file(file: UploadFile = File(...)):
    """Temporary endpoint to upload CSV to /app/data volume. Remove after use."""
    dest = DATA_DIR / file.filename
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dest.write_bytes(content)
    return {"status": "ok", "saved_to": str(dest), "size_bytes": len(content)}


def _run_pipeline(df) -> tuple[dict, dict]:
    """Run the full analysis pipeline. Returns (output_json, session_data)."""
    import logging
    log = logging.getLogger("pipeline")

    log.info("Step 1/6: Schema detection (rows=%d)", len(df))
    schema = detect_schema(df)
    log.info("  domain=%s  order_col=%s", schema.get("domain"), schema.get("order_id_col"))

    log.info("Step 2/6: Parsing & grouping orders...")
    orders_map = build_orders_map(df, schema)
    log.info("  Orders found: %d", len(orders_map))

    if not orders_map:
        raise ValueError("No valid orders found in the uploaded file.")

    log.info("Step 3a/6: Building step frequencies...")
    step_frequencies = build_step_frequencies(orders_map)

    log.info("Step 3b/6: AI flow inference (unique steps=%d)...", len(step_frequencies))
    top_sequences = get_top_sequences(orders_map, top_n=20)
    flow_data = infer_flow(top_sequences, step_frequencies, schema.get("domain", "generic"))

    standard_flow = flow_data["standard_flow"]
    critical_steps = flow_data["critical_steps"]

    # Merge domain rules: schema auto-detected rules take priority, AI rules appended
    schema_rules = schema.get("domain_rules", [])
    ai_rules = flow_data.get("domain_rules", [])
    domain_rules = schema_rules + [r for r in ai_rules if r.get("rule_id") not in {s["rule_id"] for s in schema_rules}]

    log.info("  Standard flow: %d steps, %d domain rules (%d auto-detected, %d from AI)",
             len(standard_flow), len(domain_rules), len(schema_rules), len(ai_rules))

    # schema_rules are already applied inside build_orders_map (DuckDB path).
    # Only need apply_domain_rules for any NEW ai_rules not in schema.
    extra_ai_rules = [r for r in ai_rules if r.get("rule_id") not in {s["rule_id"] for s in schema_rules}]
    if extra_ai_rules:
        log.info("Step 2b/6: Applying %d additional AI domain rules...", len(extra_ai_rules))
        apply_domain_rules(df, orders_map, extra_ai_rules, schema["order_id_col"])

    log.info("Step 4/6: Deviation engine (%d orders)...", len(orders_map))
    analyzed = run_all_orders(orders_map, standard_flow, critical_steps, domain_rules)

    log.info("Step 5/6: Rule-based RCA...")
    analyzed = enrich_with_rca(analyzed)

    log.info("Step 6/6: Formatting output...")
    # Sanitize numpy/NaN types ONCE here — format_final_output and session both reuse this list
    safe_orders = [_safe(o) for o in analyzed]
    output = format_final_output(safe_orders, top_sequences=top_sequences)
    output["domain"] = schema.get("domain", "generic")
    log.info("Pipeline complete. BLOCKED=%d ALERT=%d PASS=%d",
             output["statusSummary"]["BLOCKED"],
             output["statusSummary"]["ALERT"],
             output["statusSummary"]["PASS"])

    session_data = {
        "schema": schema,
        "domain": schema.get("domain", "generic"),
        "standard_flow": standard_flow,
        "critical_steps": critical_steps,
        "domain_rules": domain_rules,
        "orders": safe_orders,          # already sanitized — no second _safe() pass
        "summary": output.get("summary", {}),
    }

    return output, session_data


@app.post("/analyze")
async def analyze(
    table_a: UploadFile = File(...),
    table_b: Optional[UploadFile] = File(None),
    definition_mode: str = Form("AI"),
):
    try:
        bytes_a = await table_a.read()
        df = parse_file(bytes_a, table_a.filename or "file.csv")

        if table_b is not None and table_b.filename:
            bytes_b = await table_b.read()
            df_b = parse_file(bytes_b, table_b.filename)
            from pandas import concat
            df = concat([df, df_b], ignore_index=True).drop_duplicates()

    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"File parsing error: {exc}")

    try:
        output, session_data = _run_pipeline(df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    session_id = str(uuid.uuid4())
    store.set(session_id, session_data)
    output["session_id"] = session_id

    return JSONResponse(content=output)


def _load_df_from_postgres() -> "pd.DataFrame":
    """Load logistic_activities table from PostgreSQL into a DataFrame."""
    import pandas as pd
    from sqlalchemy import create_engine
    db_url = os.getenv("DATABASE_URL", "")
    engine = create_engine(db_url)
    with engine.connect() as conn:
        df = pd.read_sql('SELECT * FROM logistic_activities', conn)
    return df


@app.get("/analyze-default")
async def analyze_default():
    db_url = os.getenv("DATABASE_URL", "")

    try:
        if db_url:
            df = _load_df_from_postgres()
        else:
            name_a = os.getenv("DEFAULT_TABLE_A", "")
            if not name_a:
                raise HTTPException(status_code=404, detail="No DATABASE_URL or DEFAULT_TABLE_A set")
            path_a = DATA_DIR / name_a
            if not path_a.exists():
                raise HTTPException(status_code=404, detail=f"File not found: backend/data/{name_a}")
            df = parse_file(path_a.read_bytes(), name_a)
            name_b = os.getenv("DEFAULT_TABLE_B", "")
            if name_b:
                path_b = DATA_DIR / name_b
                if path_b.exists():
                    import pandas as pd
                    df_b = parse_file(path_b.read_bytes(), name_b)
                    df = pd.concat([df, df_b], ignore_index=True).drop_duplicates()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Data loading error: {exc}")

    try:
        output, session_data = _run_pipeline(df)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    session_id = str(uuid.uuid4())
    store.set(session_id, session_data)
    output["session_id"] = session_id

    return JSONResponse(content=output)


@app.get("/default-files")
async def default_files():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        return {
            "table_a": {"name": "logistic_activities (PostgreSQL)", "exists": True},
            "table_b": {"name": "", "exists": False},
        }
    name_a = os.getenv("DEFAULT_TABLE_A", "")
    name_b = os.getenv("DEFAULT_TABLE_B", "")
    return {
        "table_a": {"name": name_a, "exists": bool(name_a and (DATA_DIR / name_a).exists())},
        "table_b": {"name": name_b, "exists": bool(name_b and (DATA_DIR / name_b).exists())},
    }


class SummaryPayload(BaseModel):
    session_id: str


@app.post("/summary")
async def summary_endpoint(payload: SummaryPayload):
    """Generate AI executive narrative. Called in background after /analyze."""
    session_data = store.get(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    orders = session_data.get("orders", [])
    top_orders = sorted(orders, key=lambda x: x.get("Deviation_Score", 0), reverse=True)

    narrative = generate_summary(
        session_data.get("summary", {}),
        session_data.get("domain", "process"),
        top_orders,
    )
    return {"narrative": narrative}


class ChatPayload(BaseModel):
    question: str
    session_id: str


@app.post("/chat")
async def chat_endpoint(payload: ChatPayload):
    session_data = store.get(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired. Please re-upload your data.")

    orders   = session_data.get("orders", [])
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    intent = classify(question)
    loop   = asyncio.get_event_loop()

    # ── Instant local responses — no AI, return SSE immediately ──────────────
    def _instant_sse(text: str, source: str = "local"):
        async def _gen():
            yield _sse({"type": "chunk", "text": text})
            yield _sse({"type": "done",  "source": source})
        return StreamingResponse(_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ── Order lookup ──────────────────────────────────────────────────────────
    if intent == "ORDER_LOOKUP":
        order_id = extract_order_id(question)
        order    = next((o for o in orders if str(o.get("Order_Number", "")) == order_id), None) if order_id else None
        if not order:
            msg = (f"Order **{order_id}** was not found in the current session."
                   if order_id else
                   "I couldn't find an order number in your question. Try: \"show order 22376390\".")
            return _instant_sse(msg)
        prompt, table = get_stream_for_order(question, order, session_data)
        return StreamingResponse(
            build_stream_generator(prompt, table, loop),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Structured intents — pandas first, AI streams the narration ──────────
    if intent not in ("OPEN_ENDED", "GREETING"):
        pandas_result = run_query(intent, orders, question, session_data)
        if pandas_result.get("answer"):
            prompt, table = get_stream_for_data(question, pandas_result, session_data)
            return StreamingResponse(
                build_stream_generator(prompt, table, loop),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    # ── Open-ended / greeting — AI streams directly ───────────────────────────
    prompt, table = get_stream_for_open(question, session_data)
    return StreamingResponse(
        build_stream_generator(prompt, table, loop),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _order_date(order: dict) -> str:
    """Extract a YYYY-MM-DD date string from an order's metadata."""
    meta = order.get("metadata", {})
    for key in ("WADAT_IST", "actual_date", "Date", "Eventtime", "event_time"):
        v = meta.get(key, "")
        if v:
            return str(v)[:10]
    return ""


@app.get("/orders")
async def get_orders(
    session_id: str,
    page: int = 1,
    limit: int = 100,
    status: Optional[str] = None,
    risk: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    """Paginated, filtered order list. Replaces sending all orders in /analyze."""
    session_data = store.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired. Please re-upload.")

    orders = session_data.get("orders", [])

    # Server-side filtering
    if status and status != "ALL":
        orders = [o for o in orders if o.get("Process_Status") == status]
    if risk:
        orders = [o for o in orders if o.get("Risk_Level") == risk]
    if search:
        q = search.lower()
        orders = [o for o in orders if q in str(o.get("Order_Number", "")).lower()]
    if date_from:
        orders = [o for o in orders if (d := _order_date(o)) and d >= date_from]
    if date_to:
        orders = [o for o in orders if (d := _order_date(o)) and d <= date_to]

    total = len(orders)
    limit = min(max(1, limit), 500)  # cap at 500 per page
    start = (page - 1) * limit
    page_orders = orders[start: start + limit]

    return JSONResponse(content={
        "orders": page_orders,
        "total": total,
        "page": page,
        "pages": math.ceil(total / limit) if total > 0 else 0,
        "limit": limit,
    })


@app.get("/orders/{order_id}")
async def get_order(order_id: str, session_id: str):
    """Single order detail by order number."""
    session_data = store.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired. Please re-upload.")

    orders = session_data.get("orders", [])
    order = next((o for o in orders if str(o.get("Order_Number", "")) == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found.")
    return JSONResponse(content=order)


# Keep /rca endpoint for backwards compatibility — now instant rule-based
class OrdersPayload(BaseModel):
    orders: list[dict] = []


@app.post("/rca")
async def rca_endpoint(payload: OrdersPayload):
    enriched = enrich_with_rca(payload.orders)
    return JSONResponse(content={"orders": enriched})


class ContextualRCAPayload(BaseModel):
    order_id: str
    session_id: str


@app.post("/rca/contextual")
async def contextual_rca_endpoint(payload: ContextualRCAPayload):
    """Generate AI contextual RCA for a single order using real order values.
    Result is cached in the session so re-opening the same order is instant."""
    session_data = store.get(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    # Check cache first
    cache = session_data.setdefault("contextual_rca_cache", {})
    if payload.order_id in cache:
        return JSONResponse(content=cache[payload.order_id])

    # Find the order
    orders = session_data.get("orders", [])
    order = next((o for o in orders if str(o.get("Order_Number", "")) == payload.order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {payload.order_id} not found.")

    import asyncio
    loop = asyncio.get_event_loop()
    rca = await loop.run_in_executor(None, generate_contextual_rca, order)

    # Cache so repeated opens are instant
    cache[payload.order_id] = rca
    return JSONResponse(content=rca)


class ClusterInsightsPayload(BaseModel):
    session_id: str


@app.post("/insights/clusters")
async def cluster_insights_endpoint(payload: ClusterInsightsPayload):
    """Generate AI cluster-level pattern insights for the full order set.
    Called once after /analyze completes. Result cached in session."""
    session_data = store.get(payload.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    # Return cached result if already generated
    if "cluster_insights" in session_data:
        return JSONResponse(content={"insights": session_data["cluster_insights"]})

    orders = session_data.get("orders", [])
    domain = session_data.get("domain", "logistics")

    import asyncio
    loop = asyncio.get_event_loop()
    insights = await loop.run_in_executor(None, generate_cluster_insights, orders, domain)

    session_data["cluster_insights"] = insights
    return JSONResponse(content={"insights": insights})


class AlertPayload(BaseModel):
    orders: list[dict] = []
    summary: dict = {}
    blocked_orders: list[dict] = []
    high_risk_orders: list[dict] = []


@app.post("/send-alerts")
async def send_alerts_endpoint(payload: AlertPayload):
    import asyncio
    loop = asyncio.get_event_loop()
    sent = await loop.run_in_executor(None, send_alerts_for_blocked, payload.orders)
    return {"sent": sent, "count": len(sent)}

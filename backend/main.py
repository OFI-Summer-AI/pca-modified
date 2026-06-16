import asyncio
import logging
import math
import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from datetime import date as _date
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
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
from pipeline.email_service import (
    send_alerts_for_blocked, build_group_alert, send_group_alert,
    build_context_alert, send_context_alert,
)
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
    deviation_type: Optional[str] = None,
    source_location: Optional[str] = None,
    group_key: Optional[str] = None,
    order_ids: list[str] = Query(default=[]),
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
        risk_upper = risk.upper()
        orders = [o for o in orders if (o.get("Risk_Level") or "").upper() == risk_upper]
    if deviation_type:
        def _has_dev(order, dev_type):
            for d in order.get("Deviations", []):
                if d.get("type") == dev_type:
                    return True
                if d.get("type") == "DOMAIN_RULE_VIOLATION" and d.get("rule_id") == dev_type:
                    return True
            return False
        orders = [o for o in orders if _has_dev(o, deviation_type)]
    if source_location:
        sl = source_location.strip().upper()
        orders = [
            o for o in orders
            if str(o.get("metadata", {}).get("CHANGED_FROM") or
                   o.get("metadata", {}).get("actual_source") or "").strip().upper() == sl
        ]
    if search:
        q = search.lower()
        orders = [o for o in orders if q in str(o.get("Order_Number", "")).lower()]
    if date_from:
        orders = [o for o in orders if (d := _order_date(o)) and d >= date_from]
    if date_to:
        orders = [o for o in orders if (d := _order_date(o)) and d <= date_to]
    if order_ids:
        ids_set = {str(i) for i in order_ids}
        orders = [o for o in orders if str(o.get("Order_Number", "")) in ids_set]
    elif group_key and deviation_type:
        def _has_group(order, dev_type, gkey):
            meta = order.get("metadata", {})
            for d in order.get("Deviations", []):
                d_type = d.get("type", "")
                d_rule = d.get("rule_id", "")
                effective = d_rule if (d_type == "DOMAIN_RULE_VIOLATION" and d_rule) else d_type
                if effective == dev_type:
                    computed_key, _ = _compute_group_key(effective, d, meta)
                    if computed_key == gkey:
                        return True
            return False
        orders = [o for o in orders if _has_group(o, deviation_type, group_key)]

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


# ── Compliance / Action Center endpoints ──────────────────────────────────────

def _compute_group_key(deviation_type: str, deviation: dict, meta: dict):
    """Return (key, extra_fields) for a deviation within the Action Center grouping."""
    from datetime import datetime as _dt
    _NULL = {"NONE", "NAN", "NULL", "N/A", ""}  # uppercase — _clean() always uppercases

    def _clean(v): return str(v or "").strip().upper()

    if deviation_type == "WRONG_SOURCE":
        actual = _clean(meta.get("CHANGED_FROM") or meta.get("actual_source")) or "UNKNOWN"
        optimal = _clean(meta.get("OPTIMAL_SOURCE_LOCATION") or meta.get("optimal_source"))
        if optimal in _NULL or optimal == actual:
            optimal = ""
        key = f"{actual} → {optimal}" if optimal else actual
        return key, {"actual_source": actual, "optimal_source": optimal or None}

    if deviation_type == "PLANT_MISMATCH":
        actual = _clean(meta.get("WERKS")) or "UNKNOWN"
        required = _clean(meta.get("ALL_PRODUCTION_PLANT"))
        if required in _NULL or required == actual:
            required = ""
        key = f"{actual} → {required}" if required else actual
        return key, {"actual_plant": actual, "required_plant": required or None}

    if deviation_type == "DELAYED":
        try:
            a = _dt.fromisoformat(str(meta.get("WADAT_IST") or meta.get("actual_date") or "")[:10])
            s = _dt.fromisoformat(str(meta.get("EINDT") or meta.get("scheduled_date") or "")[:10])
            days = (a - s).days
            if days <= 0:   key = "Same day or early"
            elif days <= 7: key = "1–7 days late"
            elif days <= 30: key = "8–30 days late"
            elif days <= 90: key = "31–90 days late"
            else:           key = "90+ days late"
        except Exception:
            key = "Delay detected"
        return key, {}

    if deviation_type == "MISSING_CRITICAL_STEP":
        step = deviation.get("step") or "Unknown step"
        return step, {"missing_step": step}

    if deviation_type == "OUT_OF_SEQUENCE":
        steps = deviation.get("steps") or []
        label = " → ".join(steps[:3]) + ("…" if len(steps) > 3 else "")
        return label or "Sequence violation", {"steps": steps[:3]}

    if deviation_type == "DUPLICATE_STEP":
        steps = deviation.get("steps") or []
        label = ", ".join(steps[:2]) + ("…" if len(steps) > 2 else "")
        return label or "Duplicate detected", {"steps": steps}

    if deviation_type == "DELAY_FLAG":
        return "Pre-flagged by source system", {}

    return deviation_type, {}


@app.get("/compliance/breakdown")
async def compliance_breakdown(
    session_id: str,
    deviation_types: list[str] = Query(default=[]),
):
    """
    Return grouped breakdown for selected deviation types.
    Single pass through all orders — fast even for 573K orders.
    """
    session_data = store.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    if not deviation_types:
        return JSONResponse(content={"sections": []})

    orders = session_data.get("orders", [])

    # One pass — accumulate groups for all requested deviation types
    dt_groups: dict = {dt: {} for dt in deviation_types}

    for o in orders:
        matched_types: set = set()
        for d in o.get("Deviations", []):
            d_type = d.get("type", "")
            d_rule = d.get("rule_id", "")
            effective = d_rule if (d_type == "DOMAIN_RULE_VIOLATION" and d_rule) else d_type
            if effective not in dt_groups or effective in matched_types:
                continue
            matched_types.add(effective)

            meta = o.get("metadata", {})
            key, extra = _compute_group_key(effective, d, meta)
            groups = dt_groups[effective]
            if key not in groups:
                groups[key] = {"key": key, "count": 0, "sample_order_ids": [], **extra}
            groups[key]["count"] += 1
            if len(groups[key]["sample_order_ids"]) < 100:
                groups[key]["sample_order_ids"].append(str(o.get("Order_Number", "")))

    # Build response — sorted groups with percentages
    sections = []
    for dev_type in deviation_types:
        groups_list = sorted(dt_groups[dev_type].values(), key=lambda x: x["count"], reverse=True)
        type_total = sum(g["count"] for g in groups_list)
        for g in groups_list:
            raw_pct = g["count"] / type_total * 100 if type_total else 0
            g["pct"] = round(raw_pct, 1)
            # Prevent "0%" display for real non-zero groups
            if g["count"] > 0 and g["pct"] == 0.0:
                g["pct_display"] = "< 0.1%"
            else:
                g["pct_display"] = f"{g['pct']}%"
        sections.append({
            "deviation_type": dev_type,
            "total_orders":   type_total,
            "groups":         groups_list,
        })

    return JSONResponse(content={"sections": sections})


@app.get("/compliance/intersect")
async def compliance_intersect(
    session_id: str,
    filters: list[str] = Query(default=[]),   # "DEVIATION_TYPE:group_key"
):
    """
    Return orders matching ALL supplied (deviation_type, group_key) filters.
    Used by the cross-filter in the Action Center.
    """
    session_data = store.get(session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    # Parse filter list
    filter_list: list[tuple[str, str]] = []
    for f in filters:
        if ":" in f:
            dev_type, group_key = f.split(":", 1)
            filter_list.append((dev_type.strip(), group_key.strip()))

    if not filter_list:
        return JSONResponse(content={"count": 0, "sample_ids": []})

    orders = session_data.get("orders", [])
    matched_ids: list[str] = []

    for o in orders:
        meta  = o.get("metadata", {})
        devs  = o.get("Deviations", [])

        # Build set of (effective_type, group_key) pairs for this order
        order_groups: set[tuple[str, str]] = set()
        for d in devs:
            d_type = d.get("type", "")
            d_rule = d.get("rule_id", "")
            effective = d_rule if (d_type == "DOMAIN_RULE_VIOLATION" and d_rule) else d_type
            key, _ = _compute_group_key(effective, d, meta)
            order_groups.add((effective, key))

        # Order must satisfy ALL filters
        if all((ft, fk) in order_groups for ft, fk in filter_list):
            matched_ids.append(str(o.get("Order_Number", "")))

    return JSONResponse(content={
        "count":      len(matched_ids),
        "ids":        matched_ids,
        "sample_ids": matched_ids[:10],
    })


class GroupAlertPayload(BaseModel):
    session_id: str
    deviation_type: str
    group_key: str
    group_data: dict = {}


@app.get("/compliance/email-preview")
async def compliance_email_preview(
    session_id: str,
    deviation_type: str,
    group_key: str,
    group_count: int = 0,
    group_pct: float = 0.0,
):
    """Build and return email template for a compliance group (no sending)."""
    if not store.get(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    session_data = store.get(session_id)
    # Pull real order IDs from the breakdown cache for this group
    orders = session_data.get("orders", []) if session_data else []
    sample_ids: list = []
    for o in orders:
        if len(sample_ids) >= 100:
            break
        for d in o.get("Deviations", []):
            d_type = d.get("type", "")
            d_rule = d.get("rule_id", "")
            effective = d_rule if (d_type == "DOMAIN_RULE_VIOLATION" and d_rule) else d_type
            if effective == deviation_type:
                meta = o.get("metadata", {})
                key, _ = _compute_group_key(effective, d, meta)
                if key == group_key:
                    sample_ids.append(str(o.get("Order_Number", "")))
                    break
    group = {
        "key": group_key,
        "count": group_count,
        "pct": group_pct,
        "sample_order_ids": sample_ids,
    }
    today = _date.today().strftime("%d %B %Y")
    subject, html_body, plain_body = build_group_alert(deviation_type, group, today)
    to_email = os.getenv("ALERT_TO_EMAIL", "")
    smtp_ok = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS") and to_email)
    return JSONResponse(content={
        "subject": subject, "html_body": html_body, "body": plain_body,
        "recipient": to_email if smtp_ok else "",
        "smtp_configured": smtp_ok,
    })


@app.post("/compliance/send-group-alert")
async def compliance_send_group_alert(payload: GroupAlertPayload):
    """Send (or preview) a group compliance alert email."""
    if not store.get(payload.session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    today = _date.today().strftime("%d %B %Y")
    result = send_group_alert(payload.deviation_type, payload.group_data, today)
    return JSONResponse(content=result)


# ── Orders-page contextual alert ───────────────────────────────────────────────

@app.get("/compliance/orders-alert-preview")
async def orders_alert_preview(
    session_id: str,
    order_count: int = 0,
    deviation_type: Optional[str] = None,
    group_key: Optional[str] = None,
    filters: list[str] = Query(default=[]),   # "TYPE:key" for intersection
    status: Optional[str] = None,
    risk: Optional[str] = None,
):
    """Build OFI-branded alert email for whatever filter is active in Orders page."""
    if not store.get(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    today    = _date.today().strftime("%d %B %Y")
    to_email = os.getenv("ALERT_TO_EMAIL", "")
    smtp_ok  = bool(os.getenv("SMTP_USER") and os.getenv("SMTP_PASS") and to_email)

    subject, html_body, plain_body = build_context_alert(
        order_count=order_count,
        today=today,
        deviation_type=deviation_type,
        group_key=group_key,
        intersection_filters=filters or None,
        status=status,
        risk=risk,
    )
    return JSONResponse(content={
        "subject": subject,
        "html_body": html_body,
        "body": plain_body,
        "recipient": to_email if smtp_ok else "",
        "smtp_configured": smtp_ok,
    })


class OrdersAlertSendPayload(BaseModel):
    session_id: str
    order_count: int = 0
    deviation_type: Optional[str] = None
    group_key: Optional[str] = None
    intersection_filters: list[str] = []
    status: Optional[str] = None
    risk: Optional[str] = None


@app.post("/compliance/orders-alert-send")
async def orders_alert_send(payload: OrdersAlertSendPayload):
    """Send OFI-branded alert for the current Orders filter context."""
    if not store.get(payload.session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    today = _date.today().strftime("%d %B %Y")
    result = send_context_alert(
        order_count=payload.order_count,
        today=today,
        deviation_type=payload.deviation_type,
        group_key=payload.group_key,
        intersection_filters=payload.intersection_filters or None,
        status=payload.status,
        risk=payload.risk,
    )
    return JSONResponse(content=result)

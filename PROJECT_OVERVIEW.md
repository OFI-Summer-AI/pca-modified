# OFI — Process Compliance Agent (PCA)
## Full Project Overview: What We Are Building & How It Works

> Last updated: 2026-05-25

---

## What This Is

A **logistics compliance auditing tool** that ingests raw SAP delivery data (CSV/XLSX), automatically detects process deviations across hundreds of thousands of orders, scores risk, and surfaces AI-generated root cause analysis — all running locally with no cloud API keys.

The input is a flat activity log where each row is one movement event (one line on a delivery note). The output is a structured compliance report: which orders deviated, how severely, why, and what to do about it.

---

## The Data

**Source file:** `LOGISTIC_ACTIVITIES.csv` — 3 million rows, ~573,000 unique VGBEL (delivery) orders.

Each row represents one material movement on a delivery:

| Column | What it is | Pipeline role |
|--------|-----------|---------------|
| `VGBEL` | Delivery/order number | Groups all rows for one order (`order_id_col`) |
| `KEY` | Movement type ("Plant Movement", "Customer Movement") | Activity template |
| `CHANGED_FROM` | Source location code (e.g. "NL03", "DE06") | Activity template + `actual_source` metadata |
| `CHANGED_TO` | Destination location code | Activity template |
| `WADAT_IST` | Actual movement date | `timestamp_col` + `actual_date` metadata |
| `EINDT` | Scheduled delivery date | `scheduled_date` metadata (delay detection) |
| `DD_FLAG` | Delay flag (YES/NO set by SAP) | `delay_flag` metadata |
| `OPTIMAL_SOURCE_LOCATION` | System-recommended source | `optimal_source` metadata (WRONG_SOURCE rule) |
| `MATNR` | Material number | NOT the order key — blacklisted in schema detector |
| `WERKS` | Plant code | PLANT_MISMATCH rule |
| `ALL_PRODUCTION_PLANT` | Assigned production plant | PLANT_MISMATCH rule |

**Key insight:** VGBEL is always the order grouping key. MATNR is an item within an order — one order has many MATNR rows, all sharing the same VGBEL. Most orders in this dataset have exactly **one movement step** (same KEY + CHANGED_FROM + CHANGED_TO repeated across material rows, deduped to one activity). Compliance is checked via rules (source routing, delay), not step sequences.

---

## Architecture

```
User Browser (React 18, Vite, port 3000)
        │
        │  HTTP (proxied by Vite → localhost:8001)
        ▼
FastAPI Backend (Python, port 8001)
        │
        ├── In-memory session store (1-hour TTL, ~1–1.5GB RAM for 573K orders)
        ├── pipeline/          ← analysis modules
        ├── chatbot/           ← co-pilot modules
        └── Ollama (localhost:11434, qwen2.5:1.5b)
```

**No cloud APIs. No database. No auth.** All AI runs locally via Ollama. Sessions live in RAM.

---

## The Pipeline — Step by Step

When the user clicks "Run Analysis", `_run_pipeline()` in `main.py` runs synchronously:

```
File on disk
   ↓
Step 1  schema_detector.detect_schema()        ~3–5s    Ollama call #1
   ↓
Step 2  parser.build_orders_map()              ~25–45s  DuckDB
   ↓
Step 3a flow_builder.build_step_frequencies()  ~5–10s   Python Counter
Step 3a flow_builder.get_top_sequences()       ~5–10s   Python Counter
   ↓
Step 3b flow_inferrer.infer_flow()             ~3–5s    Ollama call #2
   ↓
Step 4  deviation_engine.run_all_orders()      ~10–15s  ProcessPoolExecutor (16 cores)
   ↓
Step 5  rca_engine.enrich_with_rca()           ~10–20s  template lookup (zero AI)
   ↓
Step 6  _safe() + format_final_output()        ~15–25s  aggregates
   ↓
session_store.set(session_id, session_data)    RAM — ~1–1.5GB for 573K orders
   ↓
JSONResponse(output)                           ~10KB — NO full orders array
```

**Total: ~2–3 minutes for 3M rows / 573K orders.**

After pipeline: two AI calls fire in background (non-blocking):
- `POST /summary` → executive narrative paragraph (~5s)
- `POST /insights/clusters` → pattern observations across all orders (~5s)

---

### Step 1 — Schema Detection (`schema_detector.py`)

Sends 3 sample rows + column headers to Ollama. Returns `order_id_col`, `timestamp_col`, `activity_derivation`, `domain`.

**Post-validation forces known-good values:**
- AI-chosen order column overridden if VGBEL (or other known names) exist
- MATNR, CHARG, WERKS, etc. blacklisted from being order ID
- `_merge_known_extra_cols()` always injects these into `extra_cols` regardless of AI output:
  - `DD_FLAG` → `delay_flag`
  - `EINDT` → `scheduled_date`
  - `WADAT_IST` → `actual_date`
  - `OPTIMAL_SOURCE_LOCATION` → `optimal_source`
  - `CHANGED_FROM` → `actual_source`

**Auto domain rules (no AI):**
- CHANGED_FROM + OPTIMAL_SOURCE_LOCATION → WRONG_SOURCE rule (severity: HIGH)
- WERKS + ALL_PRODUCTION_PLANT → PLANT_MISMATCH rule (severity: MEDIUM)
- Skips if col_b is >5% multi-valued or <10% populated

---

### Step 2 — Parsing & Grouping (`parser.py`)

7 DuckDB SQL queries against the DataFrame, one connection:

| Query | Output |
|-------|--------|
| Deduped steps by timestamp | `steps` list per order |
| Steps on COUNT(DISTINCT DATE) > 1 | `dup_steps` per order |
| `LOWER(TRIM(col_a)) != LOWER(TRIM(col_b))` | `domain_violations` — **case-insensitive** to prevent "nl03" vs "NL03" false positives |
| `actual_date > scheduled_date` | `delay_orders` set |
| `DD_FLAG IN ('YES','1','TRUE','Y')` | `delay_flag_orders` set |
| `(MAX(ts) − MIN(ts)) / 3600` | `tat_hours` per order |
| `FIRST(col) FILTER (WHERE col IS NOT NULL)` | `metadata` dict — first **non-null** value per column |

**Metadata null safety:** `_assemble()` explicitly checks `v is None` before `str(v)` — prevents Python `None` becoming the string `"None"` in metadata fields.

**Pandas fallback** (if DuckDB unavailable): same logic, uses `bfill().iloc[0]` for metadata.

---

### Step 3 — Flow Building & Inference

- **`flow_builder.py`**: Counter over step sets → frequencies; Counter over joined sequences → top 20
- **`flow_inferrer.py`** (Ollama call #2): Top 5 sequences + 20 frequencies → `standard_flow`, `critical_steps`
- `domain_rules` always forced `[]` from inferrer — auto-detection in schema_detector is used instead

---

### Step 4 — Deviation Engine (`deviation_engine.py`)

6 checks per order, parallelised with ProcessPoolExecutor (≥5,000 orders):

| # | Type | Severity | Trigger |
|---|------|----------|---------|
| 1 | MISSING_CRITICAL_STEP | CRITICAL | Critical step absent from actual flow |
| 2 | OUT_OF_SEQUENCE | HIGH | Standard steps in wrong order |
| 3 | DUPLICATE_STEP | LOW | Same step on different dates — **only when standard_flow exists** |
| 4 | DOMAIN_RULE_VIOLATION | HIGH/MEDIUM | CHANGED_FROM ≠ OPTIMAL_SOURCE_LOCATION (WRONG_SOURCE) or WERKS ≠ ALL_PRODUCTION_PLANT (PLANT_MISMATCH) |
| 5 | DELAYED | HIGH | Actual date > Scheduled date |
| 6 | DELAY_FLAG | MEDIUM | DD_FLAG = YES |

**Scoring:** CRITICAL=40, HIGH=25, MEDIUM=10, LOW=5  
**Status:** score≥40 → BLOCKED · score≥20 → ALERT · else → PASS

---

### Step 5 — Static RCA (`rca_engine.py`)

Zero AI. Template pools per deviation type (2–3 variants each), rotated by order index. Adds `root_cause`, `business_risk`, `recommendation` to every non-compliant order. This text is shown immediately when opening an order — replaced by contextual AI analysis once that loads.

---

### Step 6 — Format (`formatter.py`)

Single-pass builds: `statusSummary`, `heatmap`, `insights` (top 10), `riskTopOrders`, `deviationTypeCounts`, `flowBubbles`, `topSequences`, `summary`. Response ~10KB. Full orders array never sent to frontend.

---

## On-Demand AI Features

### Contextual RCA (`pipeline/contextual_rca.py`)

Called by `POST /rca/contextual` when user opens an OrderDetail page. Cached per order.

**Logic:**
1. Extract facts from metadata: actual source (CHANGED_FROM), optimal source (OPTIMAL_SOURCE_LOCATION), dates (WADAT_IST, EINDT), plant (WERKS)
2. `_parse_flow_location()` parses "plant movement from DE06 to LU05" as backup if metadata missing
3. **Case-insensitive comparison:** `actual.lower() != optimal.lower()` → sets `has_real_locations`
4. **If locations genuinely differ:** prompt specifically names both ("why was DE06 used instead of NL03")
5. **If multiple deviations** (e.g. WRONG_SOURCE + DELAY_FLAG): prompt broadened to cover all — "why DE06 was used instead of NL03 AND why there was a registered delay flag"
6. **If locations equal or unknown:** generic deviation-type prompt ("what caused this WRONG_SOURCE deviation")
7. AI output validated: all 3 fields >25 chars, else fallback to `_enriched_fallback()` with real values substituted
8. Fallback also appends delay context when delay is a secondary deviation: "Additionally, a delivery delay was registered on this order."

### Cluster Insights (`pipeline/cluster_insights.py`)

Called once in background after analysis. Aggregates stats → Ollama → 3 pattern sentences shown on Dashboard banner.

### Executive Summary (`pipeline/executive_summary.py`)

Called once in background after analysis. One Ollama call → narrative paragraph on Dashboard.

---

## Compliance Co-pilot (Chatbot)

### Architecture

Every user message goes through Ollama. Pandas computes accurate numbers first when needed; AI narrates them conversationally.

```
User message
    ↓
Intent classifier (keyword routing — no AI)
    ↓
ORDER_LOOKUP    → pandas finds order by ID  → AI writes narrative about it
Structured query → pandas computes data    → AI explains findings
Greeting/Open   →                            AI responds directly
```

### Intent Routing (`chatbot/intent_classifier.py`)

| Intent | Triggered by |
|--------|-------------|
| `ORDER_LOOKUP` | 6–12 digit number in question + context words |
| `GREETING` | "hi", "hello", "thanks", "what can you do", etc. |
| `DELAY_ANALYSIS` | "delay", "late", "overdue", "behind schedule", etc. |
| `SOURCE_ANALYSIS` | "wrong source", "optimal source", "source location", etc. |
| `PLANT_ANALYSIS` | "plant", "warehouse", "location", "werks", etc. |
| `STATUS_QUERY` | "compliance status", "how many blocked", "adherence", etc. |
| `RANKING_QUERY` | "top risk", "highest risk", "worst orders", "top 10", etc. |
| `DEVIATION_QUERY` | "deviation", "violation", "most common", "what went wrong", etc. |
| `SUMMARY_REQUEST` | "summary", "overview", "how are we doing", "brief me", etc. |
| `OPEN_ENDED` | Everything else |

### What Pandas Computes (`chatbot/pandas_queries.py`)

| Handler | What it returns |
|---------|----------------|
| `order_lookup` | Order status, movement, source used vs required, dates, deviation list, root cause |
| `delay_analysis` | Count + % of delayed orders, grouped by source location (top 10) |
| `source_analysis` | Count of WRONG_SOURCE orders, table of order/used/required/status |
| `plant_analysis` | Order distribution by CHANGED_FROM / WERKS / CHANGED_TO with BLOCKED/ALERT counts |
| `material_analysis` | Top materials by order volume + blocked count + avg score |
| `status_query` | BLOCKED/ALERT/PASS counts with percentages |
| `ranking_query` | Top 10 risk orders or top compliant orders |
| `deviation_query` | All deviation types with counts, most common highlighted |
| `summary_query` | Full dataset summary: totals, adherence, avg score, top issue |

### What AI Does (`chatbot/gemini_chat.py`)

Three functions, all calling Ollama:

| Function | Used when | Context given to AI |
|----------|-----------|---------------------|
| `ask_about_order` | ORDER_LOOKUP | Full order facts: movement, source used vs required, dates, deviations, root cause |
| `ask_with_data` | Structured intents | Pandas-computed numbers + data rows + dataset summary |
| `ask_open` | Greeting / open-ended | Dataset snapshot: totals, adherence %, top deviations, top 5 risk orders |

AI context always includes: total orders, BLOCKED/ALERT/PASS counts, adherence %, top 5 deviation types with counts, top 5 risk orders.

### What You Can Ask the Chatbot (and Get a Correct Answer)

**Order lookups — always accurate:**
- "Show me order 22376390"
- "Tell me about order 22553605"
- "What is the status of order 22315045"
- "Give me details on 22376390"
- Any 6–12 digit order number with a context word

**Compliance overview:**
- "Give me a compliance summary"
- "How are we doing overall?"
- "What is the overall compliance status?"
- "How many orders are blocked?"
- "What is the adherence rate?"

**Delay analysis:**
- "Which orders are delayed?"
- "How many deliveries are late?"
- "Show me delay breakdown by location"
- "Which locations have the most delays?"
- "How many orders have the delay flag set?"

**Source routing issues:**
- "Which orders used the wrong source location?"
- "Show me wrong source violations"
- "How many orders have suboptimal routing?"

**Deviation breakdown:**
- "What are the most common deviations?"
- "Show me deviation breakdown"
- "What compliance issues appear most often?"
- "What went wrong across the dataset?"

**Risk ranking:**
- "Show me the top 10 risk orders"
- "Which orders have the highest deviation score?"
- "What are the worst performing orders?"

**Location / plant analysis:**
- "Which plants have the most issues?"
- "Show order distribution by source location"
- "Which warehouses have the most blocked orders?"

**Open-ended (AI answers from context, accuracy depends on model):**
- "What patterns do you see in the compliance data?"
- "What should we focus on to improve compliance?"
- "Why might we have so many WRONG_SOURCE violations?"
- "Is the 15% non-compliance rate typical for logistics?"
- General conversation, greetings, follow-up questions

### What the Chatbot Cannot Answer Reliably

- Questions requiring cross-referencing with external data (SAP master data, contracts, stock levels)
- "Why does order X use BE03?" — AI can observe the violation but cannot know the real business reason
- Questions about orders from a previous session (session lost on server restart)
- Precise percentage breakdowns for very specific subcategories (AI may approximate)
- Questions outside the dataset (competitor benchmarks, industry standards, etc.)

---

## Frontend Pages

### Upload (`Upload.jsx`)
- **Particle canvas:** 110 gold particles, attraction physics (gather toward cursor within 180px)
- **Physics:** `vx += (cursor_dx/d) * 0.45` — velocity accumulation; `vx = vx * 0.90 + homeVx * 0.015` — damping + spring-back
- **MAX_CONN = 4:** each particle draws at most 4 lines → prevents dense star-cluster shapes
- **REPULSE = 28px:** soft push keeps particles naturally scattered; connection only drawn when `dd > REPULSE`
- **Progress:** `97 * (1 − e^(−t/90000))` — asymptotic, never stalls; jumps to 100% when backend responds
- **Elapsed timer:** real seconds counter displayed while pipeline runs

### Dashboard (`Dashboard.jsx`)
- **Cluster Insights Banner** at top: numbered AI pattern list, "Identifying compliance patterns…" loading state
- **KPI Row:** Adherence Rate = green (high is good); Non-Compliant count = red (high is bad)
- **Executive Summary:** AI narrative paragraph
- **Charts:** deviation bar chart, risk heatmap, flow bubbles, top sequences

### Orders (`Orders.jsx`)
- Server-side paginated: `GET /orders?page=&limit=&status=&risk=&search=&date_from=&date_to=`
- No full list in frontend memory

### OrderDetail (`OrderDetail.jsx`)
- **Actual flow badge:** WRONG_SOURCE orders show `WARN` with "correct source is BE04" — not ALLOW
- **Deviations:** `rule_id` shown as primary label (e.g. WRONG_SOURCE), internal `type` as subtitle
- **Order Date:** derived from `metadata.WADAT_IST` → `metadata.actual_date` → `metadata.EINDT`
- **Cycle Time:** only shown when `tat_hours > 0`
- **Contextual RCA:** static template shown immediately, replaced with AI text on load; `useRef` prevents double-fetch

### Chat Panel (`ChatPanel.jsx` + `ChatMessage.jsx`)
- 6 suggestion chips with category icons
- **Markdown rendering:** `**bold**` → `<strong>`, `- bullet` → styled bullet row, `\n` → line breaks
- Spinner while AI is generating
- Auto-focus on panel open

---

## What Is AI vs Hardcoded

| Component | AI? | Notes |
|-----------|-----|-------|
| Schema detection | Yes — Ollama | Column identification, activity template |
| Flow inference | Yes — Ollama | Standard sequence from observed patterns |
| Deviation detection | **No** | 6 fixed rule-based checks |
| Static RCA | **No** | Template rotation (rca_engine.py) |
| Contextual RCA (OrderDetail) | Yes — Ollama | Order-specific, uses real metadata values |
| Cluster insights (Dashboard) | Yes — Ollama | Patterns across all flagged orders |
| Executive summary (Dashboard) | Yes — Ollama | Narrative paragraph |
| Chatbot — order lookup | **No** | pandas finds order, AI narrates |
| Chatbot — structured queries | **No** + Yes | pandas computes, AI explains |
| Chatbot — open/greeting | Yes — Ollama | Direct AI with dataset context |

---

## Session Model

```python
session_data = {
    "schema":                {...},
    "domain":                "logistics",
    "standard_flow":         [...],
    "critical_steps":        [...],
    "domain_rules":          [...],        # from schema_detector auto-detection
    "orders":                safe_orders,  # 573K dicts — ~1–1.5GB RAM
    "summary":               {...},
    "contextual_rca_cache":  {},           # per-order AI RCA, populated on demand
    "cluster_insights":      [...],        # 3 pattern sentences, populated once
}
```

TTL: 1 hour. No persistence — server restart clears all sessions.

---

## API Endpoints

| Method | Path | What it does | Latency |
|--------|------|-------------|---------|
| GET | `/analyze-default` | Run full pipeline on DEFAULT_TABLE_A | ~2–3 min |
| POST | `/analyze` | Run full pipeline on uploaded file | ~2–3 min |
| GET | `/orders` | Paginated + filtered orders list | <100ms |
| GET | `/orders/{id}` | Single order by Order_Number | <10ms |
| POST | `/rca/contextual` | Per-order AI RCA (cached) | ~3–5s first call |
| POST | `/insights/clusters` | Pattern insights across all orders (cached) | ~5s first call |
| POST | `/summary` | Executive narrative (Ollama) | ~5s |
| POST | `/chat` | Compliance co-pilot | ~3–8s (AI) / <50ms (local) |
| POST | `/send-alerts` | SMTP emails for BLOCKED/HIGH orders | varies |
| GET | `/health` | `{"status": "ok"}` | instant |
| GET | `/default-files` | Check which data files exist | instant |

---

## Known Limitations

1. **No session persistence** — server restart clears all sessions; user must re-run analysis
2. **ProcessPoolExecutor + `--reload`** — may conflict on Windows; auto-falls back to sequential
3. **WADAT_IST daily granularity** — multiple materials per order on same day have non-deterministic step ordering
4. **No auth** — anyone on port 8001 can call any endpoint
5. **`gemini_chat.py` filename is legacy** — uses Ollama, not Gemini
6. **Single-step orders** — most logistics orders have 1 activity; compliance is rule-based only (no sequence analysis)
7. **qwen2.5:1.5b is a small model** — chatbot AI quality limited; open-ended answers may be generic; structured queries (pandas-backed) are always accurate

---

## How to Run

```powershell
# 1. Start Ollama
ollama serve
ollama pull qwen2.5:1.5b

# 2. Backend
cd backend
python -m uvicorn main:app --reload --port 8001

# 3. Frontend
cd frontend
npm run dev    # http://localhost:3000
```

Place your CSV in `backend/data/` and set `DEFAULT_TABLE_A=yourfile.csv` in `backend/.env`.

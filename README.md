# PAM Agent — FastAPI Backend

Process Compliance Agent backend for SAP P2P procurement workflow analysis.

## Setup

```bash
cd pam_agent
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys and SMTP credentials
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `RCA_PROVIDER` | LLM provider: `openai` or `groq` | `openai` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `GROQ_API_KEY` | Groq API key (fallback) | — |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USER` | SMTP username | — |
| `SMTP_PASS` | SMTP password / app password | — |
| `ALERT_FROM_EMAIL` | Sender email address | — |
| `ALERT_TO_EMAIL` | Recipient email address | — |

## Run

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at `http://localhost:8000/docs`

## Endpoints

### `POST /analyze`

Accepts multipart form upload of event log files and runs the full pipeline.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `table_a` | File (CSV/XLSX) | Yes | Event log |
| `table_b` | File (CSV/XLSX) | No | Reference/master data |
| `definition_mode` | string | No | `"AI"` (default) |

**Response:**
```json
{
  "status": "success",
  "totalOrders": 40,
  "heatmap": { "CRITICAL": 8, "HIGH": 5, "MEDIUM": 3, "LOW": 24 },
  "statusSummary": { "BLOCKED": 8, "ALERT": 14, "PASS": 18 },
  "insights": [...],
  "orders": [...],
  "summary": { "total_orders": 40, "blocked": 8, ... }
}
```

### `POST /send-alerts`

Sends HTML email alerts for BLOCKED and HIGH-risk orders.

```json
{
  "orders": [{ "Order_Number": "...", "Process_Status": "BLOCKED", ... }]
}
```

### `GET /health`

Returns `{ "status": "ok" }`.

## Example curl

```bash
curl -X POST http://localhost:8000/analyze \
  -F "table_a=@event_log.csv" \
  -F "definition_mode=AI"
```

## Expected CSV columns

| Column | Purpose |
|--------|---------|
| `Case Key` / `Ebeln` / `Order_Number` / `Purchase Order` | Order identifier |
| `Activity En` / `Activity De` | Activity name |
| `Eventtime` | Event timestamp |

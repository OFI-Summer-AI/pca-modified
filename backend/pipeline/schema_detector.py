import json
import logging

import pandas as pd

from .ai_client import call_ai

logger = logging.getLogger(__name__)

_ORDER_COLS = [
    "VGBEL", "Case Key", "Ebeln", "EBELN", "Order_Number",
    "Purchase Order", "order_id", "REFERENCE", "Reference",
    "DOC_NUM", "DELIVERY", "SHIPMENT_ID",
]
_TS_COLS = [
    "Eventtime", "WADAT_IST", "EINDT", "Date", "Timestamp",
    "datetime", "event_time", "BUDAT", "ERDAT",
]
_NEVER_ORDER_COLS = {
    "MATNR", "CHARG", "LGORT", "WERKS", "BUKRS", "MENGE",
    "MEINS", "LIFNR", "KUNNR", "BELNR", "POSNR",
}

# Column-pair rules that can be auto-detected without AI
# Each entry: (col_a, col_b, rule_id, description, severity)
_AUTO_DOMAIN_RULES = [
    (
        "CHANGED_FROM", "OPTIMAL_SOURCE_LOCATION",
        "WRONG_SOURCE",
        "Material moved from non-optimal source location (CHANGED_FROM ≠ OPTIMAL_SOURCE_LOCATION)",
        "HIGH",
    ),
    (
        "WERKS", "ALL_PRODUCTION_PLANT",
        "PLANT_MISMATCH",
        "Movement plant differs from assigned production plant (WERKS ≠ ALL_PRODUCTION_PLANT)",
        "MEDIUM",
    ),
]


def _detect_domain_rules(df: pd.DataFrame) -> list:
    """
    Auto-detect meaningful compliance rules from column names — no AI needed.
    Only adds a rule if BOTH columns exist and the column values are single-valued
    (not comma-separated lists), to avoid false positives.
    """
    cols = set(df.columns)
    rules = []

    for col_a, col_b, rule_id, description, severity in _AUTO_DOMAIN_RULES:
        if col_a not in cols or col_b not in cols:
            continue

        # Skip if col_b looks like it contains comma-separated multi-values
        sample = df[col_b].dropna().astype(str).head(200)
        multi_val_pct = sample.str.contains(",").mean()
        if multi_val_pct > 0.05:   # >5% of rows have commas → skip
            logger.info(
                "Skipping domain rule %s — %s appears multi-valued (%.0f%% contain commas)",
                rule_id, col_b, multi_val_pct * 100,
            )
            continue

        # Only add if col_b has meaningful data (not all null/empty)
        non_null = df[col_b].notna().mean()
        if non_null < 0.1:
            logger.info("Skipping domain rule %s — %s is mostly null (%.0f%% populated)", rule_id, col_b, non_null * 100)
            continue

        rules.append({
            "rule_id": rule_id,
            "description": description,
            "col_a": col_a,
            "col_b": col_b,
            "severity": severity,
        })
        logger.info("Auto-detected domain rule: %s (%s ≠ %s)", rule_id, col_a, col_b)

    return rules


def _build_prompt(headers: list, samples: list) -> str:
    brief = [{k: str(v)[:40] for k, v in row.items()} for row in samples[:3]]
    return f"""You are a process-mining analyst. Identify key columns in this data table.

Columns: {json.dumps(headers)}

Sample rows (3):
{json.dumps(brief, indent=2)}

Fill in the JSON below. Return ONLY the JSON — no explanation, no markdown.

{{
  "order_id_col": "the column that GROUPS many rows into one order/delivery/document — one value appears in 10-100 rows; look first for: VGBEL, Case Key, Ebeln, Order_Number, REFERENCE, delivery number",
  "timestamp_col": "date or datetime column for when the event happened, or null",
  "activity_derivation": "template string describing the process step using {{COLNAME}} placeholders — describe what HAPPENED (movement type, status change, location) — do NOT use material codes, batch numbers, or numeric IDs",
  "domain": "one word: logistics or procurement or finance or manufacturing or generic"
}}

Rules:
- order_id_col: must be a GROUPING key (one order = many rows). Never pick MATNR, CHARG, LGORT, WERKS, or any item/batch/location code.
- activity_derivation example: if columns include KEY, CHANGED_FROM, CHANGED_TO use "{{KEY}} from {{CHANGED_FROM}} to {{CHANGED_TO}}"
- If an activity column like 'Activity En' or 'KEY' exists, base the derivation on it."""


# Known extra columns — always extracted when present, regardless of AI output.
# These feed order metadata used by contextual RCA and delay detection.
_KNOWN_EXTRA_COLS = [
    ("delay_flag",    "DD_FLAG"),
    ("scheduled_date","EINDT"),
    ("actual_date",   "WADAT_IST"),
    ("optimal_source","OPTIMAL_SOURCE_LOCATION"),
    ("actual_source", "CHANGED_FROM"),
]


def _merge_known_extra_cols(df: pd.DataFrame, result: dict) -> None:
    """Ensure key columns are always in extra_cols even when AI schema skips them.

    AI prompt only asks for 4 fields and never returns extra_cols, so without this
    the metadata dict is always empty and contextual RCA has no real values to use.
    Hardcoded mappings fill the gap; any AI-detected extras are kept alongside them.
    """
    cols = set(df.columns)
    existing = result.get("extra_cols") or {}
    for flag, col in _KNOWN_EXTRA_COLS:
        if col in cols and flag not in existing:
            existing[flag] = col
            logger.info("Auto-added extra_col: %s → %s", flag, col)
    result["extra_cols"] = existing


def detect_schema(df: pd.DataFrame) -> dict:
    headers = list(df.columns)
    samples = df.head(5).to_dict(orient="records")

    try:
        result = call_ai(_build_prompt(headers, samples), expect_json=True)
        result = _validate_and_clean(result, df)
        logger.info("Schema detected via AI: domain=%s  order_col=%s",
                    result.get("domain", "?"), result.get("order_id_col", "?"))
    except Exception as e:
        logger.warning("Schema AI failed: %s — using fallback", e)
        result = _fallback_schema(df)

    # Always ensure key columns land in extra_cols regardless of AI/fallback path
    _merge_known_extra_cols(df, result)

    # Always auto-detect domain rules regardless of AI success/failure
    result["domain_rules"] = _detect_domain_rules(df)
    logger.info("Domain rules auto-detected: %d", len(result["domain_rules"]))

    return result


def _validate_and_clean(result: dict, df: pd.DataFrame) -> dict:
    cols = set(df.columns)

    oc = result.get("order_id_col", "")
    col_missing = oc not in cols
    col_blacklisted = oc in _NEVER_ORDER_COLS
    known_good = next((c for c in _ORDER_COLS if c in cols), None)
    col_overridden_by_known = known_good and oc != known_good

    if col_missing or col_blacklisted or col_overridden_by_known:
        corrected = known_good or _best_order_col(df)
        logger.warning(
            "AI order_id_col '%s' rejected (missing=%s blacklisted=%s known_good=%s) — using '%s'",
            oc, col_missing, col_blacklisted, known_good, corrected,
        )
        result["order_id_col"] = corrected

    tc = result.get("timestamp_col")
    if tc and tc not in cols:
        result["timestamp_col"] = next((c for c in _TS_COLS if c in cols), None)
        logger.warning("AI timestamp_col '%s' not in columns — corrected", tc)

    extra = {}
    for k, v in result.get("extra_cols", {}).items():
        if v and str(v).lower() not in ("null", "none", "") and v in cols:
            extra[k] = v
    result["extra_cols"] = extra

    if not isinstance(result.get("domain"), str):
        result["domain"] = "generic"

    return result


def _best_order_col(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    for c in _ORDER_COLS:
        if c in cols:
            return c
    n = len(df)
    best, best_score = df.columns[0], float("inf")
    for c in df.columns:
        if c in _NEVER_ORDER_COLS:
            continue
        u = df[c].nunique()
        if u < 2:
            continue
        ratio = u / n
        score = abs(ratio - 0.01)
        if score < best_score:
            best_score = score
            best = c
    return best


def _fallback_schema(df: pd.DataFrame) -> dict:
    cols = set(df.columns)
    order_col = _best_order_col(df)
    ts_col = next((c for c in _TS_COLS if c in cols), None)

    if "Activity En" in cols:
        activity = "{Activity En}"
    elif "KEY" in cols and "CHANGED_FROM" in cols and "CHANGED_TO" in cols:
        activity = "{KEY} from {CHANGED_FROM} to {CHANGED_TO}"
    elif "CHANGED_FROM" in cols and "CHANGED_TO" in cols:
        activity = "Movement from {CHANGED_FROM} to {CHANGED_TO}"
    elif "KEY" in cols:
        activity = "{KEY}"
    else:
        activity = f"{{{order_col}}}"

    extra = {}
    for flag, col in [
        ("delay_flag",    "DD_FLAG"),
        ("scheduled_date","EINDT"),
        ("actual_date",   "WADAT_IST"),
        ("optimal_source","OPTIMAL_SOURCE_LOCATION"),
        ("actual_source", "CHANGED_FROM"),
    ]:
        if col in cols:
            extra[flag] = col

    domain = "logistics" if any(c in cols for c in ("CHANGED_FROM", "VGBEL", "WADAT_IST")) else "generic"

    return {
        "order_id_col": order_col,
        "timestamp_col": ts_col,
        "activity_derivation": activity,
        "domain": domain,
        "extra_cols": extra,
    }

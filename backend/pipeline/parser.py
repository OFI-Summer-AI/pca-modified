import io
import math
import re

import pandas as pd


def parse_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    buf = io.BytesIO(file_bytes)
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(buf)
    return pd.read_csv(buf, on_bad_lines="skip", low_memory=False)


def _apply_template(df: pd.DataFrame, template: str) -> pd.Series:
    """Vectorized application of a {COLNAME} format string across DataFrame rows."""
    parts = re.split(r"\{(\w+)\}", template)
    result = pd.Series("", index=df.index, dtype=str)
    for i, part in enumerate(parts):
        if i % 2 == 0:
            result = result + part
        else:
            if part in df.columns:
                result = result + df[part].fillna("").astype(str)
            else:
                result = result + f"{{{part}}}"
    return result


def apply_domain_rules(df: pd.DataFrame, orders_map: dict, domain_rules: list, order_col: str) -> None:
    """Apply domain rules to an already-built orders_map without re-parsing.
    Modifies orders_map in place — avoids a second full build_orders_map call."""
    for rule in domain_rules:
        col_a = rule.get("col_a", "")
        col_b = rule.get("col_b", "")
        rule_id = rule.get("rule_id", "DOMAIN_RULE")
        if col_a not in df.columns or col_b not in df.columns:
            continue
        mask = (
            df[col_a].notna()
            & df[col_b].notna()
            & (df[col_a].astype(str).str.strip().str.lower() != df[col_b].astype(str).str.strip().str.lower())
        )
        for oid in df.loc[mask, order_col].unique():
            sid = str(oid)
            if sid in orders_map and rule_id not in orders_map[sid]["domain_violations"]:
                orders_map[sid]["domain_violations"].append(rule_id)


def build_orders_map(df: pd.DataFrame, schema: dict) -> dict:
    """Group DataFrame into per-order dicts. Uses DuckDB when available (10x faster for large files)."""
    order_col = schema["order_id_col"]
    ts_col = schema.get("timestamp_col")
    activity_tpl = schema.get("activity_derivation", f"{{{order_col}}}")
    extra = schema.get("extra_cols", {})
    domain_rules = schema.get("domain_rules", [])

    # Clean order_id
    df = df.dropna(subset=[order_col]).copy()
    df[order_col] = df[order_col].astype(str).str.strip()
    df = df[~df[order_col].str.lower().isin(["nan", "none", ""])]

    if df.empty:
        raise ValueError(f"No valid rows found after filtering on '{order_col}'.")

    # Parse timestamps
    has_ts = bool(ts_col and ts_col in df.columns)
    if has_ts:
        df[ts_col] = pd.to_datetime(df[ts_col], errors="coerce")

    # Derive activity string (pandas vectorized)
    df["_activity"] = _apply_template(df, activity_tpl).str.strip().str.lower()

    try:
        import duckdb
        return _build_duckdb(df, order_col, ts_col, has_ts, extra, domain_rules)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("DuckDB failed (%s) — using pandas fallback", exc)
        return _build_pandas(df, order_col, ts_col, has_ts, extra, domain_rules)


# ── DuckDB path (fast for large files) ──────────────────────────────────────

def _build_duckdb(df, order_col, ts_col, has_ts, extra, domain_rules):
    import duckdb

    con = duckdb.connect()
    con.register("df", df)

    oc = f'"{order_col}"'
    tc = f'"{ts_col}"' if has_ts else None

    # 1. Step sequences — deduped first occurrence, ordered by timestamp
    if has_ts:
        flows_df = con.execute(f"""
            SELECT {oc}, list(_activity ORDER BY min_ts NULLS LAST) AS steps
            FROM (
                SELECT {oc}, _activity, MIN({tc}) AS min_ts
                FROM df GROUP BY {oc}, _activity
            ) GROUP BY {oc}
        """).df()
    else:
        flows_df = con.execute(f"""
            SELECT {oc}, list(_activity) AS steps
            FROM (SELECT DISTINCT {oc}, _activity FROM df)
            GROUP BY {oc}
        """).df()
    flows = dict(zip(flows_df[order_col].astype(str), flows_df["steps"]))

    # 2. Duplicate step detection
    # Threshold: only flag if the same activity appears on DIFFERENT dates (timestamp-based)
    # or, if no timestamp, more than once distinctly.
    # This avoids false positives where multiple item-rows (e.g. different MATNR) share
    # the same activity string in one delivery — that is normal logistics behaviour, not a process error.
    if has_ts:
        dup_df = con.execute(f"""
            SELECT {oc}, list(_activity) AS dup_steps
            FROM (
                SELECT {oc}, _activity
                FROM df
                GROUP BY {oc}, _activity
                HAVING COUNT(DISTINCT DATE_TRUNC('day', {tc})) > 1
            ) GROUP BY {oc}
        """).df()
    else:
        dup_df = con.execute(f"""
            SELECT {oc}, list(_activity) AS dup_steps
            FROM (
                SELECT {oc}, _activity FROM df
                GROUP BY {oc}, _activity HAVING COUNT(*) > 1
            ) GROUP BY {oc}
        """).df()
    dup_steps_per_order = dict(zip(dup_df[order_col].astype(str), dup_df["dup_steps"]))

    # 3. Domain rule violations
    domain_violations: dict = {}
    for rule in domain_rules:
        col_a, col_b = rule.get("col_a", ""), rule.get("col_b", "")
        rule_id = rule.get("rule_id", "DOMAIN_RULE")
        if col_a in df.columns and col_b in df.columns:
            viol_df = con.execute(f"""
                SELECT DISTINCT {oc} FROM df
                WHERE "{col_a}" IS NOT NULL AND "{col_b}" IS NOT NULL
                  AND LOWER(TRIM(CAST("{col_a}" AS VARCHAR))) != LOWER(TRIM(CAST("{col_b}" AS VARCHAR)))
            """).df()
            for oid in viol_df[order_col].astype(str):
                domain_violations.setdefault(oid, []).append(rule_id)

    # 4. Delay detection (actual > scheduled)
    delay_orders: set = set()
    actual_col = extra.get("actual_date")
    sched_col = extra.get("scheduled_date")
    if actual_col and sched_col and actual_col in df.columns and sched_col in df.columns and actual_col != sched_col:
        delay_df = con.execute(f"""
            SELECT DISTINCT {oc} FROM df
            WHERE "{actual_col}" IS NOT NULL AND "{sched_col}" IS NOT NULL
              AND TRY_CAST("{actual_col}" AS DATE) > TRY_CAST("{sched_col}" AS DATE)
        """).df()
        delay_orders = set(delay_df[order_col].astype(str))

    # 5. Delay flag detection
    delay_flag_orders: set = set()
    flag_col = extra.get("delay_flag")
    if flag_col and flag_col in df.columns:
        flag_df = con.execute(f"""
            SELECT DISTINCT {oc} FROM df
            WHERE UPPER(TRIM(CAST("{flag_col}" AS VARCHAR))) IN ('YES', '1', 'TRUE', 'Y')
        """).df()
        delay_flag_orders = set(flag_df[order_col].astype(str))

    # 6. TAT per order
    tat_hours: dict = {}
    if has_ts:
        tat_df = con.execute(f"""
            SELECT {oc},
                   (EPOCH(MAX({tc})) - EPOCH(MIN({tc}))) / 3600.0 AS tat_hours
            FROM df WHERE {tc} IS NOT NULL
            GROUP BY {oc} HAVING COUNT({tc}) >= 2
        """).df()
        tat_hours = dict(zip(tat_df[order_col].astype(str), tat_df["tat_hours"]))

    # 7. Metadata (first NON-NULL value per order for extra columns)
    # Using FILTER (WHERE col IS NOT NULL) ensures we get a real value even when
    # the first row for an order has a null — e.g. OPTIMAL_SOURCE_LOCATION is null
    # on some rows but populated on others within the same VGBEL.
    meta_cols = list({v for v in extra.values() if v and v in df.columns})
    meta_dict = {}
    if meta_cols:
        exprs = ", ".join(
            f'FIRST("{c}") FILTER (WHERE "{c}" IS NOT NULL) AS "{c}"'
            for c in meta_cols
        )
        meta_df = con.execute(f"SELECT {oc}, {exprs} FROM df GROUP BY {oc}").df()
        meta_df[order_col] = meta_df[order_col].astype(str)
        meta_dict = meta_df.set_index(order_col).to_dict("index")

    # 8. All unique order IDs
    all_ids = con.execute(f"SELECT DISTINCT CAST({oc} AS VARCHAR) AS oid FROM df").df()["oid"].tolist()
    con.close()

    return _assemble(all_ids, flows, dup_steps_per_order, domain_violations,
                     delay_orders, delay_flag_orders, tat_hours, meta_dict)


# ── Pandas fallback ──────────────────────────────────────────────────────────

def _build_pandas(df, order_col, ts_col, has_ts, extra, domain_rules):
    if has_ts:
        df = df.sort_values(ts_col, na_position="last")

    df["_is_first"] = ~df.duplicated(subset=[order_col, "_activity"], keep="first")

    # Duplicate detection: only flag if same activity appears on multiple distinct dates
    # (avoids false positives from multiple item-rows with the same activity on the same day)
    if has_ts:
        dup_check = df.groupby([order_col, "_activity"])[ts_col].apply(
            lambda x: x.dt.normalize().nunique()
        )
        dup_steps_per_order = (
            dup_check[dup_check > 1]
            .reset_index(name="_cnt")
            .groupby(order_col)["_activity"]
            .apply(list)
            .to_dict()
        )
    else:
        counts = df.groupby([order_col, "_activity"]).size()
        dup_steps_per_order = (
            counts[counts > 1]
            .reset_index(name="_cnt")
            .groupby(order_col)["_activity"]
            .apply(list)
            .to_dict()
        )

    flows = (
        df[df["_is_first"]]
        .groupby(order_col)["_activity"]
        .apply(list)
        .to_dict()
    )

    domain_violations: dict = {}
    for rule in domain_rules:
        col_a, col_b = rule.get("col_a", ""), rule.get("col_b", "")
        rule_id = rule.get("rule_id", "DOMAIN_RULE")
        if col_a in df.columns and col_b in df.columns:
            mask = (
                df[col_a].notna() & df[col_b].notna()
                & (df[col_a].astype(str).str.strip().str.lower() != df[col_b].astype(str).str.strip().str.lower())
            )
            for oid in df.loc[mask, order_col].unique():
                domain_violations.setdefault(str(oid), []).append(rule_id)

    delay_orders: set = set()
    actual_col = extra.get("actual_date")
    sched_col = extra.get("scheduled_date")
    if actual_col and sched_col and actual_col in df.columns and sched_col in df.columns and actual_col != sched_col:
        delay_orders = set(df.loc[df[actual_col] > df[sched_col], order_col].unique())

    delay_flag_orders: set = set()
    flag_col = extra.get("delay_flag")
    if flag_col and flag_col in df.columns:
        mask = df[flag_col].astype(str).str.strip().str.upper().isin(["YES", "1", "TRUE", "Y"])
        delay_flag_orders = set(df.loc[mask, order_col].unique())

    tat_hours: dict = {}
    if has_ts:
        def _tat(x):
            valid = x.dropna()
            if len(valid) < 2:
                return None
            return (valid.max() - valid.min()).total_seconds() / 3600
        tat_hours = df.groupby(order_col)[ts_col].apply(_tat).to_dict()

    meta_cols = list({v for v in extra.values() if v and v in df.columns})
    meta_dict = {}
    if meta_cols:
        # first() picks the first row regardless of nulls — use first non-null per column
        meta_dict = (
            df.groupby(order_col)[meta_cols]
            .apply(lambda g: g.bfill().iloc[0] if len(g) > 0 else g.iloc[0])
            .to_dict("index")
        )

    all_order_ids = [str(oid) for oid in df[order_col].unique()]
    return _assemble(all_order_ids,
                     {str(k): v for k, v in flows.items()},
                     {str(k): v for k, v in dup_steps_per_order.items()},
                     domain_violations, delay_orders, delay_flag_orders,
                     {str(k): v for k, v in tat_hours.items()}, meta_dict)


# ── Shared assembly ──────────────────────────────────────────────────────────

def _assemble(all_ids, flows, dup_steps, domain_violations,
              delay_orders, delay_flag_orders, tat_hours, meta_dict):
    result = {}
    for sid in all_ids:
        raw_meta = meta_dict.get(sid, {})
        meta = {}
        for c, v in raw_meta.items():
            if v is None or (isinstance(v, float) and math.isnan(v)):
                meta[c] = None
            else:
                s = str(v).strip()
                meta[c] = None if s.lower() in ("none", "nan", "null", "") else s
        result[sid] = {
            "steps": flows.get(sid, []),
            "dup_steps": dup_steps.get(sid, []),
            "domain_violations": domain_violations.get(sid, []),
            "has_delay": sid in delay_orders,
            "has_delay_flag": sid in delay_flag_orders,
            "tat_hours": tat_hours.get(sid),
            "metadata": meta,
        }
    return result

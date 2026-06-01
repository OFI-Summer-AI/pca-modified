import os
from concurrent.futures import ProcessPoolExecutor

SEVERITY_SCORES = {"CRITICAL": 40, "HIGH": 25, "MEDIUM": 10, "LOW": 5}


def _to_list(val):
    """Convert numpy ndarray or None to a plain Python list."""
    if val is None:
        return []
    return val.tolist() if hasattr(val, "tolist") else list(val)


def analyze_order(
    order_id: str,
    order_data: dict,
    standard_flow: list,
    critical_steps: list,
    domain_rules: list,
) -> dict:
    """Run all deviation checks. All inputs are precomputed — no row iteration here."""
    steps = _to_list(order_data.get("steps"))
    dup_steps = _to_list(order_data.get("dup_steps"))
    steps_set = set(steps)
    deviations = []

    # 1. MISSING_CRITICAL_STEP
    for step in critical_steps:
        if step not in steps_set:
            deviations.append({
                "type": "MISSING_CRITICAL_STEP",
                "severity": "CRITICAL",
                "step": step,                                   # ← structured step reference
                "detail": f"Critical step '{step}' not found in actual flow",
            })

    # 2. OUT_OF_SEQUENCE
    standard_set = set(standard_flow)
    std_in_actual = [s for s in steps if s in standard_set]
    expected_order = [s for s in standard_flow if s in set(std_in_actual)]
    if std_in_actual and std_in_actual != expected_order:
        deviations.append({
            "type": "OUT_OF_SEQUENCE",
            "severity": "HIGH",
            "steps": std_in_actual,                            # ← structured step list
            "detail": f"Steps appear out of standard order: {std_in_actual}",
        })

    # 3. DUPLICATE_STEP
    # Only meaningful when a multi-step standard flow exists.
    # For single-step logistics data (standard_flow=[]), the same movement appearing
    # on multiple dates within one delivery is normal behaviour — not a process error.
    if dup_steps and standard_flow:
        deviations.append({
            "type": "DUPLICATE_STEP",
            "severity": "LOW",
            "steps": dup_steps,
            "detail": f"Duplicate steps detected: {dup_steps}",
        })

    # 4. DOMAIN_RULE_VIOLATION
    rule_map = {r["rule_id"]: r for r in domain_rules}
    for rule_id in order_data.get("domain_violations", []):
        rule = rule_map.get(rule_id, {})
        severity = rule.get("severity", "MEDIUM")
        deviations.append({
            "type": "DOMAIN_RULE_VIOLATION",
            "rule_id": rule_id,
            "severity": severity,
            "detail": rule.get("description", f"Rule {rule_id} violated"),
        })

    # 5. DELAYED
    if order_data.get("has_delay"):
        deviations.append({
            "type": "DELAYED",
            "severity": "HIGH",
            "detail": "Actual completion date is later than scheduled date",
        })

    # 6. DELAY_FLAG
    if order_data.get("has_delay_flag"):
        deviations.append({
            "type": "DELAY_FLAG",
            "severity": "MEDIUM",
            "detail": "Delay flag is set on one or more records",
        })

    # Scoring
    score = sum(SEVERITY_SCORES.get(d["severity"], 0) for d in deviations)

    has_critical = any(d["severity"] == "CRITICAL" for d in deviations)
    if has_critical:
        status, risk = "BLOCKED", "CRITICAL"
    elif score >= 40:
        status, risk = "BLOCKED", "HIGH"
    elif score >= 20:
        status, risk = "ALERT", "MEDIUM"
    else:
        status, risk = "PASS", "LOW"

    return {
        "Order_Number": order_id,
        "Standard_Flow": standard_flow,
        "Actual_Flow": steps,
        "Critical_Steps": critical_steps,
        "Deviations": deviations,
        "Deviation_Count": len(deviations),
        "Deviation_Score": score,
        "Process_Status": status,
        "Risk_Level": risk,
        "TAT_Hours": order_data.get("tat_hours"),
        "metadata": order_data.get("metadata", {}),
        "root_cause": "",
        "business_risk": "",
        "recommendation": "",
    }


# ── Module-level worker — must be at top level for Windows ProcessPoolExecutor ──

def _analyze_chunk(args):
    items, standard_flow, critical_steps, domain_rules = args
    return [
        analyze_order(oid, data, standard_flow, critical_steps, domain_rules)
        for oid, data in items
    ]


def run_all_orders(
    orders_map: dict,
    standard_flow: list,
    critical_steps: list,
    domain_rules: list,
) -> list[dict]:
    # Pre-convert numpy arrays to plain Python lists once, before splitting into chunks.
    # This avoids ndarray serialization overhead inside each worker.
    items = [
        (oid, {
            **data,
            "steps": _to_list(data.get("steps")),
            "dup_steps": _to_list(data.get("dup_steps")),
        })
        for oid, data in orders_map.items()
    ]

    n = len(items)
    cpu = min(os.cpu_count() or 4, 16)

    # Not worth the ProcessPoolExecutor spawn overhead for small datasets
    if n < 5_000:
        return [
            analyze_order(oid, data, standard_flow, critical_steps, domain_rules)
            for oid, data in items
        ]

    chunk_size = max(500, -(-n // cpu))           # ceiling division
    chunks = [items[i: i + chunk_size] for i in range(0, n, chunk_size)]
    args_list = [(chunk, standard_flow, critical_steps, domain_rules) for chunk in chunks]

    try:
        with ProcessPoolExecutor(max_workers=cpu) as executor:
            results = list(executor.map(_analyze_chunk, args_list))
        return [order for chunk_result in results for order in chunk_result]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "ProcessPoolExecutor failed (%s) — falling back to sequential", e
        )
        return [
            analyze_order(oid, data, standard_flow, critical_steps, domain_rules)
            for oid, data in items
        ]

import math


def _safe(val):
    if isinstance(val, dict):
        return {k: _safe(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_safe(i) for i in val]
    if isinstance(val, float) and math.isnan(val):
        return None
    if hasattr(val, "item"):  # numpy scalar
        return val.item()
    if hasattr(val, "isoformat"):  # datetime
        return val.isoformat()
    return val


def format_final_output(orders: list[dict], top_sequences: list = None) -> dict:
    """Build the final JSON response.

    Assumes `orders` are already sanitized (no numpy types, no NaN floats).
    Call _safe() on the list before passing here — see main.py::_run_pipeline.
    """
    total = len(orders)

    # Single pass — build all aggregates at once
    blocked, alert, passed = [], [], []
    by_risk: dict = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    score_sum = 0
    dev_count_sum = 0

    for o in orders:
        status = o.get("Process_Status", "PASS")
        risk = o.get("Risk_Level", "LOW")
        score_sum += o.get("Deviation_Score", 0) or 0
        dev_count_sum += o.get("Deviation_Count", 0) or 0

        if status == "BLOCKED":
            blocked.append(o)
        elif status == "ALERT":
            alert.append(o)
        else:
            passed.append(o)

        by_risk.setdefault(risk, []).append(o)

    avg_score = round(score_sum / total, 2) if total > 0 else 0.0
    avg_dev_count = round(dev_count_sum / total, 2) if total > 0 else 0.0

    heatmap = {k: len(v) for k, v in by_risk.items()}

    # Top 10 non-PASS orders by score (for insights table)
    non_pass = blocked + alert
    insights = sorted(non_pass, key=lambda x: x.get("Deviation_Score", 0), reverse=True)[:10]

    # Top 10 orders per risk level (for dashboard heatmap-click interactivity)
    risk_top_orders = {
        k: sorted(v, key=lambda x: x.get("Deviation_Score", 0), reverse=True)[:10]
        for k, v in by_risk.items()
    }

    # Deviation type counts (for bar chart)
    dev_type_counts: dict = {}
    for o in non_pass:
        for d in o.get("Deviations", []):
            t = d.get("type", "UNKNOWN")
            dev_type_counts[t] = dev_type_counts.get(t, 0) + 1

    # FlowBubbles — per-step deviation/pass counts
    standard_flow = orders[0].get("Standard_Flow", []) if orders else []
    critical_steps = orders[0].get("Critical_Steps", []) if orders else []

    step_dev: dict = {s: 0 for s in standard_flow}
    step_pass: dict = {s: 0 for s in standard_flow}

    for o in orders:
        actual_set = set(o.get("Actual_Flow", []))
        for step in standard_flow:
            if step in actual_set:
                step_pass[step] += 1

        for d in o.get("Deviations", []):
            dev_type = d.get("type", "")

            if dev_type == "MISSING_CRITICAL_STEP":
                # deviation engine sets "step" to the exact missing step name
                s = d.get("step")
                if s and s in step_dev:
                    step_dev[s] += 1

            elif dev_type == "OUT_OF_SEQUENCE":
                # deviation engine sets "steps" to the list of out-of-order steps
                for s in (d.get("steps") or []):
                    if s in step_dev:
                        step_dev[s] += 1

            elif dev_type == "DUPLICATE_STEP":
                for s in (d.get("steps") or []):
                    if s in step_dev:
                        step_dev[s] += 1

            # DELAYED / DELAY_FLAG / DOMAIN_RULE_VIOLATION don't map to specific flow steps

    flow_bubbles = {
        "standard_flow": standard_flow,
        "critical_steps": critical_steps,
        "steps": {
            step: {"devCount": step_dev[step], "passCount": step_pass[step]}
            for step in standard_flow
        },
    }

    return {
        "status": "success",
        "totalOrders": total,
        "heatmap": heatmap,
        "statusSummary": {
            "BLOCKED": len(blocked),
            "ALERT": len(alert),
            "PASS": len(passed),
        },
        "insights": insights,
        "riskTopOrders": risk_top_orders,
        "deviationTypeCounts": dev_type_counts,
        "topSequences": top_sequences or [],
        "flowBubbles": flow_bubbles,
        "summary": {
            "total_orders": total,
            "blocked": len(blocked),
            "alert": len(alert),
            "pass": len(passed),
            "high_risk": len(blocked) + len(alert),
            "avg_deviation_score": avg_score,
            "avg_deviation_count": avg_dev_count,
        },
        # NOTE: full orders array omitted — use GET /orders?session_id=... for paginated access
    }

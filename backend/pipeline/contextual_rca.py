"""Contextual RCA — AI-generated root cause using real order values, not templates."""
import logging

from .ai_client import call_ai

logger = logging.getLogger(__name__)

_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Fallback templates with {placeholder} substitution for real values
_FALLBACK = {
    "WRONG_SOURCE": {
        "root_cause": "Order was sourced from {actual_source} instead of the designated optimal location {optimal_source}, indicating a routing decision outside approved guidelines.",
        "business_risk": "Non-optimal sourcing from {actual_source} increases freight cost and may distort supply chain performance metrics.",
        "recommendation": "Verify whether {optimal_source} had sufficient stock at time of movement and enforce source routing controls to prevent recurrence.",
    },
    "DELAYED": {
        "root_cause": "Actual delivery on {actual_date} exceeded the scheduled date of {scheduled_date}, pointing to a bottleneck or resource constraint during execution.",
        "business_risk": "Late completion risks breaching customer SLAs and may cascade into further delays for orders waiting on this one.",
        "recommendation": "Investigate the root delay cause for this order and implement escalation triggers for orders approaching the scheduled date threshold.",
    },
    "DELAY_FLAG": {
        "root_cause": "A delay flag was explicitly set on this delivery, confirming a registered deviation from the planned schedule.",
        "business_risk": "Confirmed schedule overrun may trigger SLA breach penalties and affect downstream delivery commitments.",
        "recommendation": "Ensure the delay is formally documented with a reason code and confirm a recovery plan is active for this order.",
    },
    "PLANT_MISMATCH": {
        "root_cause": "Movement was processed by plant {plant} which does not match the assigned production plant, indicating an unintended organisational unit handled this order.",
        "business_risk": "Cross-plant execution without authorisation can cause cost allocation errors and compliance issues in financial reporting.",
        "recommendation": "Review the plant assignment for this order and engage the master data team to validate plant configuration.",
    },
    "DEFAULT": {
        "root_cause": "A compliance deviation was detected on this order that requires investigation by the process owner.",
        "business_risk": "Potential compliance or operational impact depending on the criticality of the violated rule.",
        "recommendation": "Review the order details, document findings, and engage the responsible process owner for corrective action.",
    },
}


def _parse_flow_location(order: dict) -> tuple[str, str]:
    """Extract FROM/TO locations from the actual flow step as a metadata fallback.

    Handles two formats produced by the activity template:
      - "{KEY} from {CHANGED_FROM} to {CHANGED_TO}"  → "plant movement from de06 to lu05"
      - "{CHANGED_FROM} -> {CHANGED_TO}"              → "Gb02 -> 0040116433"
    """
    steps = order.get("Actual_Flow", [])
    if not steps:
        return "", ""
    step = steps[0]
    # Format: "... from X to Y"
    import re
    m = re.search(r"\bfrom\s+(\S+)\s+to\s+(\S+)", step, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    # Format: "X -> Y"
    if " -> " in step:
        parts = step.split(" -> ", 1)
        return parts[0].strip(), parts[1].strip()
    return "", ""


def _clean_meta(v) -> str | None:
    """Return None for null-like values (None, 'None', 'nan', 'null', '')."""
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in ("none", "nan", "null", "") else s


def _extract_facts(order: dict) -> dict:
    """Pull real values from order metadata for prompt and fallback substitution.

    Metadata is populated via extra_cols in schema_detector._merge_known_extra_cols.
    If metadata is still missing values, parse from the activity step as backup.
    """
    meta = order.get("metadata", {})
    flow_from, flow_to = _parse_flow_location(order)

    actual_source = (
        _clean_meta(meta.get("CHANGED_FROM")) or
        _clean_meta(meta.get("actual_source")) or
        flow_from or
        None
    )
    optimal_source = (
        _clean_meta(meta.get("OPTIMAL_SOURCE_LOCATION")) or
        _clean_meta(meta.get("optimal_source")) or
        None
    )

    # Case-insensitive comparison — "nl03" and "NL03" are the same location
    locations_differ = bool(
        actual_source and optimal_source
        and actual_source.strip().lower() != optimal_source.strip().lower()
    )

    return {
        "actual_source": actual_source or "unknown source",
        "optimal_source": optimal_source or "designated source",
        "actual_date": (
            _clean_meta(meta.get("WADAT_IST")) or
            _clean_meta(meta.get("actual_date")) or
            "unknown"
        ),
        "scheduled_date": (
            _clean_meta(meta.get("EINDT")) or
            _clean_meta(meta.get("scheduled_date")) or
            "unknown"
        ),
        "delay_flag": _clean_meta(meta.get("DD_FLAG")) or "not set",
        "plant": _clean_meta(meta.get("WERKS")) or "unknown",
        "destination": flow_to or "destination",
        "has_real_locations": locations_differ,
    }


def _build_prompt(order: dict, facts: dict) -> str:
    deviations = order.get("Deviations", [])
    primary = min(deviations, key=lambda d: _SEVERITY_RANK.get(d.get("severity", "LOW"), 99))
    primary_type = primary.get("rule_id") or primary.get("type", "")

    actual_flow = order.get("Actual_Flow", [])
    movement = actual_flow[0] if actual_flow else "no movement recorded"

    has_delay = any(d.get("type") == "DELAYED" for d in deviations)
    has_delay_flag = any(d.get("type") == "DELAY_FLAG" for d in deviations)

    # Build a plain-English description of what happened, using real values
    situation_parts = []
    if facts["has_real_locations"]:
        situation_parts.append(
            f"Movement went from {facts['actual_source']} to {facts['destination']}, "
            f"but the required source was {facts['optimal_source']}."
        )
    if has_delay and facts["actual_date"] != "unknown" and facts["scheduled_date"] != "unknown":
        situation_parts.append(
            f"Actual date {facts['actual_date']} was later than scheduled {facts['scheduled_date']}."
        )
    elif has_delay_flag:
        situation_parts.append("A delay flag is set on this delivery.")

    situation = " ".join(situation_parts) or f"Deviation type: {primary_type}."

    # Only reference specific locations when they're known AND genuinely different
    if facts["has_real_locations"]:
        actual_ref  = facts["actual_source"]
        optimal_ref = facts["optimal_source"]
        src_context = (
            f"Important: {actual_ref} is the WRONG source that was used. "
            f"{optimal_ref} is the CORRECT source that should have been used."
        )

        # When there are secondary deviations (delay/flag), broaden the field hints
        has_timing = has_delay or has_delay_flag
        if has_timing:
            timing_label = (
                f"actual date {facts['actual_date']} vs scheduled {facts['scheduled_date']}"
                if has_delay and facts["actual_date"] != "unknown" and facts["scheduled_date"] != "unknown"
                else "a registered delay flag"
            )
            field_hint = (
                f'"root_cause": "one sentence: why {actual_ref} was used instead of {optimal_ref} AND why there was {timing_label}",'
                f'\n  "business_risk": "one sentence: combined cost/service impact of wrong source ({actual_ref} instead of {optimal_ref}) and the delivery delay",'
                f'\n  "recommendation": "one sentence: enforce {optimal_ref} as source and address the root cause of the delivery delay to prevent recurrence"'
            )
        else:
            field_hint = (
                f'"root_cause": "one sentence: why was {actual_ref} used as the source instead of {optimal_ref}",'
                f'\n  "business_risk": "one sentence: cost or service impact of using {actual_ref} instead of {optimal_ref}",'
                f'\n  "recommendation": "one sentence: how to prevent {actual_ref} being used again; enforce {optimal_ref}"'
            )
    else:
        # No distinct source vs optimal — build a deviation-generic prompt
        actual_ref   = facts["actual_source"] if facts["actual_source"] not in ("unknown source",) else "the actual source"
        src_context  = "Focus on the deviation type and timing rather than specific location codes."
        dev_types    = ", ".join({d.get("rule_id") or d.get("type", "") for d in deviations if d.get("rule_id") or d.get("type")})
        order_num    = order.get("Order_Number")
        field_hint   = (
            f'"root_cause": "one sentence: what caused this {dev_types} deviation on order {order_num}",'
            f'\n  "business_risk": "one sentence: operational or cost impact of this deviation",'
            f'\n  "recommendation": "one sentence: concrete corrective action to prevent recurrence"'
        )

    return f"""Analyze this logistics compliance issue and return a JSON object.

Order {order.get("Order_Number")}: {situation}

Return this JSON:
{{
  {field_hint}
}}

{src_context}"""


def generate_contextual_rca(order: dict) -> dict:
    """
    Generate AI root cause analysis using real order values.
    Falls back to enriched templates (with real values substituted) if AI fails.
    """
    deviations = order.get("Deviations", [])
    if not deviations:
        return {}

    facts = _extract_facts(order)

    try:
        result = call_ai(_build_prompt(order, facts), expect_json=True)
        rc = str(result.get("root_cause", "")).strip()
        br = str(result.get("business_risk", "")).strip()
        rec = str(result.get("recommendation", "")).strip()

        if len(rc) > 25 and len(br) > 25 and len(rec) > 25:
            logger.info("Contextual RCA generated for order %s", order.get("Order_Number"))
            return {"root_cause": rc, "business_risk": br, "recommendation": rec}

        raise ValueError(f"AI output too short: rc={len(rc)}, br={len(br)}, rec={len(rec)}")

    except Exception as e:
        logger.warning("Contextual RCA AI failed (%s) — using enriched fallback", e)
        return _enriched_fallback(order, facts)


def _enriched_fallback(order: dict, facts: dict) -> dict:
    """Templates with real values substituted in — order-specific even without AI."""
    deviations = order.get("Deviations", [])
    dev_types = {d.get("type") for d in deviations}
    primary = min(deviations, key=lambda d: _SEVERITY_RANK.get(d.get("severity", "LOW"), 99))
    key = primary.get("rule_id") or primary.get("type") or "DEFAULT"
    tmpl = _FALLBACK.get(key) or _FALLBACK["DEFAULT"]

    has_delay_secondary = (
        ("DELAYED" in dev_types or "DELAY_FLAG" in dev_types)
        and key not in ("DELAYED", "DELAY_FLAG")
    )

    try:
        rc  = tmpl["root_cause"].format(**facts)
        br  = tmpl["business_risk"].format(**facts)
        rec = tmpl["recommendation"].format(**facts)
    except KeyError:
        rc  = tmpl["root_cause"]
        br  = tmpl["business_risk"]
        rec = tmpl["recommendation"]

    # Append delay context when it's a secondary deviation not covered by the primary template
    if has_delay_secondary:
        rc  += " Additionally, a delivery delay was registered on this order."
        br  += " The concurrent delivery delay compounds the service risk."
        rec += " Also investigate and resolve the cause of the delivery delay."

    return {"root_cause": rc, "business_risk": br, "recommendation": rec}

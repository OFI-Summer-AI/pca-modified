"""Rule-based RCA — multiple template variants per deviation type, rotated by order index."""

_TEMPLATES = {
    "MISSING_CRITICAL_STEP": [
        {
            "root_cause": "A mandatory process step was absent from the recorded flow, indicating it was skipped or not captured in the system.",
            "business_risk": "Direct compliance gap with audit exposure. Skipped steps may signal unauthorized shortcuts or system capture failures.",
            "recommendation": "Confirm whether the step physically occurred. If yes, enforce retroactive system capture. If not, trigger an immediate corrective action review.",
        },
        {
            "root_cause": "The process log is missing a critical step that must be present for compliance. This points to either a process bypass or a recording failure.",
            "business_risk": "Missing evidence of a critical control creates an audit finding. Financial or regulatory consequences may follow if left unresolved.",
            "recommendation": "Cross-check physical records against the system log. Engage the process owner to close the gap and strengthen entry controls at this step.",
        },
        {
            "root_cause": "A required step in the standard flow was not executed or not registered, breaking the control chain for this order.",
            "business_risk": "Control chain failure — downstream steps that depend on this one may have proceeded without the necessary pre-conditions being met.",
            "recommendation": "Place the order under review hold. Validate all downstream steps to ensure they were executed on valid grounds before releasing.",
        },
    ],
    "OUT_OF_SEQUENCE": [
        {
            "root_cause": "Process steps were executed or recorded in a different order than the standard flow, suggesting a process breakdown or manual override.",
            "business_risk": "Downstream dependencies may be compromised — approvals, quality checks, or financial postings may have proceeded without required prior steps.",
            "recommendation": "Review the order timeline and identify where the sequence diverged. Assess impact on downstream steps and retrain the team on standard process sequence.",
        },
        {
            "root_cause": "The actual execution order of process steps does not match the approved standard flow. This is likely a result of manual process shortcuts.",
            "business_risk": "Sequence violations undermine internal controls. Steps executed prematurely may result in incorrect financial entries or unapproved commitments.",
            "recommendation": "Map the actual sequence against the standard and identify the trigger for the deviation. Update training and enforce system-level sequencing controls.",
        },
        {
            "root_cause": "Steps were completed out of order, possibly due to urgency pressure, user error, or a gap in system workflow enforcement.",
            "business_risk": "Process integrity is at risk. Out-of-sequence execution can lead to duplicate processing, approval bypasses, or missed quality gates.",
            "recommendation": "Conduct a root cause interview with the process executor. Implement system controls that block out-of-sequence step entry where possible.",
        },
    ],
    "DUPLICATE_STEP": [
        {
            "root_cause": "The same process step was recorded more than once, likely due to manual re-entry, system retry, or an integration duplication issue.",
            "business_risk": "Duplicate entries risk inflating KPIs and creating duplicate financial postings such as double-invoicing or double-counting in reports.",
            "recommendation": "Verify whether the step genuinely occurred multiple times or is a recording error. Audit affected financial postings and add deduplication controls.",
        },
        {
            "root_cause": "A repeated activity log entry was detected for the same step. This may stem from a system timeout retry or a user submitting the same action twice.",
            "business_risk": "Data integrity risk — duplicated process steps may cause incorrect status reporting and create inconsistencies in audit trails.",
            "recommendation": "Investigate the system logs for the time of duplication. Apply idempotency controls to prevent retry-based duplicates and validate the final process state.",
        },
    ],
    "WRONG_SOURCE": [
        {
            "root_cause": "Material was moved from a non-optimal source location, deviating from the system-recommended supply point.",
            "business_risk": "Non-optimal sourcing increases logistics cost, extends transit time, and may indicate routing decisions made outside approved guidelines.",
            "recommendation": "Review the sourcing decision for this delivery. Validate whether an exception was approved or enforce the optimal source location in the planning system.",
        },
        {
            "root_cause": "The actual source location (CHANGED_FROM) did not match the designated optimal source, suggesting either a stock availability issue or a manual override.",
            "business_risk": "Repeated non-optimal sourcing inflates freight costs and distorts supply chain performance metrics.",
            "recommendation": "Investigate whether the optimal source had sufficient stock at the time of movement. If stock was unavailable, update the source strategy; if not, enforce routing compliance.",
        },
        {
            "root_cause": "The delivery was fulfilled from an alternative location rather than the planned optimal source, creating a sourcing deviation.",
            "business_risk": "Unplanned sourcing deviations can cause downstream imbalances in inventory levels across locations.",
            "recommendation": "Align with the supply planning team to confirm whether alternative sourcing was authorised. Implement system controls to flag non-optimal source selections at the time of execution.",
        },
    ],
    "PLANT_MISMATCH": [
        {
            "root_cause": "The executing plant (WERKS) does not match the assigned production plant, indicating the movement was processed by an unintended organisational unit.",
            "business_risk": "Cross-plant execution without proper authorisation can cause cost allocation errors and compliance issues in financial reporting.",
            "recommendation": "Verify whether the movement was intentionally rerouted or if a data entry error occurred. Ensure plant assignment rules are enforced during order creation.",
        },
        {
            "root_cause": "A mismatch between the movement plant and the production plant was detected, suggesting the order was processed outside its assigned plant structure.",
            "business_risk": "Plant mismatches can lead to incorrect material valuation, MRP disruptions, and inaccurate capacity planning data.",
            "recommendation": "Review the plant assignment for this material and correct the routing if required. Engage the master data team to validate plant configuration.",
        },
    ],
    "DOMAIN_RULE_VIOLATION": [
        {
            "root_cause": "A domain-specific compliance rule was violated, indicating a deviation from the expected operational standard for this process area.",
            "business_risk": "Operational inefficiency, increased cost exposure, or a compliance breach depending on the criticality of the rule violated.",
            "recommendation": "Review the specific rule violation and escalate to the process owner. Determine whether a formal exception was approved or corrective action is required.",
        },
        {
            "root_cause": "The order breached a rule defined for this business domain. This may reflect a data entry error, a system gap, or an intentional override without documentation.",
            "business_risk": "Rule violations increase audit risk and may indicate systemic process issues if the same rule is violated across multiple orders.",
            "recommendation": "Document the violation with supporting evidence. Engage the domain owner to assess whether the rule definition needs updating or the process needs reinforcement.",
        },
        {
            "root_cause": "Process data did not conform to an expected business constraint, triggering a domain rule violation flag on this order.",
            "business_risk": "Non-conformance with domain rules can signal process drift — repeated violations may indicate that the standard is not being enforced at the operational level.",
            "recommendation": "Cross-reference this violation with other orders to assess frequency. If systemic, consider a process improvement initiative rather than individual correction only.",
        },
    ],
    "DELAYED": [
        {
            "root_cause": "The actual completion time exceeded the planned schedule, indicating a bottleneck or resource constraint during execution.",
            "business_risk": "Delayed orders risk breaching customer SLAs, triggering penalty clauses, and causing downstream queue buildup for dependent processes.",
            "recommendation": "Identify the specific bottleneck in the timeline. Review capacity planning and scheduling accuracy for this process segment and flag for SLA reporting.",
        },
        {
            "root_cause": "Process execution took significantly longer than the expected lead time, pointing to either resource unavailability or an unresolved dependency.",
            "business_risk": "Late completions affect customer satisfaction and may cascade into further delays for orders waiting on this one as a dependency.",
            "recommendation": "Investigate whether the delay was planned (e.g., approved exception) or unplanned. Update forecasting models and implement escalation triggers for threshold breaches.",
        },
        {
            "root_cause": "The order's cycle time exceeded the defined threshold, suggesting inefficiencies in handoff, approval wait times, or processing capacity.",
            "business_risk": "Repeated delays in this process segment indicate a systemic issue that will continue to affect throughput and service levels if not addressed.",
            "recommendation": "Analyze the delay pattern across similar orders. Prioritize process improvements at the identified bottleneck step and set up automated alerts for threshold breaches.",
        },
    ],
    "DELAY_FLAG": [
        {
            "root_cause": "A delay flag was explicitly set on this order, confirming a known and registered deviation from the planned schedule.",
            "business_risk": "Confirmed schedule overrun with downstream impact on dependent processes or customer delivery windows.",
            "recommendation": "Ensure the delay is formally documented with a reason code. Verify a recovery plan is active and escalate if the delay exceeds acceptable thresholds.",
        },
        {
            "root_cause": "The system recorded a delay flag against this order, indicating that the planned completion date was missed and the deviation was acknowledged.",
            "business_risk": "Flagged delays require management attention. If not resolved promptly, they can trigger SLA breach penalties or affect customer confidence.",
            "recommendation": "Review the reason for the flag and confirm it aligns with the actual timeline. Ensure the order is reprioritized and the delay does not propagate to linked orders.",
        },
    ],
}

_DEFAULT_TEMPLATES = [
    {
        "root_cause": "A process deviation was detected that requires investigation by the process owner.",
        "business_risk": "Potential compliance or operational impact depending on process criticality.",
        "recommendation": "Review the order details, document findings, and engage the responsible process owner for corrective action.",
    },
]

_SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def enrich_with_rca(orders: list[dict]) -> list[dict]:
    """Add root_cause, business_risk, recommendation to each order from template pools."""
    for i, order in enumerate(orders):
        deviations = order.get("Deviations", [])
        if not deviations:
            continue

        primary = min(deviations, key=lambda d: _SEVERITY_RANK.get(d.get("severity", "LOW"), 99))
        dev_type = primary.get("type", "")
        rule_id = primary.get("rule_id", "")

        pool = _TEMPLATES.get(rule_id) or _TEMPLATES.get(dev_type) or _DEFAULT_TEMPLATES
        template = pool[i % len(pool)]

        order["root_cause"] = template["root_cause"]
        order["business_risk"] = template["business_risk"]
        order["recommendation"] = template["recommendation"]

    return orders

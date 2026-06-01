import logging

from .ai_client import call_ai

logger = logging.getLogger(__name__)


def generate_summary(summary: dict, domain: str, top_orders: list) -> str:
    """Generate an AI executive narrative for the analysis results."""
    total = summary.get("total_orders", 0)
    blocked = summary.get("blocked", 0)
    alert = summary.get("alert", 0)
    passed = summary.get("pass", 0)
    avg_score = summary.get("avg_deviation_score", 0)

    top_issues = []
    for o in top_orders[:5]:
        devs = [d.get("type", "") for d in o.get("Deviations", [])]
        top_issues.append(f"Order {o.get('Order_Number')}: {', '.join(devs) or 'no deviations'}")

    prompt = f"""Write a 3-sentence executive summary for a {domain} compliance analysis.

Data:
- Total orders: {total}
- BLOCKED: {blocked} ({round(blocked/total*100,1) if total else 0}%)
- ALERT: {alert} ({round(alert/total*100,1) if total else 0}%)
- PASS: {passed} ({round(passed/total*100,1) if total else 0}%)
- Average deviation score: {avg_score}

Top issues: {'; '.join(top_issues)}

Write 3 professional sentences covering: what was analyzed, the main risk finding, and the recommended action. No bullet points."""

    try:
        return call_ai(prompt, expect_json=False)
    except Exception as e:
        logger.warning("Executive summary AI failed: %s", e)
        high_risk_pct = round((blocked + alert) / total * 100, 1) if total else 0
        return (
            f"Analysis of {total:,} {domain} orders identified {blocked:,} blocked and {alert:,} alert cases, "
            f"representing {high_risk_pct}% of total volume. "
            f"The average deviation score of {avg_score} indicates {'significant' if avg_score > 20 else 'moderate'} compliance risk. "
            f"Immediate review of blocked orders is recommended to address critical process gaps."
        )

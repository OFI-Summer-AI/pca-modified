"""Cluster Insights — AI pattern analysis over aggregated deviation data."""
import logging
from collections import Counter

from .ai_client import call_ai

logger = logging.getLogger(__name__)


def _aggregate(orders: list) -> dict:
    """Pre-aggregate stats from the orders list — no AI, fast."""
    total = len(orders)
    non_pass = [o for o in orders if o.get("Process_Status") in ("BLOCKED", "ALERT")]

    dev_type_counts: Counter = Counter()
    source_violations: Counter = Counter()
    rule_violations: Counter = Counter()

    for o in non_pass:
        for d in o.get("Deviations", []):
            dev_type_counts[d.get("type", "UNKNOWN")] += 1
            rid = d.get("rule_id")
            if rid:
                rule_violations[rid] += 1

        meta = o.get("metadata", {})
        src = meta.get("CHANGED_FROM", "")
        if src:
            source_violations[src] += 1

    return {
        "total": total,
        "non_pass_count": len(non_pass),
        "dev_type_counts": dict(dev_type_counts.most_common(5)),
        "top_sources": dict(source_violations.most_common(5)),
        "top_rules": dict(rule_violations.most_common(3)),
    }


def _build_prompt(stats: dict, domain: str) -> str:
    total = stats["total"]
    non_pass = stats["non_pass_count"]
    pct = round(non_pass / total * 100, 1) if total else 0

    dev_lines = "\n".join(
        f"  - {t}: {c:,} orders" for t, c in stats["dev_type_counts"].items()
    ) or "  - No deviations detected"

    source_lines = "\n".join(
        f"  - {s}: {c:,} cases" for s, c in stats["top_sources"].items()
    ) or "  - No source data"

    rule_lines = "\n".join(
        f"  - {r}: {c:,} violations" for r, c in stats["top_rules"].items()
    ) or "  - No rule violations"

    return f"""You are a supply chain analyst. Identify 3 operational patterns from this {domain} compliance dataset.

Dataset: {total:,} total orders, {non_pass:,} non-compliant ({pct}%)

Deviation types:
{dev_lines}

Top source locations with violations:
{source_lines}

Top rule violations:
{rule_lines}

Return ONLY this JSON object with exactly 3 insights:
{{
  "insights": [
    "first pattern — one sentence under 20 words referencing specific numbers",
    "second pattern — one sentence under 20 words referencing specific numbers",
    "third pattern — one sentence under 20 words referencing specific numbers"
  ]
}}

Rules:
- Each insight must reference actual numbers or location codes from the data above
- Identify patterns, not just restate numbers
- No bullet points, no markdown"""


def generate_cluster_insights(orders: list, domain: str) -> list[str]:
    """
    Generate 3 AI-identified patterns from aggregated order data.
    Returns a list of insight strings. Falls back to rule-based patterns if AI fails.
    """
    if not orders:
        return []

    stats = _aggregate(orders)

    if stats["non_pass_count"] == 0:
        return ["All orders are fully compliant — no deviation patterns detected."]

    try:
        result = call_ai(_build_prompt(stats, domain), expect_json=True)

        insights = result.get("insights", [])
        if not isinstance(insights, list):
            insights = list(result.values()) if isinstance(result, dict) else []

        insights = [str(i).strip() for i in insights if str(i).strip()][:3]

        if not insights:
            raise ValueError("Empty insights list from AI")

        logger.info("Cluster insights generated: %d patterns", len(insights))
        return insights

    except Exception as e:
        logger.warning("Cluster insights AI failed (%s) — using fallback", e)
        return _fallback_insights(stats)


def _fallback_insights(stats: dict) -> list[str]:
    """Rule-based fallback — derives patterns from aggregated counts."""
    insights = []
    total = stats["total"]
    non_pass = stats["non_pass_count"]
    pct = round(non_pass / total * 100, 1) if total else 0

    dev_counts = stats["dev_type_counts"]
    if dev_counts:
        top_type, top_count = next(iter(dev_counts.items()))
        type_pct = round(top_count / total * 100, 1)
        insights.append(
            f"{top_type.replace('_', ' ').title()} is the primary compliance gap, "
            f"affecting {top_count:,} orders ({type_pct}% of total volume)."
        )

    top_sources = stats["top_sources"]
    if top_sources:
        top_src, top_src_count = next(iter(top_sources.items()))
        insights.append(
            f"Source location {top_src} accounts for {top_src_count:,} non-compliant movements, "
            f"suggesting a routing issue at that plant."
        )

    insights.append(
        f"{non_pass:,} orders ({pct}%) require compliance review, "
        f"with {total - non_pass:,} orders fully compliant."
    )

    return insights[:3]

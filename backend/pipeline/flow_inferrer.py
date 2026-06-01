import json
import logging

from .ai_client import call_ai

logger = logging.getLogger(__name__)


def _is_single_step_dataset(top_sequences: list) -> bool:
    """
    Return True if >80% of observed sequences are single-step.
    For such datasets (e.g. logistics movements) sequence-based checks
    (MISSING_CRITICAL_STEP, OUT_OF_SEQUENCE) are meaningless and must be skipped.
    """
    if not top_sequences:
        return True
    total = sum(s["count"] for s in top_sequences)
    single = sum(s["count"] for s in top_sequences if len(s["sequence"]) == 1)
    return total > 0 and (single / total) > 0.8


def _build_prompt(top_sequences: list, step_frequencies: dict, domain: str) -> str:
    top5 = top_sequences[:5]
    freq_top = list(step_frequencies.items())[:20]

    seq_lines = "\n".join(
        f"  {i+1}. [{', '.join(repr(s) for s in seq['sequence'])}]  (count: {seq['count']})"
        for i, seq in enumerate(top5)
    )
    freq_lines = "\n".join(f"  {step!r}: {cnt}" for step, cnt in freq_top)

    return f"""You are a process analyst. Identify the standard (happy-path) flow for a {domain} process.

Top observed sequences:
{seq_lines}

Most frequent steps:
{freq_lines}

Return ONLY this JSON. Use EXACT step strings from above — do not rephrase or shorten them.

{{
  "standard_flow": ["step1", "step2", "step3"],
  "critical_steps": ["step that must always appear"],
  "domain_rules": []
}}

Rules:
- standard_flow: the ordered sequence a compliant order should follow; include 5–15 steps.
- critical_steps: 1–3 steps from standard_flow that are mandatory for compliance.
- domain_rules: always return an empty array [].
- IMPORTANT: Use ONLY step strings that appear EXACTLY in the sequences or frequency list above."""


def _validate_against_data(result: dict, step_frequencies: dict) -> dict:
    """
    Drop any AI-invented step names that don't exist in the actual data.
    A critical_step that matches nothing in the data makes every order BLOCKED.
    """
    known_steps = set(step_frequencies.keys())

    original_sf = result.get("standard_flow", [])
    original_cs = result.get("critical_steps", [])

    valid_sf = [s for s in original_sf if s in known_steps]
    valid_cs = [s for s in original_cs if s in known_steps]

    if set(original_sf) - set(valid_sf):
        logger.warning("Dropped %d invented steps from standard_flow: %s",
                       len(set(original_sf) - set(valid_sf)),
                       list(set(original_sf) - set(valid_sf))[:5])
    if set(original_cs) - set(valid_cs):
        logger.warning(
            "Dropped %d invented critical_steps (would cause 100%% BLOCKED): %s",
            len(set(original_cs) - set(valid_cs)),
            list(set(original_cs) - set(valid_cs)))

    result["standard_flow"] = valid_sf
    result["critical_steps"] = valid_cs
    return result


def infer_flow(top_sequences: list, step_frequencies: dict, domain: str) -> dict:
    """
    Infer standard flow. For single-step datasets, skip sequence checks entirely.
    """
    # Single-step dataset: sequence-based deviation checks are meaningless
    if _is_single_step_dataset(top_sequences):
        logger.info(
            "Single-step dataset detected (>80%% of orders have 1 step) — "
            "skipping sequence-based flow inference. Domain rules will drive compliance."
        )
        return {"standard_flow": [], "critical_steps": [], "domain_rules": []}

    # Multi-step dataset: use Ollama
    try:
        result = call_ai(
            _build_prompt(top_sequences, step_frequencies, domain),
            expect_json=True,
        )
        sf = result.get("standard_flow")
        if not sf or not isinstance(sf, list) or len(sf) < 2:
            raise ValueError(f"AI returned insufficient standard_flow: {sf}")

        result["standard_flow"] = [str(s) for s in sf]
        result["critical_steps"] = [str(s) for s in result.get("critical_steps") or []]
        result["domain_rules"] = []

        # Validate: drop any step name the model invented
        result = _validate_against_data(result, step_frequencies)

        if len(result["standard_flow"]) < 2:
            raise ValueError("After validation, fewer than 2 valid steps remain — using fallback")

        logger.info("Flow inferred via AI: %d steps (%d critical)",
                    len(result["standard_flow"]), len(result["critical_steps"]))
        return result

    except Exception as e:
        logger.warning("Flow inference failed: %s — using fallback", e)
        return _fallback_flow(top_sequences)


def _fallback_flow(top_sequences: list) -> dict:
    """Most common sequence, no critical steps (avoids false BLOCKED)."""
    if top_sequences:
        return {
            "standard_flow": top_sequences[0]["sequence"],
            "critical_steps": [],
            "domain_rules": [],
        }
    return {"standard_flow": [], "critical_steps": [], "domain_rules": []}

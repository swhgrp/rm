"""
AI Reasoning Layer — Claude Sonnet integration for GL anomaly analysis.

Called only when the rules engine returns 1+ flags. Adds contextual reasoning,
severity adjustments, and recommended actions to each flag.
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

BATCH_SIZE = 25

SYSTEM_PROMPT = """You are an expert restaurant accountant reviewing flagged GL transactions for a multi-location hospitality group.
You receive a list of automatically detected anomalies. Your job is to:
1. Assess the severity of each flag given restaurant industry context
2. Explain in plain English what is wrong and why it matters operationally or financially
3. Suggest a specific recommended action for the accounting team

Respond ONLY with a valid JSON array. No preamble, no markdown, no explanation outside the JSON.
Each element: {"flag_index": N, "severity": "info|warning|critical", "ai_reasoning": "...", "ai_confidence": "high|medium|low", "recommended_action": "..."}"""


def analyze_flags_with_ai(
    flags: list[dict],
    area_id: int,
    area_name: str,
    period_label: str,
) -> list[dict]:
    """
    Send flagged items to Claude Sonnet for contextual analysis.

    Processes in batches of 20 flags per API call. Merges AI fields back into
    the flag dicts. If the AI call fails, returns flags unchanged.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping AI analysis")
        return flags

    model = os.environ.get("GL_REVIEW_AI_MODEL", "claude-sonnet-4-6")

    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic package not installed — skipping AI analysis")
        return flags

    client = anthropic.Anthropic(api_key=api_key, timeout=120.0, max_retries=1)

    # Process in batches
    for batch_start in range(0, len(flags), BATCH_SIZE):
        batch = flags[batch_start:batch_start + BATCH_SIZE]
        batch_offset = batch_start  # so we can map flag_index back

        prompt = _build_prompt(batch, area_id, area_name, period_label, offset=batch_offset)

        try:
            logger.info(f"AI analysis: sending batch starting at {batch_start} ({len(batch)} flags) to {model}")
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text.strip()
            ai_results = _parse_response(response_text)

            if ai_results:
                _merge_ai_results(flags, ai_results, batch_offset)
                logger.info(f"AI analysis complete for batch starting at {batch_start}: {len(ai_results)} results")
            else:
                logger.warning(f"AI returned no parseable results for batch starting at {batch_start}")

        except Exception:
            logger.exception(f"AI analysis failed for batch starting at {batch_start}, using rules-engine defaults")

    return flags


def _build_prompt(
    batch: list[dict],
    area_id: int,
    area_name: str,
    period_label: str,
    offset: int = 0,
) -> str:
    """Build the user prompt containing the flagged items."""
    lines = [
        f"Location: {area_name} (area_id={area_id})",
        f"Review period: {period_label}",
        f"Number of flags: {len(batch)}",
        "",
        "Flagged items:",
    ]

    for i, flag in enumerate(batch):
        idx = offset + i + 1  # 1-based
        parts = [
            f"  Flag #{idx}:",
            f"    Type: {flag.get('flag_type', 'UNKNOWN')}",
            f"    Title: {flag.get('title', '')}",
            f"    Detail: {flag.get('detail', '')}",
        ]
        if flag.get('flagged_value') is not None:
            parts.append(f"    Flagged Value: ${flag['flagged_value']:,.2f}")
        if flag.get('expected_range_low') is not None and flag.get('expected_range_high') is not None:
            parts.append(f"    Expected Range: ${flag['expected_range_low']:,.2f} — ${flag['expected_range_high']:,.2f}")
        lines.extend(parts)
        lines.append("")

    return "\n".join(lines)


def _parse_response(text: str) -> Optional[list[dict]]:
    """Parse the AI JSON response. Returns None if unparseable."""
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        logger.warning("AI response is not a JSON array")
        return None
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse AI response as JSON: {e}")
        return None


def _merge_ai_results(flags: list[dict], ai_results: list[dict], batch_offset: int):
    """Merge AI analysis back into flag dicts by flag_index."""
    for result in ai_results:
        idx = result.get("flag_index")
        if idx is None:
            continue

        # flag_index is 1-based
        list_idx = idx - 1
        if 0 <= list_idx < len(flags):
            flag = flags[list_idx]
            if result.get("severity") in ("info", "warning", "critical"):
                flag["severity"] = result["severity"]
            if result.get("ai_reasoning"):
                flag["ai_reasoning"] = result["ai_reasoning"]
            if result.get("ai_confidence") in ("high", "medium", "low"):
                flag["ai_confidence"] = result["ai_confidence"]
            if result.get("recommended_action"):
                # Append recommended action to ai_reasoning
                reasoning = flag.get("ai_reasoning", "")
                flag["ai_reasoning"] = f"{reasoning}\n\nRecommended action: {result['recommended_action']}".strip()

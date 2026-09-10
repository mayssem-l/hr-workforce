import logging
import re

from django.conf import settings

from core.services.llm_explanations import generate_manager_summary


logger = logging.getLogger(__name__)

MAX_MANAGER_SUMMARY_CHARACTERS = 400
NUMBER_PATTERN = re.compile(r"(?<![\w])[-+]?\d+(?:\.\d+)?%?")


def _validated_manager_summary(summary, explanation):
    if not isinstance(summary, str):
        return None

    summary = summary.strip()
    if (
        not summary
        or len(summary) > MAX_MANAGER_SUMMARY_CHARACTERS
        or any(marker in summary for marker in ("\r", "\n", "<", ">", "```"))
    ):
        return None

    deterministic_text = " ".join(
        (
            str(explanation["category"]),
            str(explanation["label"]),
            *(str(member) for member in explanation["team"]),
            *(str(strength) for strength in explanation["strengths"]),
            *(str(tradeoff) for tradeoff in explanation["tradeoffs"]),
        )
    )
    allowed_numbers = set(NUMBER_PATTERN.findall(deterministic_text))
    returned_numbers = set(NUMBER_PATTERN.findall(summary))
    if not returned_numbers <= allowed_numbers:
        return None
    return summary


def build_optional_manager_summaries(explanations):
    """Optionally enrich deterministic evidence without changing it."""

    if not settings.GEMINI_MANAGER_SUMMARIES_ENABLED:
        return {
            "state": "disabled",
            "message": (
                "Optional Gemini summaries are off. The deterministic "
                "strengths, trade-offs, and comparisons remain complete."
            ),
            "items": (),
        }

    items = []
    has_available = False
    has_unavailable = False
    for explanation in explanations:
        summary = None
        try:
            generated_summary = generate_manager_summary(
                explanation,
                timeout_ms=settings.GEMINI_MANAGER_SUMMARY_TIMEOUT_MS,
            )
            summary = _validated_manager_summary(
                generated_summary,
                explanation,
            )
        except Exception:
            logger.warning(
                "Optional Gemini summary unavailable for recommendation "
                "category %s.",
                explanation.get("category", "unavailable"),
            )

        if summary is None:
            state = "unavailable"
            has_unavailable = True
        else:
            state = "available"
            has_available = True
        items.append(
            {
                "category": explanation["category"],
                "label": explanation["label"],
                "state": state,
                "summary": summary,
                "service_explanation": explanation,
            }
        )

    if has_available and has_unavailable:
        state = "partial"
        message = (
            "Some optional Gemini summaries are unavailable. Deterministic "
            "evidence remains authoritative for every strategy."
        )
    elif has_available:
        state = "available"
        message = (
            "Optional Gemini wording is available. Deterministic strengths, "
            "trade-offs, and comparisons remain authoritative."
        )
    else:
        state = "unavailable"
        message = (
            "Optional Gemini summaries are unavailable. The complete "
            "deterministic evidence remains available below."
        )
    return {
        "state": state,
        "message": message,
        "items": tuple(items),
    }

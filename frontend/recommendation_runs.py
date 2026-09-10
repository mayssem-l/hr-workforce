"""Ephemeral server-side store for one generated recommendation result.

Reviewing a staffing handoff must not invalidate the originating
recommendation, and cancelling must return to the exact same result
without rerunning the expensive pipeline. Results are therefore kept in
Django's configured cache (the same backend already used for one-time
submission tokens) under an unguessable run identifier, bound to the
project and user that generated them, with a short TTL.

This is not recommendation history: entries expire automatically, are
deleted after a successful staffing confirmation, and are never trusted
without revalidating the current input snapshot and references first.
No model or migration is involved.
"""

import logging
import secrets

from django.core.cache import cache


logger = logging.getLogger(__name__)

RECOMMENDATION_RUN_CACHE_PREFIX = "recommendation-run"
RECOMMENDATION_RUN_TTL_SECONDS = 60 * 60


def issue_recommendation_run_id():
    return secrets.token_urlsafe(24)


def _cache_key(run_id):
    return f"{RECOMMENDATION_RUN_CACHE_PREFIX}:{run_id}"


def store_recommendation_run(
    run_id,
    *,
    project_id,
    user_id,
    input_signature,
    pipeline_result,
    manager_summaries,
):
    try:
        cache.set(
            _cache_key(run_id),
            {
                "project_id": project_id,
                "user_id": user_id,
                "input_signature": input_signature,
                "pipeline_result": pipeline_result,
                "manager_summaries": manager_summaries,
            },
            timeout=RECOMMENDATION_RUN_TTL_SECONDS,
        )
    except Exception:
        logger.warning(
            "Recommendation run %s could not be cached.", run_id
        )


def fetch_recommendation_run(run_id):
    try:
        record = cache.get(_cache_key(run_id))
    except Exception:
        logger.warning(
            "Recommendation run %s could not be read.", run_id
        )
        return None
    return record if isinstance(record, dict) else None


def invalidate_recommendation_run(run_id):
    if not run_id:
        return
    try:
        cache.delete(_cache_key(run_id))
    except Exception:
        logger.warning(
            "Recommendation run %s could not be invalidated.", run_id
        )

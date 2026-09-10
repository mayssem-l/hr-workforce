import hashlib
import secrets

from django.core import signing
from django.core.cache import cache


RECOMMENDATION_TOKEN_MAX_AGE_SECONDS = 60 * 60
RECOMMENDATION_TOKEN_SALT = "frontend.recommendation-generation"
RECOMMENDATION_SUBMISSION_CACHE_PREFIX = "recommendation-submission"


class InvalidRecommendationSubmissionToken(ValueError):
    """Raised when a generation token is invalid for the current request."""


def issue_recommendation_submission_token(*, project_id, user_id):
    payload = {
        "project_id": project_id,
        "user_id": user_id,
        "nonce": secrets.token_urlsafe(18),
    }
    return signing.dumps(
        payload,
        salt=RECOMMENDATION_TOKEN_SALT,
        compress=True,
    )


def validate_recommendation_submission_token(
    token,
    *,
    project_id,
    user_id,
):
    try:
        payload = signing.loads(
            token,
            salt=RECOMMENDATION_TOKEN_SALT,
            max_age=RECOMMENDATION_TOKEN_MAX_AGE_SECONDS,
        )
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise InvalidRecommendationSubmissionToken from exc

    if not isinstance(payload, dict):
        raise InvalidRecommendationSubmissionToken
    if payload.get("project_id") != project_id:
        raise InvalidRecommendationSubmissionToken
    if payload.get("user_id") != user_id:
        raise InvalidRecommendationSubmissionToken
    if not isinstance(payload.get("nonce"), str) or not payload["nonce"]:
        raise InvalidRecommendationSubmissionToken
    return token


def claim_recommendation_submission(token):
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cache_key = f"{RECOMMENDATION_SUBMISSION_CACHE_PREFIX}:{token_digest}"
    return cache.add(
        cache_key,
        True,
        timeout=RECOMMENDATION_TOKEN_MAX_AGE_SECONDS,
    )

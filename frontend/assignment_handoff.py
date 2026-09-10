import hashlib
import secrets

from django.core import signing
from django.core.cache import cache


HANDOFF_TOKEN_MAX_AGE_SECONDS = 60 * 60
HANDOFF_TOKEN_SALT = "frontend.assignment-handoff"
HANDOFF_SUBMISSION_CACHE_PREFIX = "assignment-handoff"


class InvalidHandoffToken(ValueError):
    """Raised when a confirmation token is invalid for the request."""


class StaleHandoffToken(ValueError):
    """Raised when inputs changed after the review was prepared."""


def issue_handoff_token(
    *,
    project_id,
    user_id,
    category,
    input_signature=None,
):
    payload = {
        "project_id": project_id,
        "user_id": user_id,
        "category": category,
        "nonce": secrets.token_urlsafe(18),
    }
    if input_signature is not None:
        payload["input_signature"] = input_signature
    return signing.dumps(
        payload,
        salt=HANDOFF_TOKEN_SALT,
        compress=True,
    )


def validate_handoff_token(
    token,
    *,
    project_id,
    user_id,
    category,
    input_signature=None,
):
    try:
        payload = signing.loads(
            token,
            salt=HANDOFF_TOKEN_SALT,
            max_age=HANDOFF_TOKEN_MAX_AGE_SECONDS,
        )
    except (signing.BadSignature, signing.SignatureExpired) as exc:
        raise InvalidHandoffToken from exc

    if not isinstance(payload, dict):
        raise InvalidHandoffToken
    if payload.get("project_id") != project_id:
        raise InvalidHandoffToken
    if payload.get("user_id") != user_id:
        raise InvalidHandoffToken
    if payload.get("category") != category:
        raise InvalidHandoffToken
    if not isinstance(payload.get("nonce"), str) or not payload["nonce"]:
        raise InvalidHandoffToken
    rendered_signature = payload.get("input_signature")
    if (
        input_signature is not None
        and rendered_signature is not None
        and rendered_signature != input_signature
    ):
        raise StaleHandoffToken
    return token


def claim_handoff_submission(token):
    token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    cache_key = f"{HANDOFF_SUBMISSION_CACHE_PREFIX}:{token_digest}"
    return cache.add(
        cache_key,
        True,
        timeout=HANDOFF_TOKEN_MAX_AGE_SECONDS,
    )

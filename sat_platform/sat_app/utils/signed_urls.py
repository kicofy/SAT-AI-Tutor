"""Helpers for short-lived signed URLs (e.g., figure images)."""

from __future__ import annotations

from typing import Any, Dict

from itsdangerous import BadSignature, BadTimeSignature, URLSafeTimedSerializer


def _serializer(secret: str, salt: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key=secret, salt=salt)


def sign_payload(secret: str, salt: str, payload: Dict[str, Any]) -> str:
    """Return a signed token for the payload."""

    return _serializer(secret, salt).dumps(payload)


def verify_payload(token: str, secret: str, salt: str, *, max_age: int) -> Dict[str, Any]:
    """Verify and return the payload or raise a signature error."""

    try:
        return _serializer(secret, salt).loads(token, max_age=max_age)
    except (BadSignature, BadTimeSignature) as exc:
        raise exc


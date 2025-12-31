"""Password reset token issuance and confirmation."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import current_app, render_template, request
from werkzeug.exceptions import BadRequest

from ..extensions import db
from ..models import User
from ..utils import hash_password
from . import mail_service

RESET_TOKEN_TTL_MINUTES = 30
RESET_RESEND_INTERVAL_SECONDS = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _find_user(identifier: str) -> User | None:
    normalized = identifier.strip()
    if not normalized:
        raise BadRequest("reset_identifier_missing")
    query = User.query
    if "@" in normalized:
        return query.filter_by(email=normalized.lower()).first()
    return query.filter(db.func.lower(User.username) == normalized.lower()).first()


def request_password_reset(identifier: str) -> None:
    """Issue a password reset token and email, if the user exists."""

    try:
        user = _find_user(identifier)
    except BadRequest:
        raise

    if not user:
        return

    now = _now()
    last_request = _coerce_aware(user.password_reset_requested_at)
    if last_request and (now - last_request).total_seconds() < RESET_RESEND_INTERVAL_SECONDS:
        raise BadRequest("reset_recent")

    raw_token = secrets.token_urlsafe(48)
    user.password_reset_token = raw_token
    user.password_reset_requested_at = now
    user.password_reset_expires_at = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    db.session.add(user)
    db.session.commit()

    _send_reset_email(user, raw_token)


def confirm_password_reset(token: str, new_password: str) -> User:
    if not token:
        raise BadRequest("reset_token_missing")
    user = User.query.filter_by(password_reset_token=token).first()
    if not user:
        raise BadRequest("reset_token_invalid")
    expires_at = _coerce_aware(user.password_reset_expires_at)
    if not expires_at or _now() > expires_at:
        raise BadRequest("reset_token_expired")

    user.password_hash = hash_password(new_password)
    user.password_reset_token = None
    user.password_reset_requested_at = None
    user.password_reset_expires_at = None

    db.session.add(user)
    db.session.commit()
    return user


def _current_origin() -> str | None:
    """Best-effort origin from the incoming request (honor proxies)."""
    try:
        # Prefer proxy headers when present
        proto = request.headers.get("X-Forwarded-Proto") or request.scheme
        host = request.headers.get("X-Forwarded-Host") or request.host
        if not host:
            return None
        return f"{proto}://{host}".rstrip("/")
    except Exception:
        return None


def _build_reset_url(token: str) -> str:
    cfg_url = (current_app.config.get("PASSWORD_RESET_URL") or "").strip()
    origin = _current_origin()
    default_path = "/auth/reset-password"
    if cfg_url:
        # If config already includes scheme, trust it; otherwise treat as path.
        if cfg_url.startswith(("http://", "https://")):
            base_url = cfg_url
        else:
            base_url = f"{origin or ''}/{cfg_url.lstrip('/')}" if origin else f"http://localhost:3000{default_path}"
    else:
        base_url = f"{origin or 'http://localhost:3000'}{default_path}"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"


def _send_reset_email(user: User, token: str) -> None:
    reset_link = _build_reset_url(token)
    language = _resolve_language(user)
    context = {
        "name": (user.username or user.email.split("@")[0]).split()[0],
        "reset_link": reset_link,
        "expires_minutes": RESET_TOKEN_TTL_MINUTES,
        "year": _now().year,
    }
    subject = (
        "重置 SAT AI Tutor 密码"
        if language == "zh"
        else "Reset your SAT AI Tutor password"
    )
    html_body = render_template(f"emails/password_reset_{language}.html", **context)
    text_body = render_template(f"emails/password_reset_{language}.txt", **context)
    try:
        mail_service.send_email(
            to=user.email,
            subject=subject,
            text=text_body,
            html=html_body,
            headers={"X-Mail-Template": "password_reset"},
        )
    except Exception:  # pragma: no cover - defensive log
        current_app.logger.warning("Failed to send password reset email", exc_info=True)


def _resolve_language(user: User) -> str:
    pref = (getattr(user.profile, "language_preference", "") or "").lower()
    if "zh" in pref:
        return "zh"
    return "en"


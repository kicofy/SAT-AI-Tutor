"""Password reset token issuance and confirmation."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.parse import urlparse

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
        # Highest priority: browser-sent Origin header (includes scheme/host/port).
        origin = request.headers.get("Origin")
        if origin:
            return origin.rstrip("/")
        # Next: Referer (fallback when Origin absent for GET).
        referer = request.headers.get("Referer")
        if referer:
            parsed = urlparse(referer)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

        # 1) Forwarded header (standard)
        fwd = request.headers.get("Forwarded")
        if fwd:
            # format: proto=https;host=example.com
            parts = dict(
                entry.strip().split("=", 1)
                for entry in fwd.replace(";", ",").split(",")
                if "=" in entry
            )
            proto = parts.get("proto")
            host = parts.get("host")
            if host:
                return f"{(proto or request.scheme)}://{host}".rstrip("/")

        # 2) X-Forwarded-*
        proto = request.headers.get("X-Forwarded-Proto")
        host = request.headers.get("X-Forwarded-Host")
        if host:
            return f"{(proto or request.scheme)}://{host}".rstrip("/")

        # 3) Fallback to Host / url_root
        host = request.headers.get("Host") or request.host
        if host:
            return f"{request.scheme}://{host}".rstrip("/")
        if request.url_root:
            return request.url_root.rstrip("/")
        return None
    except Exception:
        return None


def _build_reset_url(token: str) -> str:
    """
    Build reset URL using a front-end base URL from env.
    PASSWORD_RESET_URL accepts just the base (e.g. http://3.238.9.209:3000)
    and we append the reset path automatically (/auth/reset-password).
    If a path is already present, we respect it and append the reset path.
    """
    raw_base = (current_app.config.get("PASSWORD_RESET_URL") or "").strip()
    if not raw_base:
        raw_base = "http://localhost:3000"

    # Ensure scheme exists
    if not raw_base.startswith(("http://", "https://")):
        raw_base = f"http://{raw_base.lstrip('/')}"

    parsed = urlparse(raw_base)
    scheme = parsed.scheme or "http"
    netloc = parsed.netloc or parsed.path  # handle cases like "example.com:3000"
    path = parsed.path if parsed.netloc else ""
    base_root = f"{scheme}://{netloc}"

    # Keep existing path (if any) and append reset path.
    reset_path = "/auth/reset-password"
    full_path = (path.rstrip("/") if path else "") + reset_path
    base_url = f"{base_root}{full_path}"

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


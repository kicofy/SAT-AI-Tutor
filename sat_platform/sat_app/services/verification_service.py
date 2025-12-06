"""Utility helpers for email verification codes."""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone
from flask import current_app, render_template
from werkzeug.exceptions import BadRequest

from ..extensions import db
from ..models import User, EmailVerificationTicket
from . import mail_service

CODE_LENGTH = 6
CODE_TTL_MINUTES = 5
MAX_ATTEMPTS = 5
RESEND_INTERVAL_SECONDS = 60
RESEND_DAILY_LIMIT = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_code(length: int = CODE_LENGTH) -> str:
    alphabet = string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


def issue_new_code(user: User, *, commit: bool = True) -> User:
    """Create a fresh code and update counters."""

    code = _generate_code()
    expiry = _now() + timedelta(minutes=CODE_TTL_MINUTES)
    user.email_verification_code = code
    user.email_verification_expires_at = expiry
    user.email_verification_attempts = 0
    user.email_verification_sent_at = _now()

    # reset daily window if older than 24h
    window_start = _coerce_aware(user.email_verification_sent_window_start) or _now()
    if window_start < _now() - timedelta(hours=24):
        window_start = _now()
        user.email_verification_sent_count = 0
    user.email_verification_sent_window_start = window_start
    user.email_verification_sent_count = (user.email_verification_sent_count or 0) + 1

    if commit:
        db.session.add(user)
        db.session.commit()
    return user


def ensure_can_resend(user: User) -> None:
    now = _now()
    sent_at = _coerce_aware(user.email_verification_sent_at)
    if sent_at and (now - sent_at).total_seconds() < RESEND_INTERVAL_SECONDS:
        raise BadRequest("verification_code_recent")
    count = user.email_verification_sent_count or 0
    window_start = _coerce_aware(user.email_verification_sent_window_start) or now
    if window_start < now - timedelta(hours=24):
        return
    if count >= RESEND_DAILY_LIMIT:
        raise BadRequest("verification_resend_limit")


def send_verification_email(user: User, *, commit: bool = True) -> None:
    ensure_can_resend(user)
    issue_new_code(user, commit=commit)
    language = _resolve_language(user)
    _deliver_code(
        email=user.email,
        language=language,
        code=user.email_verification_code,
        name=(user.username or user.email.split("@")[0]).split()[0],
    )


def verify_code(email: str, code: str) -> User:
    user = User.query.filter_by(email=email.lower()).first()
    if not user:
        raise BadRequest("verification_user_not_found")
    if user.is_email_verified:
        return user
    if not user.email_verification_code or not user.email_verification_expires_at:
        raise BadRequest("verification_code_missing")
    expires_at = _coerce_aware(user.email_verification_expires_at)
    if _now() > expires_at:
        raise BadRequest("verification_code_expired")
    if user.email_verification_attempts >= MAX_ATTEMPTS:
        raise BadRequest("verification_attempts_exceeded")
    if user.email_verification_code != code.strip():
        user.email_verification_attempts += 1
        db.session.add(user)
        db.session.commit()
        raise BadRequest("verification_code_invalid")

    user.is_email_verified = True
    user.email_verification_code = None
    user.email_verification_expires_at = None
    user.email_verification_attempts = 0
    db.session.add(user)
    db.session.commit()
    return user


def _resolve_language(user: User) -> str:
    pref = (getattr(user.profile, "language_preference", "") or "").lower()
    if "zh" in pref:
        return "zh"
    return "en"


def _subject_by_language(language: str) -> str:
    if language == "zh":
        return "SAT AI Tutor 验证码"
    return "Your SAT AI Tutor verification code"


def _build_template_context(name: str, code: str) -> dict:
    return {
        "code": code,
        "name": name,
        "expires_minutes": CODE_TTL_MINUTES,
        "year": _now().year,
    }


def _coerce_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


# Pre-registration ticket helpers ------------------------------------------------


def request_signup_code(email: str, language: str = "en") -> None:
    normalized = email.lower()
    if User.query.filter_by(email=normalized).first():
        raise BadRequest("email_exists")
    ticket = EmailVerificationTicket.query.filter_by(email=normalized).first()
    now = _now()
    if ticket:
        last_sent = _coerce_aware(ticket.last_sent_at)
        if last_sent and (now - last_sent).total_seconds() < RESEND_INTERVAL_SECONDS:
            raise BadRequest("verification_code_recent")
        if last_sent and last_sent > now - timedelta(hours=24):
            if ticket.resend_count >= RESEND_DAILY_LIMIT:
                raise BadRequest("verification_resend_limit")
        else:
            ticket.resend_count = 0
    else:
        ticket = EmailVerificationTicket(email=normalized, language=language or "en")
    ticket.code = _generate_code()
    ticket.expires_at = now + timedelta(minutes=CODE_TTL_MINUTES)
    ticket.attempts = 0
    ticket.last_sent_at = now
    ticket.resend_count = (ticket.resend_count or 0) + 1
    ticket.language = (language or ticket.language or "en")
    db.session.add(ticket)
    db.session.commit()
    _deliver_code(
        email=normalized,
        language=ticket.language,
        code=ticket.code,
        name=normalized.split("@")[0],
    )


def consume_signup_code(email: str, code: str) -> EmailVerificationTicket:
    normalized = email.lower()
    ticket = EmailVerificationTicket.query.filter_by(email=normalized).first()
    if not ticket:
        raise BadRequest("verification_code_missing")
    if _now() > _coerce_aware(ticket.expires_at):
        raise BadRequest("verification_code_expired")
    if ticket.attempts >= MAX_ATTEMPTS:
        raise BadRequest("verification_attempts_exceeded")
    if ticket.code != code.strip():
        ticket.attempts += 1
        db.session.add(ticket)
        db.session.commit()
        raise BadRequest("verification_code_invalid")
    db.session.delete(ticket)
    db.session.commit()
    return ticket


def _deliver_code(*, email: str, language: str, code: str, name: str) -> None:
    context = _build_template_context(name, code)
    subject = _subject_by_language(language)
    html_body = render_template(f"emails/verification_{language}.html", **context)
    text_body = render_template(f"emails/verification_{language}.txt", **context)
    mail_service.send_email(
        to=email,
        subject=subject,
        text=text_body,
        html=html_body,
        headers={"X-Mail-Template": "signup_verification"},
    )


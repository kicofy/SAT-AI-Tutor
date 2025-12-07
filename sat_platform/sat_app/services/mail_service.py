"""Outgoing email utilities."""

from __future__ import annotations

import re
import smtplib
from contextlib import contextmanager
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Iterable, Sequence

from flask import current_app


class MailServiceError(RuntimeError):
    """Raised when the mailer fails to deliver a message."""


def send_email(
    *,
    to: str | Sequence[str],
    subject: str,
    text: str | None = None,
    html: str | None = None,
    cc: str | Sequence[str] | None = None,
    bcc: str | Sequence[str] | None = None,
    reply_to: str | None = None,
    sender: tuple[str, str] | str | None = None,
    headers: dict[str, str] | None = None,
) -> str | None:
    """Send an email using the SMTP settings from Flask config.

    Args:
        to: Recipient email or list of recipients.
        subject: Email subject.
        text: Plain-text body.
        html: HTML body (optional).
        cc: Carbon-copy recipients.
        bcc: Blind carbon-copy recipients (not added to headers).
        reply_to: Optional reply-to address.
        sender: Override default sender. Accepts "email" or (name, email).
        headers: Additional MIME headers.

    Returns:
        The RFC Message-ID of the delivered message, or ``None`` when
        delivery is skipped (e.g., mail disabled).

    Raises:
        MailServiceError: when delivery fails.
        ValueError: when required parameters are missing.
    """

    config = current_app.config
    if not config.get("MAIL_ENABLED", True):
        current_app.logger.info("Mail disabled; skipping send to %s", to)
        return None

    recipients = _normalize_recipients(to)
    if not recipients:
        raise ValueError("At least one recipient is required")
    cc_recipients = _normalize_recipients(cc)
    bcc_recipients = _normalize_recipients(bcc)

    if text is None and html is None:
        raise ValueError("Either text or html body must be provided")

    msg = EmailMessage()
    msg["Subject"] = subject
    from_name, from_email = _resolve_sender(sender, config)
    msg["From"] = formataddr((from_name, from_email)) if from_name else from_email
    msg["To"] = ", ".join(recipients)
    if cc_recipients:
        msg["Cc"] = ", ".join(cc_recipients)
    reply_to_header = reply_to or config.get("MAIL_REPLY_TO")
    if reply_to_header:
        msg["Reply-To"] = reply_to_header
    if headers:
        for key, value in headers.items():
            msg[key] = value
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if from_email else None)

    plain_body = text or (_html_to_text(html) if html else "")
    msg.set_content(plain_body or " ")
    if html:
        msg.add_alternative(html, subtype="html")

    all_recipients = recipients + cc_recipients + bcc_recipients

    try:
        with _smtp_connection(config) as client:
            client.send_message(msg, to_addrs=all_recipients or None)
            current_app.logger.info(
                "Email sent to=%s subject=%s message_id=%s",
                all_recipients or recipients,
                subject,
                msg["Message-ID"],
            )
            return msg["Message-ID"]
    except Exception as exc:  # pragma: no cover - defensive logging
        current_app.logger.exception("Failed to send email: %s", exc)
        raise MailServiceError(str(exc)) from exc


def _normalize_recipients(addresses: str | Sequence[str] | None) -> list[str]:
    if addresses is None:
        return []
    if isinstance(addresses, str):
        addresses = [addresses]
    normalized = []
    for address in addresses:
        if not address:
            continue
        normalized.append(address.strip())
    return normalized


def _resolve_sender(
    sender_override: tuple[str, str] | str | None,
    config: dict,
) -> tuple[str | None, str]:
    # Many SMTP providers (Zoho, Gmail, etc.) require the envelope sender to match the
    # authenticated username. Prefer MAIL_USERNAME when available to avoid 553 relay
    # errors, but still fall back to MAIL_DEFAULT_SENDER for development convenience.
    default_email = config.get("MAIL_USERNAME") or config.get("MAIL_DEFAULT_SENDER")
    default_name = config.get("MAIL_DEFAULT_NAME")
    if isinstance(sender_override, tuple):
        return sender_override[0], sender_override[1]
    if isinstance(sender_override, str):
        return default_name, sender_override
    return default_name, default_email


def _html_to_text(html: str | None) -> str:
    if not html:
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", html)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@contextmanager
def _smtp_connection(config: dict):
    server = config.get("MAIL_SERVER")
    port = config.get("MAIL_PORT")
    timeout = config.get("MAIL_TIMEOUT", 30)
    username = config.get("MAIL_USERNAME")
    password = config.get("MAIL_PASSWORD")
    use_ssl = config.get("MAIL_USE_SSL", False)
    use_tls = config.get("MAIL_USE_TLS", True)

    if not server or not port:
        raise MailServiceError("SMTP server or port is not configured")

    smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    client = smtp_cls(server, port, timeout=timeout)
    try:
        if not use_ssl and use_tls:
            client.starttls()
        if username:
            client.login(username, password)
        yield client
    finally:
        try:
            client.quit()
        except Exception:  # pragma: no cover - defensive close
            client.close()


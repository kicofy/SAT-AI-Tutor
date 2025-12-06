from __future__ import annotations

from contextlib import contextmanager

import pytest

from sat_app.services import mail_service


@contextmanager
def _stub_connection(sentinel):
    class DummySMTP:
        def __init__(self):
            self.closed = False

        def send_message(self, message, to_addrs=None):
            sentinel["message"] = message
            sentinel["to_addrs"] = to_addrs

        def quit(self):
            self.closed = True

    smtp = DummySMTP()
    yield smtp
    smtp.quit()


def test_send_email_builds_message(monkeypatch, app_with_db):
    captured = {}
    monkeypatch.setattr(mail_service, "_smtp_connection", lambda config: _stub_connection(captured))

    app_with_db.config.update(
        {
            "MAIL_USERNAME": "noreply@aisatmentor.com",
            "MAIL_PASSWORD": "secret",
            "MAIL_DEFAULT_SENDER": "noreply@aisatmentor.com",
            "MAIL_DEFAULT_NAME": "SAT AI Tutor",
            "MAIL_ENABLED": True,
        }
    )

    with app_with_db.app_context():
        message_id = mail_service.send_email(
            to="student@example.com",
            subject="Welcome",
            text="Plain text body",
            html="<p>HTML body</p>",
            cc=["coach@example.com"],
            bcc=["ops@example.com"],
        )

    assert "message" in captured
    assert message_id is not None
    assert "coach@example.com" in captured["to_addrs"]
    assert "ops@example.com" in captured["to_addrs"]
    message = captured["message"]
    assert message["Subject"] == "Welcome"
    assert message["To"] == "student@example.com"
    assert "coach@example.com" in message["Cc"]


def test_send_email_skips_when_disabled(monkeypatch, app_with_db):
    called = {"used": False}

    def _fail_connection(config):
        called["used"] = True
        return _stub_connection({})

    monkeypatch.setattr(mail_service, "_smtp_connection", _fail_connection)
    app_with_db.config["MAIL_ENABLED"] = False

    with app_with_db.app_context():
        result = mail_service.send_email(
            to="student@example.com",
            subject="Disabled",
            text="body",
        )

    assert result is None
    assert called["used"] is False


def test_send_email_requires_body(app_with_db):
    app_with_db.config["MAIL_ENABLED"] = True
    with app_with_db.app_context():
        with pytest.raises(ValueError):
            mail_service.send_email(to="student@example.com", subject="oops")


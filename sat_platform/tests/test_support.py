from __future__ import annotations

import pytest

from sat_app.services import settings_service, mail_service


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_update_general_settings(client, admin_token):
    response = client.put(
        "/api/admin/settings/general",
        json={"suggestion_email": "support@example.com"},
        headers=_auth_header(admin_token),
    )
    assert response.status_code == 200
    assert response.get_json()["settings"]["suggestion_email"] == "support@example.com"
    with client.application.app_context():
        assert settings_service.get_setting("suggestion_email") == "support@example.com"


def test_submit_suggestion_sends_email(client, student_token, monkeypatch):
    with client.application.app_context():
        settings_service.set_setting("suggestion_email", "support@example.com")

    sent: dict | None = {}

    def fake_send_email(**kwargs):
        nonlocal sent
        sent = kwargs
        return "msg"

    monkeypatch.setattr(mail_service, "send_email", fake_send_email)

    resp = client.post(
        "/api/support/suggestions",
        json={"title": "Bug report", "content": "Details here", "contact": "student@demo.com"},
        headers=_auth_header(student_token),
    )
    assert resp.status_code == 200
    assert sent is not None
    assert sent["to"] == "support@example.com"
    assert "Bug report" in sent["subject"]


def test_submit_suggestion_without_recipient_fails(client, student_token):
    with client.application.app_context():
        settings_service.set_setting("suggestion_email", None)
    resp = client.post(
        "/api/support/suggestions",
        json={"title": "Test", "content": "No recipient"},
        headers=_auth_header(student_token),
    )
    assert resp.status_code == 400


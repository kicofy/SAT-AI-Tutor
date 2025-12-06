from __future__ import annotations

from sat_app.services import mail_service


def test_admin_can_send_test_email(monkeypatch, client, admin_token):
    captured = {}

    def fake_send_email(**kwargs):
        captured.update(kwargs)
        return "test-id"

    monkeypatch.setattr(mail_service, "send_email", fake_send_email)

    resp = client.post(
        "/api/admin/email/test",
        json={
            "email": "student@example.com",
            "subject": "Hello",
            "message": "Testing",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200
    assert captured["to"] == "student@example.com"
    assert captured["subject"] == "Hello"


def test_student_cannot_send_test_email(monkeypatch, client, student_token):
    resp = client.post(
        "/api/admin/email/test",
        json={"email": "student@example.com"},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 403


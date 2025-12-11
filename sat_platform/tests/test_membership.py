from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sat_app.extensions import db
from sat_app.models import User, DiagnosticAttempt, Question


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _ensure_diagnostic(user_id: int):
    attempt = DiagnosticAttempt(
        user_id=user_id,
        status="skipped",
        total_questions=0,
        result_summary={"status": "skipped"},
    )
    db.session.add(attempt)


def test_plan_requires_membership_after_trial(client, app_with_db, student_token):
    with app_with_db.app_context():
        user = User.query.filter_by(email="student@example.com").first()
        user.created_at = datetime.now(timezone.utc) - timedelta(days=8)
        db.session.add(user)
        _ensure_diagnostic(user.id)
        db.session.commit()
    resp = client.get("/api/learning/plan/today", headers=_auth(student_token))
    assert resp.status_code == 402
    assert resp.get_json()["error"] == "membership_required"


def test_plan_allowed_during_trial(client, app_with_db, student_token):
    with app_with_db.app_context():
        user = User.query.filter_by(email="student@example.com").first()
        user.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.session.add(user)
        _ensure_diagnostic(user.id)
        db.session.commit()
    resp = client.get("/api/learning/plan/today", headers=_auth(student_token))
    assert resp.status_code == 200
    assert "plan" in resp.get_json()


def test_ai_explain_quota_enforced(client, app_with_db, student_token, monkeypatch):
    with app_with_db.app_context():
        user = User.query.filter_by(email="student@example.com").first()
        user.created_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.session.add(user)
        question = Question(
            section="RW",
            stem_text="Sample stem",
            choices={"A": "One", "B": "Two", "C": "Three", "D": "Four"},
            correct_answer={"value": "A"},
        )
        db.session.add(question)
        db.session.commit()
        question_id = question.id

    def _fake_explainer(**kwargs):
        return {"steps": [], "language": "en"}

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_explainer)

    payload = {"question_id": question_id, "user_answer": {"value": "A"}}
    for _ in range(5):
        resp = client.post("/api/ai/explain", json=payload, headers=_auth(student_token))
        assert resp.status_code == 200
    final = client.post("/api/ai/explain", json=payload, headers=_auth(student_token))
    assert final.status_code == 429
    assert final.get_json()["error"] == "ai_explain_quota_exceeded"


def test_student_can_create_membership_order(client, student_token):
    resp = client.post(
        "/api/membership/orders",
        json={"plan": "monthly"},
        headers=_auth(student_token),
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["order"]["status"] == "pending"
    assert data["order"]["plan"] == "monthly"


def test_admin_can_approve_membership_order(client, app_with_db, student_token, admin_token):
    create_resp = client.post(
        "/api/membership/orders",
        json={"plan": "quarterly"},
        headers=_auth(student_token),
    )
    assert create_resp.status_code == 201
    order_id = create_resp.get_json()["order"]["id"]

    decision = client.post(
        f"/api/admin/membership/orders/{order_id}/decision",
        json={"action": "approve"},
        headers=_auth(admin_token),
    )
    assert decision.status_code == 200
    payload = decision.get_json()
    assert payload["order"]["status"] == "approved"

    with app_with_db.app_context():
        user = User.query.filter_by(email="student@example.com").first()
        assert user.membership_expires_at is not None


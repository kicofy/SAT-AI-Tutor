"""Tests for analytics endpoints."""

from __future__ import annotations

import pytest

from sat_app.extensions import db
from sat_app.models import Question


@pytest.fixture()
def question_fixture(app_with_db):
    with app_with_db.app_context():
        q = Question(
            section="RW",
            sub_section="Grammar",
            stem_text="Choose correct.",
            choices={"A": "A", "B": "B"},
            correct_answer={"value": "A"},
            difficulty_level=3,
            skill_tags=["RW_StandardEnglish"],
        )
        db.session.add(q)
        db.session.commit()
        return q.id


def _start_and_answer(client, token, question_id):
    resp = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    session = resp.get_json()["session"]
    entry = session["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": session["id"],
            "question_id": entry["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/api/learning/session/end",
        json={"session_id": session["id"]},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_progress_endpoint(client, student_token, question_fixture, monkeypatch):
    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: {"protocol_version": "1.0", "question_id": question_fixture, "explanation_blocks": []},
    )
    _start_and_answer(client, student_token, question_fixture)

    resp = client.get(
        "/api/analytics/progress",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["progress"]
    assert data
    assert "predicted_score_rw" in data[-1]


def test_ai_diagnose_endpoint(client, student_token, question_fixture, monkeypatch):
    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: {"protocol_version": "1.0", "question_id": question_fixture, "explanation_blocks": []},
    )
    monkeypatch.setattr(
        "sat_app.services.ai_diagnostic.generate_report",
        lambda user_id: type("Report", (), {"predictor_payload": {"rw": 500, "math": 510}, "narrative": {"protocol_version": "diag"}})(),
    )
    _start_and_answer(client, student_token, question_fixture)

    resp = client.post(
        "/api/ai/diagnose",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["predictor"]["rw"] == 500
    assert body["narrative"]["protocol_version"] == "diag"


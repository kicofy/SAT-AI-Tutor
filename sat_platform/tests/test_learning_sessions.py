"""Tests for student practice sessions."""

from __future__ import annotations

import pytest

from sat_app.extensions import db
from sat_app.models import Question


@pytest.fixture()
def seeded_question(app_with_db):
    with app_with_db.app_context():
        question = Question(
            section="RW",
            sub_section="Grammar",
            stem_text="Choose the correct option.",
            choices={"A": "Option A", "B": "Option B"},
            correct_answer={"value": "A"},
            skill_tags=["grammar"],
        )
        db.session.add(question)
        db.session.commit()
        return question.id


def test_student_can_start_session(client, seeded_question, student_token):
    resp = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["session"]
    assert len(data["questions_assigned"]) == 1


def test_student_can_answer_question(client, seeded_question, student_token, monkeypatch):
    fake_payload = {
        "protocol_version": "1.0",
        "question_id": seeded_question,
        "answer_correct": True,
        "explanation_blocks": [
            {"language": "bilingual", "text_en": "mock", "text_zh": "mock", "related_parts": []}
        ],
    }

    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: fake_payload,
    )
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    question_entry = start["questions_assigned"][0]
    answer_resp = client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "A"},
            "time_spent_sec": 30,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert answer_resp.status_code == 200
    body = answer_resp.get_json()
    assert body["is_correct"] is True
    assert body["explanation"]["protocol_version"] == "1.0"


def test_mastery_endpoint_returns_snapshot(client, seeded_question, student_token, monkeypatch):
    fake_payload = {
        "protocol_version": "1.0",
        "question_id": seeded_question,
        "answer_correct": False,
        "explanation_blocks": [
            {"language": "bilingual", "text_en": "mock", "text_zh": "mock", "related_parts": []}
        ],
    }

    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: fake_payload,
    )

    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]

    question_entry = start["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "B"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    mastery_resp = client.get(
        "/api/learning/mastery",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert mastery_resp.status_code == 200
    payload = mastery_resp.get_json()
    assert payload["mastery"]


def test_plan_endpoints(client, seeded_question, student_token, monkeypatch):
    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: {
            "protocol_version": "1.0",
            "question_id": seeded_question,
            "answer_correct": True,
            "explanation_blocks": [],
        },
    )

    resp = client.get(
        "/api/learning/plan/today",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    plan = resp.get_json()["plan"]
    assert plan["protocol_version"] == "plan.v1"

    regen = client.post(
        "/api/learning/plan/regenerate",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert regen.status_code == 200


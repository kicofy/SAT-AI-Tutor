"""Tests for AI explainer endpoints."""

from __future__ import annotations

import pytest

from sat_app.extensions import db
from sat_app.models import Question


@pytest.fixture()
def question_id(app_with_db):
    with app_with_db.app_context():
        q = Question(
            section="RW",
            sub_section="Grammar",
            stem_text="Pick the correct option.",
            choices={"A": "A", "B": "B"},
            correct_answer={"value": "A"},
            skill_tags=["grammar"],
        )
        db.session.add(q)
        db.session.commit()
        return q.id


def test_ai_explain_endpoint(client, student_token, question_id, monkeypatch):
    fake_payload = {
        "protocol_version": "1.0",
        "question_id": question_id,
        "answer_correct": True,
        "explanation_blocks": [
            {"language": "bilingual", "text_en": "mock", "text_zh": "mock", "related_parts": []}
        ],
    }

    monkeypatch.setattr(
        "sat_app.services.ai_explainer.generate_explanation",
        lambda *args, **kwargs: fake_payload,
    )

    resp = client.post(
        "/api/ai/explain",
        json={"question_id": question_id, "user_answer": {"value": "A"}},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["explanation"]["protocol_version"] == "1.0"


def _prepare_session_and_log(client, token):
    resp = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_json()
    start = resp.get_json()["session"]
    question_entry = start["questions_assigned"][0]
    answer = client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {token}"},
    ).get_json()
    return question_entry["question_id"], answer["log_id"]


def test_ai_explain_detail_does_not_generate(client, student_token, question_id, monkeypatch):
    question_id, log_id = _prepare_session_and_log(client, student_token)
    called = {"count": 0}

    def _should_not_run(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("generate_explanation should not be called")

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _should_not_run)
    resp = client.post(
        "/api/ai/explain/detail",
        json={"question_id": question_id, "log_id": log_id},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ai_explanation"] is None
    assert payload["meta"]["has_ai_explanation"] is False
    assert payload["meta"]["explanation_language"] == "en"
    assert called["count"] == 0


def test_ai_explain_generate_then_detail(client, student_token, question_id, monkeypatch):
    question_id, log_id = _prepare_session_and_log(client, student_token)
    calls = {"count": 0}
    fake_payload = {
        "protocol_version": "1.0",
        "question_id": question_id,
        "answer_correct": True,
        "explanation_blocks": [],
    }

    def _fake_generate(*args, **kwargs):
        calls["count"] += 1
        return fake_payload

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_generate)
    resp = client.post(
        "/api/ai/explain/generate",
        json={"question_id": question_id, "log_id": log_id},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    assert calls["count"] == 1

    detail = client.post(
        "/api/ai/explain/detail",
        json={"question_id": question_id, "log_id": log_id},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()
    assert detail["ai_explanation"]["protocol_version"] == "1.0"
    assert detail["meta"]["has_ai_explanation"] is True


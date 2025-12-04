"""Tests for student practice sessions."""

from __future__ import annotations

import pytest

from sat_app.extensions import db
from sat_app.models import Question, StudySession


@pytest.fixture()
def seeded_question(app_with_db):
    with app_with_db.app_context():
        question = Question(
            section="RW",
            sub_section="Grammar",
            stem_text="Choose the correct option.",
            choices={"A": "Option A", "B": "Option B"},
            correct_answer={"value": "A"},
            skill_tags=["RW_StandardEnglish"],
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
    calls = {"count": 0}

    def _fake_explainer(*args, **kwargs):
        calls["count"] += 1
        return {
            "protocol_version": "1.0",
            "question_id": seeded_question,
            "answer_correct": True,
            "language": "en",
            "summary": "Mock summary",
            "steps": [
                {
                    "id": "s1",
                    "type": "focus",
                    "title": "Mock",
                    "narration": "mock narration",
                    "duration_ms": 2000,
                    "delay_ms": 300,
                    "animations": [{"target": "stem", "text": "mock", "action": "highlight", "cue": "reason"}],
                    "board_notes": ["tip"],
                }
            ],
        }

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_explainer)
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    question_entry = start["questions_assigned"][0]
    answer_data = client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "A"},
            "time_spent_sec": 30,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()
    assert answer_data["is_correct"] is True
    assert "log_id" in answer_data
    explanation = client.post(
        "/api/learning/session/explanation",
        json={"session_id": start["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["explanation"]
    assert explanation["protocol_version"] == "1.0"
    explanation_again = client.post(
        "/api/learning/session/explanation",
        json={"session_id": start["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["explanation"]
    assert explanation_again["protocol_version"] == "1.0"
    assert calls["count"] == 1


def test_mastery_endpoint_returns_snapshot(client, seeded_question, student_token, monkeypatch):
    fake_payload = {
        "protocol_version": "1.0",
        "question_id": seeded_question,
        "answer_correct": False,
        "language": "en",
        "summary": "Mock summary",
        "steps": [
            {
                "id": "s1",
                "type": "focus",
                "title": "Mock",
                "narration": "mock narration",
                "duration_ms": 2000,
                "delay_ms": 300,
                "animations": [],
                "board_notes": [],
            }
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
            "language": "en",
            "summary": "Mock",
            "steps": [
                {
                    "id": "s1",
                    "type": "focus",
                    "title": "Mock",
                    "narration": "mock",
                    "duration_ms": 2000,
                    "delay_ms": 300,
                    "animations": [],
                    "board_notes": [],
                }
            ],
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


def test_explanation_cache_reused_across_sessions(client, seeded_question, student_token, monkeypatch):
    calls = {"count": 0}

    def _fake_explainer(*args, **kwargs):
        calls["count"] += 1
        return {
            "protocol_version": "1.0",
            "question_id": seeded_question,
            "answer_correct": True,
            "language": "en",
            "summary": "Cache summary",
            "steps": [
                {
                    "id": "s1",
                    "type": "focus",
                    "title": "Mock Step",
                    "narration": "mock narration",
                    "duration_ms": 2000,
                    "delay_ms": 300,
                    "animations": [{"target": "stem", "text": "mock", "action": "highlight"}],
                    "board_notes": [],
                }
            ],
        }

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_explainer)

    def _complete_session():
        session = client.post(
            "/api/learning/session/start",
            json={"num_questions": 1},
            headers={"Authorization": f"Bearer {student_token}"},
        ).get_json()["session"]
        question_entry = session["questions_assigned"][0]
        client.post(
            "/api/learning/session/answer",
            json={
                "session_id": session["id"],
                "question_id": question_entry["question_id"],
                "user_answer": {"value": "A"},
            },
            headers={"Authorization": f"Bearer {student_token}"},
        )
        explanation = client.post(
            "/api/learning/session/explanation",
            json={"session_id": session["id"], "question_id": question_entry["question_id"]},
            headers={"Authorization": f"Bearer {student_token}"},
        ).get_json()["explanation"]
        return explanation

    first_explanation = _complete_session()
    assert first_explanation["protocol_version"] == "1.0"
    assert calls["count"] == 1

    second_explanation = _complete_session()
    assert second_explanation["protocol_version"] == "1.0"
    assert second_explanation == first_explanation
    assert calls["count"] == 1


def test_clear_explanation_endpoint(client, seeded_question, student_token, monkeypatch):
    calls = {"count": 0}

    def _fake_explainer(*args, **kwargs):
        calls["count"] += 1
        return {
            "protocol_version": "1.0",
            "question_id": seeded_question,
            "answer_correct": False,
            "language": "en",
            "summary": "Mock summary",
            "steps": [
                {
                    "id": "s1",
                    "type": "focus",
                    "title": "Mock",
                    "narration": "mock",
                    "duration_ms": 2000,
                    "delay_ms": 300,
                    "animations": [],
                    "board_notes": [],
                }
            ],
        }

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_explainer)

    session = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    question_entry = session["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": session["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    client.post(
        "/api/learning/session/explanation",
        json={"session_id": session["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert calls["count"] == 1

    clear_resp = client.post(
        "/api/learning/session/explanation/clear",
        json={"session_id": session["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert clear_resp.status_code == 200

    client.post(
        "/api/learning/session/explanation",
        json={"session_id": session["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert calls["count"] == 2


def test_active_session_resume_and_abort(client, seeded_question, student_token):
    start_resp = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert start_resp.status_code == 201
    session = start_resp.get_json()["session"]
    question_entry = session["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": session["id"],
            "question_id": question_entry["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    active = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    assert active is not None
    assert active["id"] == session["id"]
    assert active["questions_done"]

    client.post(
        "/api/learning/session/abort",
        json={"session_id": session["id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    active_after_abort = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    assert active_after_abort is None


def test_session_summary_saved_on_completion(client, seeded_question, student_token):
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
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    client.post(
        "/api/learning/session/end",
        json={"session_id": start["id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    with client.application.app_context():
        session = db.session.get(StudySession, start["id"])
        assert session.summary
        assert session.summary["total_questions"] == 1
        assert session.summary["correct"] == 1


"""Tests for student practice sessions."""

from __future__ import annotations

import pytest

from sat_app.extensions import db
from sat_app.models import Question, StudySession, QuestionExplanationCache
from sat_app.services import question_explanation_service


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
        fallback = Question(
            section="RW",
            sub_section="Grammar",
            stem_text="Fallback question text.",
            choices={"A": "Fallback A", "B": "Fallback B"},
            correct_answer={"value": "B"},
            skill_tags=["RW_StandardEnglish"],
        )
        db.session.add_all([question, fallback])
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


def test_plan_session_does_not_block_practice_flow(
    app_with_db, client, seeded_question, student_token
):
    from sat_app.models import User, Question
    from sat_app.services import session_service

    with app_with_db.app_context():
        user = User.query.filter_by(email="student@example.com").first()
        assert user is not None
        question = db.session.get(Question, seeded_question)
        session_service.create_session(
            user_id=user.id,
            questions=[question],
            plan_block_id="block-abc",
            session_type="plan",
        )

    active = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    assert active is None

    resp = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 201

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
    with client.application.app_context():
        cache = QuestionExplanationCache.query.filter_by(
            question_id=question_entry["question_id"]
        ).first()
        assert cache is not None
    with client.application.app_context():
        question = db.session.get(Question, question_entry["question_id"])
        stats = question.metadata_json.get("difficulty_stats")
        assert stats["total_attempts"] == 1


def test_cached_explanations_reused(client, app_with_db, seeded_question, student_token, monkeypatch):
    calls = {"count": 0}

    def _fake_generate(*args, **kwargs):
        calls["count"] += 1
        return {
            "protocol_version": "1.0",
            "question_id": seeded_question,
            "answer_correct": True,
            "language": "bilingual",
            "summary": "cached",
            "steps": [],
        }

    monkeypatch.setattr("sat_app.services.ai_explainer.generate_explanation", _fake_generate)
    with app_with_db.app_context():
        for question in Question.query.all():
            question_explanation_service.ensure_explanation(
                question=question,
                language="en",
                source="test",
            )
    initial_calls = calls["count"]

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
    resp = client.post(
        "/api/learning/session/explanation",
        json={"session_id": start["id"], "question_id": question_entry["question_id"]},
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    assert calls["count"] == initial_calls


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


def test_active_session_reflects_question_updates(app_with_db, client, seeded_question, student_token):
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    with app_with_db.app_context():
        question = db.session.get(Question, seeded_question)
        question.stem_text = "Updated stem text"
        question.choices = {"A": "Option A", "B": "Rewritten B"}
        question.correct_answer = {"value": "B"}
        db.session.commit()
    active = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    assert active is not None
    refreshed = active["questions_assigned"][0]
    assert refreshed["stem_text"] == "Updated stem text"
    assert refreshed["choices"]["B"] == "Rewritten B"
    assert refreshed["correct_answer"]["value"] == "B"


def test_active_session_uses_cached_when_question_deleted(app_with_db, client, seeded_question, student_token):
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    cached = start["questions_assigned"][0]
    with app_with_db.app_context():
        question = db.session.get(Question, seeded_question)
        db.session.delete(question)
        db.session.commit()
    active = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    assert active is not None
    fallback = active["questions_assigned"][0]
    assert fallback["question_id"] != cached["question_id"]
    assert fallback["stem_text"] != cached["stem_text"]
def test_deleted_answered_question_marked_unavailable(
    app_with_db, client, seeded_question, student_token
):
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
    with app_with_db.app_context():
        question = db.session.get(Question, seeded_question)
        db.session.delete(question)
        db.session.commit()
    active = client.get(
        "/api/learning/session/active",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    entry = next(
        (q for q in active["questions_assigned"] if q["question_id"] == question_entry["question_id"]),
        None,
    )
    assert entry is not None
    assert entry.get("unavailable_reason") == "question_deleted"


def test_answer_endpoint_handles_deleted_question(
    app_with_db, client, seeded_question, student_token
):
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    with app_with_db.app_context():
        question = db.session.get(Question, seeded_question)
        db.session.delete(question)
        db.session.commit()
    resp = client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": start["questions_assigned"][0]["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["error"] == "question_reassigned"
    assert payload["session"]["questions_assigned"]
    assert payload["session"]["questions_assigned"][0]["question_id"] != seeded_question


def test_answer_endpoint_reports_unavailable_when_bank_empty(
    app_with_db, client, seeded_question, student_token
):
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    with app_with_db.app_context():
        Question.query.delete()
        db.session.commit()
    resp = client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": start["questions_assigned"][0]["question_id"],
            "user_answer": {"value": "A"},
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 409
    payload = resp.get_json()
    assert payload["error"] == "question_unavailable"
    assert "session" not in payload


def test_tutor_notes_endpoint_returns_cached(client, student_token, monkeypatch):
    calls = {"count": 0}

    def fake_call_ai(*args, **kwargs):
        calls["count"] += 1
        return {
            "notes": [
                {"title": "Focus", "body": "Do RW first", "priority": "info"},
            ]
        }

    monkeypatch.setattr("sat_app.services.tutor_notes_service._call_ai", fake_call_ai)

    client.post(
        "/api/diagnostic/skip",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    resp = client.get(
        "/api/learning/tutor-notes/today",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["notes"][0]["title"] == "Focus"
    assert calls["count"] == 1

    # Second call should return cached result without invoking AI again
    resp2 = client.get(
        "/api/learning/tutor-notes/today",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp2.status_code == 200
    assert calls["count"] == 1


def test_tutor_notes_fallback_when_disabled(app_with_db, client, student_token, monkeypatch):
    with app_with_db.app_context():
        original = app_with_db.config.get("AI_TUTOR_NOTES_ENABLE", True)
        app_with_db.config["AI_TUTOR_NOTES_ENABLE"] = False
    try:
        client.post(
            "/api/diagnostic/skip",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        resp = client.get(
            "/api/learning/tutor-notes/today",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["notes"]
        assert all("title" in note for note in payload["notes"])
        assert any("New" in note["title"] or "新用户" in note["title"] for note in payload["notes"])
    finally:
        with app_with_db.app_context():
            app_with_db.config["AI_TUTOR_NOTES_ENABLE"] = original


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

    client.post(
        "/api/diagnostic/skip",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    resp = client.get(
        "/api/learning/plan/today",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 200
    plan = resp.get_json()["plan"]
    assert plan["protocol_version"] == "plan.v2"

    regen = client.post(
        "/api/learning/plan/regenerate",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert regen.status_code == 200


def test_plan_endpoint_requires_diagnostic(client, student_token):
    resp = client.get(
        "/api/learning/plan/today",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert resp.status_code == 428
    payload = resp.get_json()
    assert payload["error"] == "diagnostic_required"
    diagnostic = payload.get("diagnostic")
    assert diagnostic
    assert diagnostic.get("requires_diagnostic") is True


def test_analytics_efficiency_and_mistakes(app_with_db, client, student_token):
    from sat_app.models import Question

    with app_with_db.app_context():
        math_question = Question(
            section="Math",
            sub_section="Algebra",
            stem_text="Solve x+2=4",
            choices={"A": "1", "B": "2"},
            correct_answer={"value": "B"},
            skill_tags=["M_Algebra"],
            difficulty_level=3,
        )
        db.session.add(math_question)
        db.session.commit()

    # Correct answer to generate timing data
    start = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1, "section": "Math"},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    entry = start["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": start["id"],
            "question_id": entry["question_id"],
            "user_answer": {"value": "B"},
            "time_spent_sec": 90,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    # Incorrect answer to populate mistake queue
    second = client.post(
        "/api/learning/session/start",
        json={"num_questions": 1, "section": "Math"},
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()["session"]
    second_entry = second["questions_assigned"][0]
    client.post(
        "/api/learning/session/answer",
        json={
            "session_id": second["id"],
            "question_id": second_entry["question_id"],
            "user_answer": {"value": "A"},
            "time_spent_sec": 40,
        },
        headers={"Authorization": f"Bearer {student_token}"},
    )

    eff = client.get(
        "/api/analytics/efficiency",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()
    assert eff["sample_size"] >= 1
    assert eff["sections"]

    mistakes = client.get(
        "/api/analytics/mistakes",
        headers={"Authorization": f"Bearer {student_token}"},
    ).get_json()
    assert mistakes["total_mistakes"] >= 1


def test_diagnostic_start_and_status(client, seeded_question, student_token):
    status_resp = client.get(
        "/api/diagnostic/status",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert status_resp.status_code == 200
    status_payload = status_resp.get_json()
    assert status_payload["requires_diagnostic"] is True

    start_resp = client.post(
        "/api/diagnostic/start",
        headers={"Authorization": f"Bearer {student_token}"},
    )
    assert start_resp.status_code == 201
    start_payload = start_resp.get_json()
    assert start_payload["session"]


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


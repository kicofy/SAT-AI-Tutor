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


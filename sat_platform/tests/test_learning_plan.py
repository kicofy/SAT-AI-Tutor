"""Tests for advanced learning plan generation."""

from __future__ import annotations

from datetime import date

from sat_app.extensions import db
from sat_app.models import User, UserProfile, DiagnosticAttempt
from sat_app.services import learning_plan_service


def _create_user():
    user = User(
        email="plan@example.com",
        username="plan_user",
        role="student",
        password_hash="stub",
    )
    profile = UserProfile(
        user=user,
        daily_available_minutes=60,
        target_score_rw=700,
        target_score_math=750,
    )
    db.session.add(user)
    db.session.add(profile)
    db.session.commit()
    attempt = DiagnosticAttempt(
        user_id=user.id,
        status="skipped",
        total_questions=0,
        result_summary={"status": "skipped"},
    )
    db.session.add(attempt)
    db.session.commit()
    return user


def test_generate_daily_plan_enriched_metadata(app_with_db, monkeypatch):
    with app_with_db.app_context():
        user = _create_user()

        def _fake_mastery_snapshot(user_id: int):
            assert user_id == user.id
            return [
                {
                    "skill_tag": "RW_MainIdeasEvidence",
                    "label": "主旨推理",
                    "domain": "Reading & Writing",
                    "mastery_score": 0.55,
                    "last_practiced_at": None,
                },
                {
                    "skill_tag": "M_Algebra",
                    "label": "代数",
                    "domain": "Math",
                    "mastery_score": 0.62,
                    "last_practiced_at": None,
                },
            ]

        monkeypatch.setattr(
            learning_plan_service, "get_mastery_snapshot", _fake_mastery_snapshot
        )

        plan = learning_plan_service.generate_daily_plan(user.id, date.today())
        detail = plan.generated_detail
        assert detail["protocol_version"] == "plan.v2"
        assert detail["blocks"]
        assert detail["insights"]
        block = detail["blocks"][0]
        assert "priority_score" in block
        assert block.get("strategy_tips")

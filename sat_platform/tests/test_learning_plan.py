"""Tests for the learning plan service."""

from __future__ import annotations

from datetime import date

import pytest

from sat_app.extensions import db
from sat_app.models import User, UserProfile
from sat_app.services.learning_plan_service import (
    generate_daily_plan,
    get_or_generate_plan,
)


@pytest.fixture()
def student_with_profile(app_with_db):
    with app_with_db.app_context():
        user = User(
            email="plan_user@example.com",
            username="plan_user",
            password_hash="hash",
            role="student",
        )
        db.session.add(user)
        db.session.flush()
        profile = UserProfile(
            user_id=user.id,
            daily_available_minutes=90,
            target_score_rw=380,
            target_score_math=420,
        )
        db.session.add(profile)
        db.session.commit()
        return user.id


def test_generate_daily_plan(app_with_db, student_with_profile, monkeypatch):
    with app_with_db.app_context():
        monkeypatch.setattr(
            "sat_app.services.learning_plan_service.get_mastery_snapshot",
            lambda user_id: [
                {"skill_tag": "RW_Grammar", "mastery_score": 0.3},
                {"skill_tag": "Math_Algebra", "mastery_score": 0.6},
            ],
        )
        plan = generate_daily_plan(student_with_profile, date(2025, 1, 1))
        assert plan.generated_detail["plan_date"] == "2025-01-01"
        assert plan.generated_detail["blocks"]


def test_get_or_generate_plan_returns_existing(app_with_db, student_with_profile, monkeypatch):
    with app_with_db.app_context():
        calls = {"count": 0}

        def fake_generate(user_id, plan_date=None):
            calls["count"] += 1
            return generate_daily_plan(user_id, plan_date)

        monkeypatch.setattr(
            "sat_app.services.learning_plan_service.generate_daily_plan",
            generate_daily_plan,
        )
        plan1 = get_or_generate_plan(student_with_profile, date(2025, 1, 2))
        plan2 = get_or_generate_plan(student_with_profile, date(2025, 1, 2))
        assert plan1.id == plan2.id


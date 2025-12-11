"""Tests for CLI study plan commands."""

from __future__ import annotations

from sat_app.extensions import db
from sat_app.models import StudyPlan, User, UserProfile, DiagnosticAttempt
from sat_app.utils.security import hash_password


def _create_student(email: str) -> int:
    user = User(
        email=email,
        username=email.split("@")[0],
        password_hash=hash_password("StrongPass123!"),
        role="student",
    )
    user.profile = UserProfile(
        daily_available_minutes=60,
        daily_plan_questions=12,
        language_preference="en",
    )
    db.session.add(user)
    db.session.commit()
    db.session.add(
        DiagnosticAttempt(
            user_id=user.id,
            status="skipped",
            total_questions=0,
            result_summary={"status": "skipped"},
        )
    )
    db.session.commit()
    return user.id


def test_plan_generate_single_user(app_with_db):
    runner = app_with_db.test_cli_runner()
    with app_with_db.app_context():
        student_id = _create_student("plan_student@example.com")
    result = runner.invoke(args=["plan", "generate", "--user-id", str(student_id)])
    assert result.exit_code == 0, result.output
    assert "Generated plan" in result.output
    with app_with_db.app_context():
        assert StudyPlan.query.filter_by(user_id=student_id).count() == 1


def test_plan_generate_all_students(app_with_db):
    runner = app_with_db.test_cli_runner()
    with app_with_db.app_context():
        first_id = _create_student("plan_one@example.com")
        second_id = _create_student("plan_two@example.com")
    result = runner.invoke(args=["plan", "generate", "--all"])
    assert result.exit_code == 0, result.output
    output = result.output
    assert f"{first_id}" in output and f"{second_id}" in output
    with app_with_db.app_context():
        assert StudyPlan.query.filter(
            StudyPlan.user_id.in_([first_id, second_id])
        ).count() == 2


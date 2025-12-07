"""Tests for the adaptive engine and mastery tracking."""

from __future__ import annotations

from datetime import timedelta, timezone, datetime

import pytest

from sat_app.extensions import db
from sat_app.models import Question, User, StudySession, UserQuestionLog, SkillMastery, QuestionReview
from sat_app.services import adaptive_engine, spaced_repetition


@pytest.fixture()
def student_id(app_with_db):
    with app_with_db.app_context():
        user = User(
            email="adaptive_student@example.com",
            username="adaptive_student",
            password_hash="hash",
            role="student",
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _create_question(section: str, skill_tag: str, text: str) -> Question:
    question = Question(
        section=section,
        sub_section="sub",
        stem_text=text,
        choices={"A": "A", "B": "B"},
        correct_answer={"value": "A"},
        skill_tags=[skill_tag],
    )
    db.session.add(question)
    db.session.commit()
    return question


def test_select_prioritizes_low_mastery(app_with_db, student_id):
    with app_with_db.app_context():
        weak_question = _create_question("RW", "grammar", "Weak skill")
        strong_question = _create_question("RW", "vocab", "Strong skill")

        low_mastery = SkillMastery(
            user_id=student_id,
            skill_tag="grammar",
            mastery_score=0.2,
        )
        high_mastery = SkillMastery(
            user_id=student_id,
            skill_tag="vocab",
            mastery_score=0.9,
        )
        db.session.add_all([low_mastery, high_mastery])
        db.session.commit()

        result = adaptive_engine.select_next_questions(student_id, 1, section="RW")
        assert result
        assert result[0].id == weak_question.id


def test_update_mastery_from_log_adjusts_scores(app_with_db, student_id):
    with app_with_db.app_context():
        question = _create_question("Math", "algebra", "Solve x.")
        session = StudySession(user_id=student_id, questions_assigned=[])
        db.session.add(session)
        db.session.commit()

        log = UserQuestionLog(
            user_id=student_id,
            study_session_id=session.id,
            question_id=question.id,
            is_correct=False,
            user_answer={"value": "B"},
        )
        log.question = question
        db.session.add(log)
        db.session.flush()

        adaptive_engine.update_mastery_from_log(log, question)
        mastery = SkillMastery.query.filter_by(user_id=student_id, skill_tag="M_Algebra").one()
        assert mastery.mastery_score < 0.5

        log_correct = UserQuestionLog(
            user_id=student_id,
            study_session_id=session.id,
            question_id=question.id,
            is_correct=True,
            user_answer={"value": "A"},
        )
        log_correct.question = question
        db.session.add(log_correct)
        db.session.flush()

        adaptive_engine.update_mastery_from_log(log_correct, question)
        mastery = SkillMastery.query.filter_by(user_id=student_id, skill_tag="M_Algebra").one()
        assert mastery.mastery_score > 0.4


def test_spaced_repetition_injects_due_reviews(app_with_db, student_id):
    with app_with_db.app_context():
        question = _create_question("RW", "grammar", "Needs review")
        session = StudySession(user_id=student_id, questions_assigned=[])
        db.session.add(session)
        db.session.commit()

        log = UserQuestionLog(
            user_id=student_id,
            study_session_id=session.id,
            question_id=question.id,
            is_correct=False,
            user_answer={"value": "B"},
        )
        db.session.add(log)
        db.session.flush()

        spaced_repetition.schedule_from_log(log)

        review = QuestionReview.query.filter_by(user_id=student_id, question_id=question.id).one()
        review.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.session.commit()

        due_questions = spaced_repetition.get_due_questions(student_id, limit=5, section="RW")
        assert due_questions
        assert due_questions[0].id == question.id


def test_mastery_snapshot_marks_missing_data(app_with_db, student_id):
    with app_with_db.app_context():
        default_mastery = app_with_db.config.get("ADAPTIVE_DEFAULT_MASTERY", 0.5)
        snapshot = adaptive_engine.get_mastery_snapshot(student_id)
        assert snapshot
        # find a skill with no practice data
        empty_entry = next(entry for entry in snapshot if not entry["has_data"])
        assert empty_entry["observed_score"] is None
        assert empty_entry["mastery_score"] == pytest.approx(default_mastery, rel=0.2)

        target_tag = snapshot[0]["skill_tag"]
        mastery = SkillMastery(user_id=student_id, skill_tag=target_tag, mastery_score=0.7)
        db.session.add(mastery)
        db.session.commit()

        updated_snapshot = adaptive_engine.get_mastery_snapshot(student_id)
        entry = next(item for item in updated_snapshot if item["skill_tag"] == target_tag)
        assert entry["has_data"] is True
        assert entry["observed_score"] == pytest.approx(0.7)


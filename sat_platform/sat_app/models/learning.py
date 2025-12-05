"""Learning-related models (sessions, question logs)."""

from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class StudySession(db.Model):
    __tablename__ = "study_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    session_type = db.Column(db.String(32), nullable=False, default="practice")
    started_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at = db.Column(db.DateTime(timezone=True))
    questions_assigned = db.Column(db.JSON, nullable=False)
    questions_done = db.Column(db.JSON, nullable=True)
    summary = db.Column(db.JSON, nullable=True)
    plan_block_id = db.Column(db.String(128), index=True)
    diagnostic_attempt_id = db.Column(
        db.Integer, db.ForeignKey("diagnostic_attempts.id"), index=True
    )

    user = db.relationship("User", backref="study_sessions")
    plan_task = db.relationship("StudyPlanTask", back_populates="session", uselist=False)
    diagnostic_attempt = db.relationship(
        "DiagnosticAttempt",
        back_populates="session",
        uselist=False,
    )


class UserQuestionLog(db.Model):
    __tablename__ = "user_question_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    study_session_id = db.Column(db.Integer, db.ForeignKey("study_sessions.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    user_answer = db.Column(db.JSON, nullable=False)
    time_spent_sec = db.Column(db.Integer)
    answered_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    viewed_explanation = db.Column(db.Boolean, default=False, nullable=False)
    explanation = db.Column(db.JSON)

    user = db.relationship("User", backref="question_logs")
    study_session = db.relationship("StudySession", backref="question_logs")
    question = db.relationship("Question")


class SkillMastery(db.Model):
    __tablename__ = "skill_masteries"
    __table_args__ = (db.UniqueConstraint("user_id", "skill_tag", name="uq_user_skill"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    skill_tag = db.Column(db.String(128), nullable=False, index=True)
    mastery_score = db.Column(db.Float, default=0.5, nullable=False)
    success_streak = db.Column(db.Integer, default=0, nullable=False)
    last_practiced_at = db.Column(db.DateTime(timezone=True))
    due_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", backref="skill_masteries")


class QuestionReview(db.Model):
    __tablename__ = "question_reviews"
    __table_args__ = (db.UniqueConstraint("user_id", "question_id", name="uq_user_question_review"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    due_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    status = db.Column(db.String(32), default="due", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    user = db.relationship("User", backref="question_reviews")
    question = db.relationship("Question")


class StudyPlan(db.Model):
    __tablename__ = "study_plans"
    __table_args__ = (db.UniqueConstraint("user_id", "plan_date", name="uq_user_plan_date"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_date = db.Column(db.Date, nullable=False, index=True)
    target_minutes = db.Column(db.Integer, nullable=False)
    target_questions = db.Column(db.Integer, nullable=False)
    generated_detail = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", backref="study_plans")


class StudyPlanTask(db.Model):
    __tablename__ = "study_plan_tasks"
    __table_args__ = (
        db.UniqueConstraint("user_id", "plan_date", "block_id", name="uq_plan_task_block"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_date = db.Column(db.Date, nullable=False, index=True)
    block_id = db.Column(db.String(128), nullable=False)
    section = db.Column(db.String(32), nullable=False)
    focus_skill = db.Column(db.String(128))
    questions_target = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending")
    session_id = db.Column(db.Integer, db.ForeignKey("study_sessions.id"))
    started_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user = db.relationship("User", backref="study_plan_tasks")
    session = db.relationship("StudySession", back_populates="plan_task")


class DailyMetric(db.Model):
    __tablename__ = "daily_metrics"
    __table_args__ = (db.UniqueConstraint("user_id", "day", name="uq_user_day_metric"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    day = db.Column(db.Date, nullable=False, index=True)
    sessions_completed = db.Column(db.Integer, default=0, nullable=False)
    questions_answered = db.Column(db.Integer, default=0, nullable=False)
    correct_questions = db.Column(db.Integer, default=0, nullable=False)
    avg_difficulty = db.Column(db.Float)
    predicted_score_rw = db.Column(db.Integer)
    predicted_score_math = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", backref="daily_metrics")


class DiagnosticReport(db.Model):
    __tablename__ = "diagnostic_reports"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    generated_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    predictor_payload = db.Column(db.JSON, nullable=False)
    narrative = db.Column(db.JSON, nullable=False)

    user = db.relationship("User", backref="diagnostic_reports")


class DiagnosticAttempt(db.Model):
    __tablename__ = "diagnostic_attempts"
    __table_args__ = (
        db.Index("ix_diagnostic_attempts_user_status", "user_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="pending")
    total_questions = db.Column(db.Integer, nullable=False, default=0)
    started_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True))
    result_summary = db.Column(db.JSON)
    metadata_json = db.Column("metadata", db.JSON)

    user = db.relationship("User", backref="diagnostic_attempts")
    session = db.relationship(
        "StudySession",
        back_populates="diagnostic_attempt",
        uselist=False,
    )


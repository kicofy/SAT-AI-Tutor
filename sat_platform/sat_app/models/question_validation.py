from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class QuestionValidationIssue(db.Model):
    __tablename__ = "question_validation_issues"
    __table_args__ = (
        db.Index("ix_qvi_question_id", "question_id"),
        db.Index("ix_qvi_source_id", "source_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    source_id = db.Column(db.Integer, nullable=True, index=True)
    issue_code = db.Column(db.String(64), nullable=False)
    message = db.Column(db.String(512), nullable=False)
    severity = db.Column(db.String(16), default="error", nullable=False)  # error|warning
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    question = db.relationship("Question", backref="validation_issues")



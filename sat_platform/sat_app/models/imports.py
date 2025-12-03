"""Models for AI question ingestion pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class QuestionImportJob(db.Model):
    __tablename__ = "question_import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=True)
    source_path = db.Column(db.String(512), nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    ingest_strategy = db.Column(db.String(32), nullable=False, default="classic")
    status = db.Column(db.String(32), default="pending", nullable=False)
    total_blocks = db.Column(db.Integer, default=0, nullable=False)
    parsed_questions = db.Column(db.Integer, default=0, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", backref="question_import_jobs")


class QuestionDraft(db.Model):
    __tablename__ = "question_drafts"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("question_import_jobs.id"), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job = db.relationship("QuestionImportJob", backref="drafts")


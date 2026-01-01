"""Models representing source documents (e.g., uploaded PDFs)."""

from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class QuestionSource(db.Model):
    __tablename__ = "question_sources"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=True)
    stored_path = db.Column(db.String(512), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    total_pages = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    uploader = db.relationship("User", backref="question_sources")
    # When a PDF collection (QuestionSource) is deleted, also remove its ingest
    # jobs and drafts so coarse caches/drafts don't linger.
    jobs = db.relationship(
        "QuestionImportJob",
        back_populates="source",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    questions = db.relationship("Question", back_populates="source", lazy="dynamic")
    drafts = db.relationship(
        "QuestionDraft",
        back_populates="source",
        lazy="dynamic",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )



"""Models for AI question ingestion pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db
from ..models.question import QuestionFigure


def utcnow():
    return datetime.now(timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    if value is None:
        return None
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


class QuestionImportJob(db.Model):
    __tablename__ = "question_import_jobs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("question_sources.id"), nullable=True, index=True)
    filename = db.Column(db.String(255), nullable=True)
    source_path = db.Column(db.String(512), nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    ingest_strategy = db.Column(db.String(32), nullable=False, default="classic")
    status = db.Column(db.String(32), default="pending", nullable=False)
    total_blocks = db.Column(db.Integer, default=0, nullable=False)
    parsed_questions = db.Column(db.Integer, default=0, nullable=False)
    processed_pages = db.Column(db.Integer, default=0, nullable=False)
    total_pages = db.Column(db.Integer, default=0, nullable=False)
    current_page = db.Column(db.Integer, default=0, nullable=False)
    status_message = db.Column(db.Text, nullable=True)
    last_progress_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", backref="question_import_jobs")
    source = db.relationship("QuestionSource", back_populates="jobs")

    def serialize(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "filename": self.filename,
            "ingest_strategy": self.ingest_strategy,
            "status": self.status,
            "total_blocks": self.total_blocks,
            "parsed_questions": self.parsed_questions,
            "processed_pages": self.processed_pages,
            "total_pages": self.total_pages,
             "current_page": self.current_page,
            "status_message": self.status_message,
            "last_progress_at": _isoformat(self.last_progress_at),
            "error_message": self.error_message,
            "created_at": _isoformat(self.created_at),
            "updated_at": _isoformat(self.updated_at),
            "source": self._serialize_source(),
        }

    def _serialize_source(self) -> dict | None:
        if not self.source:
            return None
        return {
            "id": self.source.id,
            "filename": self.source.filename,
            "original_name": self.source.original_name,
            "total_pages": self.source.total_pages,
        }


class QuestionDraft(db.Model):
    __tablename__ = "question_drafts"

    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("question_import_jobs.id"), nullable=False, index=True)
    source_id = db.Column(db.Integer, db.ForeignKey("question_sources.id"), nullable=True, index=True)
    payload = db.Column(db.JSON, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    job = db.relationship(
        "QuestionImportJob",
        backref=db.backref("drafts", cascade="all, delete-orphan", passive_deletes=True),
    )
    source = db.relationship("QuestionSource", back_populates="drafts")
    figures = db.relationship(
        QuestionFigure,
        backref="draft",
        lazy="dynamic",
    )

    def serialize(self) -> dict:
        source_payload = None
        if self.source:
            source_payload = {
                "id": self.source.id,
                "filename": self.source.filename,
                "original_name": self.source.original_name,
                "total_pages": self.source.total_pages,
            }
        return {
            "id": self.id,
            "job_id": self.job_id,
            "source_id": self.source_id,
            "payload": self.payload,
            "is_verified": self.is_verified,
            "figure_count": self.figures.count(),
            "created_at": _isoformat(self.created_at),
            "updated_at": _isoformat(self.updated_at),
            "source": source_payload,
        }

    def serialize(self) -> dict:
        payload = self.payload or {}
        return {
            "id": self.id,
            "job_id": self.job_id,
            "source_id": self.source_id,
            "payload": payload,
            "is_verified": self.is_verified,
            "requires_figure": bool(payload.get("has_figure") or payload.get("choice_figure_keys")),
            "figure_count": self.figures.count(),
            "created_at": _isoformat(self.created_at),
            "updated_at": _isoformat(self.updated_at),
            "source": self._serialize_source(),
        }

    def _serialize_source(self) -> dict | None:
        if not self.source:
            return None
        return {
            "id": self.source.id,
            "filename": self.source.filename,
            "original_name": self.source.original_name,
            "total_pages": self.source.total_pages,
        }


from __future__ import annotations

from datetime import datetime

from ..extensions import db


class AIPaperJob(db.Model):
    __tablename__ = "ai_paper_jobs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending")
    stage = db.Column(db.String(64), nullable=False, default="pending")
    stage_index = db.Column(db.Integer, nullable=False, default=0)
    progress = db.Column(db.Integer, nullable=False, default=0)
    total_tasks = db.Column(db.Integer, nullable=False, default=0)
    completed_tasks = db.Column(db.Integer, nullable=False, default=0)
    config = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.Text, nullable=True)
    status_message = db.Column(db.Text, nullable=True)
    source_id = db.Column(db.Integer, db.ForeignKey("question_sources.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = db.relationship("QuestionSource", backref="ai_jobs", lazy=True)



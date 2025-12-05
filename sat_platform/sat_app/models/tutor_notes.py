from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class TutorNote(db.Model):
    """Daily AI-generated tutor notes cached per user."""

    __tablename__ = "coach_notes"  # legacy table name retained for compatibility
    __table_args__ = (
        db.UniqueConstraint("user_id", "plan_date", name="uq_coach_note_user_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan_date = db.Column(db.Date, nullable=False, index=True)
    language = db.Column(db.String(8), nullable=False, default="en")
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = db.relationship("User", backref="tutor_notes")


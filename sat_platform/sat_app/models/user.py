"""User domain models."""

from __future__ import annotations

from datetime import datetime, date, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(db.Model):
    """Application user (student or admin)."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(64), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="student")
    is_root = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    profile = db.relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.email} ({self.role})>"


class UserProfile(db.Model):
    """Extended preferences and study targets for a user."""

    __tablename__ = "user_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    target_score_rw = db.Column(db.Integer)
    target_score_math = db.Column(db.Integer)
    exam_date = db.Column(db.Date)
    daily_available_minutes = db.Column(db.Integer, default=60, nullable=False)
    language_preference = db.Column(db.String(20), default="bilingual", nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    user = db.relationship("User", back_populates="profile")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        date_str = self.exam_date.isoformat() if isinstance(self.exam_date, date) else "N/A"
        return f"<UserProfile user_id={self.user_id} exam_date={date_str}>"


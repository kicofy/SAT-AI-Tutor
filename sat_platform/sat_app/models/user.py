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
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    locked_reason = db.Column(db.String(255))
    locked_at = db.Column(db.DateTime(timezone=True))
    is_root = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    membership_expires_at = db.Column(db.DateTime(timezone=True))
    ai_explain_quota_date = db.Column(db.Date)
    ai_explain_quota_used = db.Column(db.Integer, nullable=False, default=0)
    is_email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_code = db.Column(db.String(12))
    email_verification_expires_at = db.Column(db.DateTime(timezone=True))
    email_verification_attempts = db.Column(db.Integer, nullable=False, default=0)
    email_verification_sent_at = db.Column(db.DateTime(timezone=True))
    email_verification_sent_count = db.Column(db.Integer, nullable=False, default=0)
    email_verification_sent_window_start = db.Column(db.DateTime(timezone=True))
    password_reset_token = db.Column(db.String(255))
    password_reset_requested_at = db.Column(db.DateTime(timezone=True))
    password_reset_expires_at = db.Column(db.DateTime(timezone=True))

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
    daily_plan_questions = db.Column(db.Integer, default=12, nullable=False)
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


class EmailVerificationTicket(db.Model):
    __tablename__ = "email_verification_tickets"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    purpose = db.Column(db.String(32), nullable=False, default="signup")
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    code = db.Column(db.String(12), nullable=False)
    language = db.Column(db.String(8), nullable=False, default="en")
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_sent_at = db.Column(db.DateTime(timezone=True))
    resend_count = db.Column(db.Integer, default=0, nullable=False)
    attempts = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<EmailVerificationTicket email={self.email} purpose={self.purpose}>"


class UserSubscriptionLog(db.Model):
    __tablename__ = "user_subscription_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), index=True, nullable=False)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(64), nullable=False)
    delta_days = db.Column(db.Integer, nullable=True)
    note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)



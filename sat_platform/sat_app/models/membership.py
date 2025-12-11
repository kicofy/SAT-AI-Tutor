from __future__ import annotations

from datetime import datetime, timezone

from ..extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class MembershipOrder(db.Model):
    __tablename__ = "membership_orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plan = db.Column(db.String(32), nullable=False)  # monthly, quarterly
    price_cents = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(8), nullable=False, default="USD")
    status = db.Column(db.String(16), nullable=False, default="pending")
    user_note = db.Column(db.String(255))
    admin_note = db.Column(db.String(255))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"))

    user = db.relationship("User", foreign_keys=[user_id], backref="membership_orders")
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<MembershipOrder id={self.id} user={self.user_id} plan={self.plan} status={self.status}>"


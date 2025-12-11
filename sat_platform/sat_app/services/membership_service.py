from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from flask import current_app

from ..extensions import db
from ..models import User, UserSubscriptionLog


class MembershipError(Exception):
    def __init__(self, code: str, payload: dict | None = None):
        super().__init__(code)
        self.code = code
        self.payload = payload or {}


class PlanAccessDenied(MembershipError):
    pass


class AiQuotaExceeded(MembershipError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(value: datetime | None) -> datetime | None:
    if not value:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _today() -> date:
    return _now().date()


def _trial_limit_days() -> int:
    return int(current_app.config.get("FREE_PLAN_TRIAL_DAYS", 7))


def _ai_quota_limit() -> int:
    return int(current_app.config.get("AI_EXPLAIN_FREE_DAILY_LIMIT", 5))


def is_member(user: User) -> bool:
    if user.role == "admin":
        return True
    expires = _coerce_aware(user.membership_expires_at)
    return bool(expires and expires > _now())


def describe_membership(user: User) -> dict:
    expires = _coerce_aware(user.membership_expires_at)
    status = {
        "is_member": is_member(user),
        "expires_at": expires.isoformat() if expires else None,
        "trial_days_total": _trial_limit_days(),
        "trial_days_used": 0,
        "trial_days_remaining": 0,
        "trial_active": False,
        "trial_expires_at": None,
    }
    created = user.created_at or _now()
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    delta = _now() - created
    days_used = max(delta.days, 0)
    status["trial_days_used"] = days_used
    remaining = max(_trial_limit_days() - days_used, 0)
    status["trial_days_remaining"] = remaining
    status["trial_active"] = not status["is_member"] and remaining > 0
    trial_end = created + timedelta(days=_trial_limit_days())
    status["trial_expires_at"] = trial_end.isoformat()
    return status


def ensure_plan_access(user: User) -> dict:
    status = describe_membership(user)
    if status["is_member"] or status["trial_active"]:
        return status
    raise PlanAccessDenied(
        "membership_required",
        {
            "membership": status,
            "message": "An active membership is required to use Today's Study Plan.",
        },
    )


def describe_ai_quota(user: User) -> dict:
    if is_member(user):
        return {"limit": None, "used": 0, "resets_at": None}
    today = _today()
    used = user.ai_explain_quota_used or 0
    if user.ai_explain_quota_date != today:
        used = 0
    resets_at = datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=timezone.utc)
    return {
        "limit": _ai_quota_limit(),
        "used": used,
        "resets_at": resets_at.isoformat(),
    }


def consume_ai_explain_quota(user: User) -> dict:
    quota = describe_ai_quota(user)
    if quota["limit"] is None:
        return quota
    today = _today()
    if user.ai_explain_quota_date != today:
        user.ai_explain_quota_date = today
        user.ai_explain_quota_used = 0
    if user.ai_explain_quota_used >= quota["limit"]:
        raise AiQuotaExceeded(
            "ai_explain_quota_exceeded",
            {
                "quota": quota,
                "message": "Daily AI explanation limit reached. Upgrade to continue.",
            },
        )
    user.ai_explain_quota_used += 1
    db.session.add(user)
    db.session.commit()
    return describe_ai_quota(user)


def extend_membership(user: User, days: int, operator_id: int | None = None, note: str | None = None) -> dict:
    if days <= 0:
        raise ValueError("days must be positive")
    now = _now()
    current = _coerce_aware(user.membership_expires_at)
    base = current if current and current > now else now
    user.membership_expires_at = base + timedelta(days=days)
    db.session.add(user)
    db.session.add(
        UserSubscriptionLog(
            user_id=user.id,
            operator_id=operator_id,
            action="extend",
            delta_days=days,
            note=note,
        )
    )
    db.session.commit()
    return describe_membership(user)


def set_membership_days(
    user: User, days: int | None, operator_id: int | None = None, note: str | None = None
) -> dict:
    if days is None:
        user.membership_expires_at = None
        action = "revoke"
    else:
        if days <= 0:
            raise ValueError("days must be greater than zero")
        user.membership_expires_at = _now() + timedelta(days=days)
        action = "set"
    db.session.add(user)
    db.session.add(
        UserSubscriptionLog(
            user_id=user.id,
            operator_id=operator_id,
            action=action,
            delta_days=days,
            note=note,
        )
    )
    db.session.commit()
    return describe_membership(user)


def log_membership_action(
    user: User,
    action: str,
    operator_id: int | None = None,
    delta_days: int | None = None,
    note: str | None = None,
) -> UserSubscriptionLog:
    entry = UserSubscriptionLog(
        user_id=user.id,
        operator_id=operator_id,
        action=action,
        delta_days=delta_days,
        note=note,
    )
    db.session.add(entry)
    db.session.commit()
    return entry


def get_membership_logs(user_id: int, limit: int = 50) -> list[dict]:
    logs = (
        UserSubscriptionLog.query.filter_by(user_id=user_id)
        .order_by(UserSubscriptionLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "action": log.action,
            "delta_days": log.delta_days,
            "note": log.note,
            "operator_id": log.operator_id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


def plan_definitions() -> dict[str, dict]:
    return {
        "monthly": {
            "days": current_app.config.get("MEMBERSHIP_MONTHLY_DAYS", 30),
            "price_cents": current_app.config.get("MEMBERSHIP_MONTHLY_PRICE_CENTS", 3900),
        },
        "quarterly": {
            "days": current_app.config.get("MEMBERSHIP_QUARTERLY_DAYS", 90),
            "price_cents": current_app.config.get("MEMBERSHIP_QUARTERLY_PRICE_CENTS", 9900),
        },
    }


def apply_plan(user: User, plan: str, operator_id: int | None = None, note: str | None = None) -> dict:
    definitions = plan_definitions()
    definition = definitions.get(plan)
    if not definition:
        raise ValueError(f"Unknown plan {plan}")
    return extend_membership(user, definition["days"], operator_id=operator_id, note=note or plan)


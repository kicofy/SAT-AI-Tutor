"""Daily progress aggregation for plans and streaks."""

from __future__ import annotations

from datetime import date, datetime, timedelta, time, timezone
from typing import Dict, Tuple

from sqlalchemy import func
from flask import current_app

from ..extensions import db
from ..models import StudyPlan, UserQuestionLog


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _config_defaults() -> Tuple[int, int, int]:
    cfg = current_app.config
    default_questions = int(cfg.get("PLAN_DEFAULT_QUESTIONS", 12))
    min_per_q = int(cfg.get("PLAN_MIN_PER_QUESTION", 5))
    default_minutes = int(cfg.get("PLAN_DEFAULT_MINUTES", default_questions * min_per_q))
    fallback_sec_per_q = int(cfg.get("PROGRESS_FALLBACK_SEC_PER_QUESTION", 90))
    return default_questions, default_minutes, fallback_sec_per_q


def _load_daily_activity(user_id: int, start_day: date, end_day: date) -> Dict[date, dict]:
    """Return per-day counts and seconds within [start_day, end_day]."""
    start_dt = datetime.combine(start_day, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_day + timedelta(days=1), time.min).replace(tzinfo=timezone.utc)

    rows = (
        db.session.query(
            func.date(UserQuestionLog.answered_at).label("day"),
            func.count(UserQuestionLog.id).label("count_all"),
            func.count(UserQuestionLog.time_spent_sec).label("count_timed"),
            func.coalesce(func.sum(UserQuestionLog.time_spent_sec), 0).label("sum_sec"),
        )
        .filter(
            UserQuestionLog.user_id == user_id,
            UserQuestionLog.answered_at >= start_dt,
            UserQuestionLog.answered_at < end_dt,
        )
        .group_by(func.date(UserQuestionLog.answered_at))
        .all()
    )
    activity: Dict[date, dict] = {}
    _, _, fallback_sec_per_q = _config_defaults()
    for row in rows:
        day_raw = row.day
        if isinstance(day_raw, str):
            try:
                day = date.fromisoformat(day_raw)
            except Exception:
                continue
        else:
            day = day_raw
        total = int(row.count_all or 0)
        timed = int(row.count_timed or 0)
        summed = int(row.sum_sec or 0)
        missing = max(total - timed, 0)
        seconds = summed + missing * fallback_sec_per_q
        activity[day] = {"questions": total, "seconds": seconds}
    return activity


def _plan_targets_by_day(user_id: int, start_day: date, end_day: date, default_q: int, default_m: int) -> Dict[date, Tuple[int, int]]:
    plans = (
        StudyPlan.query.filter(
            StudyPlan.user_id == user_id,
            StudyPlan.plan_date >= start_day,
            StudyPlan.plan_date <= end_day,
        ).all()
    )
    mapping: Dict[date, Tuple[int, int]] = {}
    for plan in plans:
        mapping[plan.plan_date] = (
            plan.target_questions or default_q,
            plan.target_minutes or default_m,
        )
    return mapping


def _is_day_complete(day: date, activity: Dict[date, dict], targets: Dict[date, Tuple[int, int]], default_q: int, default_m: int) -> bool:
    stats = activity.get(day, {"questions": 0, "seconds": 0})
    questions = stats["questions"]
    minutes = stats["seconds"] / 60.0 if stats["seconds"] else 0
    target_q, target_m = targets.get(day, (default_q, default_m))
    # 80% threshold on either questions or minutes
    return (questions >= 0.8 * target_q) or (minutes >= 0.8 * target_m)


def _streak_days(user_id: int, today: date, activity: Dict[date, dict], targets: Dict[date, Tuple[int, int]], default_q: int, default_m: int, lookback_days: int = 30) -> int:
    streak = 0
    for offset in range(0, lookback_days):
        day = today - timedelta(days=offset)
        if _is_day_complete(day, activity, targets, default_q, default_m):
            streak += 1
            continue
        # break at the first non-complete day
        if offset > 0:
            break
        # offset==0 (today) incomplete -> streak 0
        break
    return streak


def _next_goal(streak: int) -> int | None:
    goals = [3, 7, 14, 30]
    for g in goals:
        if streak < g:
            return g
    return None


def get_today_progress(user_id: int) -> dict:
    today = _today()
    default_q, default_m, _ = _config_defaults()

    # Load activity for lookback
    lookback_days = 30
    start_day = today - timedelta(days=lookback_days - 1)
    activity = _load_daily_activity(user_id, start_day, today)

    targets = _plan_targets_by_day(user_id, start_day, today, default_q, default_m)
    streak = _streak_days(user_id, today, activity, targets, default_q, default_m, lookback_days=lookback_days)
    next_goal = _next_goal(streak)

    today_stats = activity.get(today, {"questions": 0, "seconds": 0})
    today_plan_targets = targets.get(today, (default_q, default_m))
    completed_minutes = round(today_stats["seconds"] / 60, 2) if today_stats["seconds"] else 0

    last_active_day = None
    if activity:
        last_active_day = max(activity.keys())

    return {
        "plan_date": today.isoformat(),
        "target_questions": today_plan_targets[0],
        "target_minutes": today_plan_targets[1],
        "completed_questions": today_stats["questions"],
        "completed_minutes": completed_minutes,
        "streak_days": streak,
        "streak_next_goal": next_goal,
        "streak_goals": [3, 7, 14, 30],
        "last_active_day": last_active_day.isoformat() if isinstance(last_active_day, date) else None,
    }


"""Learning plan service generating daily study plans."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from typing import Dict, List, Tuple

from flask import current_app
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.exceptions import NotFound, BadRequest

from ..extensions import db
from ..models import (
    StudyPlan,
    StudyPlanTask,
    StudySession,
    User,
    UserProfile,
    UserQuestionLog,
    Question,
)
from .adaptive_engine import get_mastery_snapshot
from .skill_taxonomy import describe_skill

TASK_PENDING = "pending"
TASK_ACTIVE = "active"
TASK_COMPLETED = "completed"
TASK_EXPIRED = "expired"

PLAN_PROTOCOL_VERSION = "plan.v2"
RECENT_WINDOW_DAYS = 14


def _ensure_diagnostic_completed(user_id: int) -> None:
    from . import diagnostic_service  # local import to avoid circular dependency

    if diagnostic_service.requires_diagnostic(user_id):
        raise BadRequest("diagnostic_required")


def _resolve_today() -> date:
    return datetime.now(timezone.utc).date()


def _estimate_section_split(profile: UserProfile | None) -> Dict[str, float]:
    if not profile:
        return {"RW": 0.5, "Math": 0.5}
    target_rw = (profile.target_score_rw or 350) - 350
    target_math = (profile.target_score_math or 350) - 350
    total = max(target_rw + target_math, 1)
    rw_ratio = target_rw / total if total else 0.5
    return {"RW": rw_ratio, "Math": 1 - rw_ratio}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _days_since(value: str | None) -> int | None:
    dt = _parse_iso_datetime(value)
    if not dt:
        return None
    delta = datetime.now(timezone.utc) - dt
    return max(delta.days, 0)


def _resolve_language(profile: UserProfile | None) -> str:
    pref = (getattr(profile, "language_preference", "") or "").lower()
    if "zh" in pref or "cn" in pref:
        return "zh"
    return "en"


def _available_sections() -> set[str]:
    rows = (
        db.session.execute(
            db.select(Question.section, func.count(Question.id)).group_by(Question.section)
        ).all()
    )
    return {section for section, count in rows if count}


def _load_recent_skill_stats(user_id: int, window_days: int = RECENT_WINDOW_DAYS):
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    logs = (
        UserQuestionLog.query.options(joinedload(UserQuestionLog.question))
        .filter(UserQuestionLog.user_id == user_id)
        .filter(UserQuestionLog.answered_at >= cutoff)
        .order_by(UserQuestionLog.answered_at.desc())
        .limit(600)
        .all()
    )
    stats: Dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0, "last_answered": None})
    for log in logs:
        question = log.question
        if not question:
            continue
        tags = question.skill_tags or []
        for tag in tags:
            entry = stats[tag]
            entry["total"] += 1
            if log.is_correct:
                entry["correct"] += 1
            last_seen = entry.get("last_answered")
            if last_seen is None or log.answered_at > last_seen:
                entry["last_answered"] = log.answered_at
    return stats


def _collect_overdue_skills(user_id: int, today: date) -> set[str]:
    if not StudyPlanTask.query.filter_by(user_id=user_id).first():
        return set()
    previous_day = today - timedelta(days=1)
    tasks = StudyPlanTask.query.filter(
        StudyPlanTask.user_id == user_id,
        StudyPlanTask.plan_date == previous_day,
    ).all()
    overdue = set()
    for task in tasks:
        if task.status != TASK_COMPLETED and task.focus_skill:
            overdue.add(task.focus_skill)
    return overdue


def _completion_ratio(user_id: int, today: date) -> float | None:
    previous_day = today - timedelta(days=1)
    tasks = StudyPlanTask.query.filter(
        StudyPlanTask.user_id == user_id,
        StudyPlanTask.plan_date == previous_day,
    ).all()
    if not tasks:
        return None
    total = len(tasks)
    completed = len([task for task in tasks if task.status == TASK_COMPLETED])
    if total == 0:
        return None
    return completed / total


def _adjust_minutes_for_history(user_id: int, base_minutes: int, today: date) -> int:
    ratio = _completion_ratio(user_id, today)
    minutes = base_minutes
    if ratio is not None:
        if ratio < 0.5:
            minutes = max(30, int(minutes * 0.85))
        elif ratio > 0.9:
            minutes = min(150, int(minutes * 1.1))
    return minutes


def _score_skill(
    skill: dict,
    section_bias: float,
    recent_stats: dict,
    overdue_skills: set[str],
    recency_days: int | None,
    language: str,
) -> Tuple[float, List[str], float | None]:
    mastery_gap = max(0.0, 1 - skill.get("mastery_score", 0.0))
    recency_norm = 1.0
    if recency_days is not None:
        recency_norm = min(recency_days / 10, 1)
    stats = recent_stats.get(skill["skill_tag"])
    recent_accuracy = None
    accuracy_gap = 0.4
    if stats and stats["total"]:
        recent_accuracy = stats["correct"] / stats["total"]
        accuracy_gap = max(0.0, 1 - recent_accuracy)
    overdue_bonus = 0.2 if skill["skill_tag"] in overdue_skills else 0.0
    priority = (
        mastery_gap * 0.45
        + recency_norm * 0.2
        + accuracy_gap * 0.2
        + section_bias * 0.1
        + overdue_bonus
    )
    reasons: List[str] = []
    mastery_pct = skill.get("mastery_score", 0) * 100
    if mastery_pct < 75:
        if language == "zh":
            reasons.append(f"掌握度仅 {mastery_pct:.0f}%")
        else:
            reasons.append(f"Mastery only {mastery_pct:.0f}%")
    if recency_days is None or recency_days >= 5:
        if language == "zh":
            reasons.append(f"{recency_days or '多'} 天未练")
        else:
            value = recency_days if recency_days is not None else "many"
            reasons.append(f"Last practiced {value} days ago")
    if recent_accuracy is not None and recent_accuracy < 0.8:
        if language == "zh":
            reasons.append(f"最近正确率 {recent_accuracy * 100:.0f}%")
        else:
            reasons.append(f"Recent accuracy {recent_accuracy * 100:.0f}%")
    if skill["skill_tag"] in overdue_skills:
        reasons.append("上一日未完成，需要补课" if language == "zh" else "Missed yesterday's block")
    return priority, reasons, recent_accuracy


def _compose_strategy_tips(
    label: str,
    descriptor: dict,
    block_minutes: int,
    questions: int,
    recency_days: int | None,
    recent_accuracy: float | None,
    language: str,
) -> List[str]:
    tips: List[str] = []
    descriptor_text = descriptor.get("description", "")[:40]
    if language == "zh":
        tips.append(f"热身：用 2 分钟复盘 {label} 的核心方法，关注 {descriptor_text}。")
        if recency_days and recency_days >= 7:
            tips.append(f"因为已有 {recency_days} 天未练，前 {max(1, questions // 3)} 题放慢速度，确保审题完整。")
        elif recent_accuracy is not None and recent_accuracy < 0.75:
            tips.append("上一轮正确率偏低，提交答案前检查关键证据或计算步骤。")
        else:
            tips.append("保持节奏：每完成一题立刻写下 5 秒反思，记录易错点。")
        tips.append(f"目标：{block_minutes} 分钟内攻克 {questions} 题，并挑出至少 1 个错题做深度复盘。")
    else:
        tips.append(f"Warm-up: spend 2 minutes recalling {label} tactics, especially {descriptor_text}.")
        if recency_days and recency_days >= 7:
            tips.append(
                f"It's been {recency_days} days—slow down for the first {max(1, questions // 3)} questions and read carefully."
            )
        elif recent_accuracy is not None and recent_accuracy < 0.75:
            tips.append("Accuracy was low last time—double-check evidence or calculations before submitting.")
        else:
            tips.append("Keep pace: after each question jot a 5-second note about your reasoning.")
        tips.append(
            f"Goal: finish {questions} questions in {block_minutes} minutes and pick at least one miss for deep review."
        )
    return tips


def _build_blocks_v2(
    user_id: int,
    total_minutes: int,
    mastery: List[dict],
    section_split: Dict[str, float],
    today: date,
    language: str,
) -> Tuple[List[dict], dict]:
    slot_minutes = current_app.config.get("PLAN_BLOCK_MINUTES", 25)
    review_minutes = current_app.config.get("PLAN_REVIEW_MINUTES", 12)
    minutes_per_question = current_app.config.get("PLAN_MIN_PER_QUESTION", 5)
    section_targets = {
        "RW": int(total_minutes * section_split.get("RW", 0.5)),
        "Math": total_minutes,
    }
    section_targets["Math"] = max(0, total_minutes - section_targets["RW"])
    section_assigned = {"RW": 0, "Math": 0, "mixed": 0}
    minutes_remaining = total_minutes

    available_sections = _available_sections()
    recent_stats = _load_recent_skill_stats(user_id)
    overdue_skills = _collect_overdue_skills(user_id, today)

    priorities = []
    for skill in mastery:
        descriptor = describe_skill(skill["skill_tag"])
        domain = skill.get("domain") or descriptor["domain"]
        focus_section = "RW" if domain == "Reading & Writing" else "Math"
        recency_days = _days_since(skill.get("last_practiced_at"))
        section_bias = section_split.get(focus_section, 0.5)
        priority, reasons, recent_accuracy = _score_skill(
            skill, section_bias, recent_stats, overdue_skills, recency_days, language
        )
        priorities.append(
            {
                "skill": skill,
                "descriptor": descriptor,
                "section": focus_section,
                "domain": domain,
                "priority": priority,
                "reasons": reasons,
                "recency_days": recency_days,
                "recent_accuracy": recent_accuracy,
            }
        )

    priorities.sort(key=lambda entry: entry["priority"], reverse=True)
    blocks: List[dict] = []
    total_questions = 0
    overdue_labels = []

    for entry in priorities:
        if minutes_remaining <= 0:
            break
        section = entry["section"]
        if available_sections and section not in available_sections:
            continue
        section_deficit = max(section_targets.get(section, 0) - section_assigned.get(section, 0), 0)
        block_minutes = min(slot_minutes, minutes_remaining)
        if section_deficit > 0:
            block_minutes = min(block_minutes, max(section_deficit, slot_minutes // 2))
        if block_minutes <= 0:
            continue
        questions = max(round(block_minutes / minutes_per_question), 1)
        total_questions += questions
        focus_label = entry["skill"].get("label") or entry["descriptor"]["label"]
        strategy_tips = _compose_strategy_tips(
            focus_label,
            entry["descriptor"],
            block_minutes,
            questions,
            entry["recency_days"],
            entry["recent_accuracy"],
            language,
        )
        default_note = "自适应推荐" if language == "zh" else "AI prioritized skill"
        blocks.append(
            {
                "focus_skill": entry["skill"]["skill_tag"],
                "focus_skill_label": focus_label,
                "domain": entry["domain"],
                "section": section,
                "minutes": block_minutes,
                "questions": questions,
                "notes": entry["reasons"][0] if entry["reasons"] else default_note,
                "priority_score": round(entry["priority"], 3),
                "strategy_tips": strategy_tips,
                "reasons": entry["reasons"],
                "mastery_score": entry["skill"].get("mastery_score"),
                "recency_days": entry["recency_days"],
                "recent_accuracy": entry["recent_accuracy"],
            }
        )
        minutes_remaining -= block_minutes
        section_assigned[section] = section_assigned.get(section, 0) + block_minutes
        if entry["skill"]["skill_tag"] in overdue_skills:
            overdue_labels.append(focus_label)

    if minutes_remaining > 0:
        review_minutes = min(review_minutes, minutes_remaining)
        review_questions = max(round(review_minutes / minutes_per_question), 1)
        total_questions += review_questions
        review_section = (
            "RW"
            if (section_targets.get("RW", 0) - section_assigned.get("RW", 0))
            >= (section_targets.get("Math", 0) - section_assigned.get("Math", 0))
            else "Math"
        )
        if available_sections:
            if review_section not in available_sections:
                review_section = next(iter(available_sections))
        mixed_label = "错题回顾" if language == "zh" else "Mixed Review"
        mixed_tips = (
            [
                "优先复盘昨日错题，写出错因和改进步骤。",
                "若时间允许，抽取旧题重新作答并检查是否真正掌握。",
            ]
            if language == "zh"
            else [
                "Start with yesterday's misses—write the error and fix.",
                "If time remains, redo an older problem to confirm mastery.",
            ]
        )
        mixed_note = "巩固高频错题" if language == "zh" else "Consolidate frequent misses"
        blocks.append(
            {
                "focus_skill": "mixed_review",
                "focus_skill_label": mixed_label,
                "domain": "Mixed",
                "section": review_section,
                "minutes": review_minutes,
                "questions": review_questions,
                "notes": mixed_note,
                "strategy_tips": mixed_tips,
            }
        )
        minutes_remaining -= review_minutes
        section_assigned[review_section] = section_assigned.get(review_section, 0) + review_minutes
        section_assigned["mixed"] += review_minutes

    if language == "zh":
        insights = [
            f"今日目标：{total_minutes} 分钟 · {total_questions} 题",
            f"RW/Math 分配：{section_assigned['RW']} / {section_assigned['Math']} 分钟",
        ]
        if overdue_labels:
            insights.append(f"补课技能：{'、'.join(overdue_labels[:3])}")
    else:
        insights = [
            f"Today's goal: {total_minutes} min · {total_questions} questions",
            f"RW/Math split: {section_assigned['RW']} / {section_assigned['Math']} min",
        ]
        if overdue_labels:
            insights.append(f"Catch-up skills: {', '.join(overdue_labels[:3])}")

    summary = {
        "total_questions": total_questions,
        "section_minutes_target": section_targets,
        "section_minutes_assigned": section_assigned,
        "insights": insights,
    }
    return blocks, summary


def generate_daily_plan(user_id: int, plan_date: date | None = None) -> StudyPlan:
    today = plan_date or _resolve_today()
    _ensure_diagnostic_completed(user_id)
    _expire_previous_tasks(user_id, today)
    plan = StudyPlan.query.filter_by(user_id=user_id, plan_date=today).first()
    user = db.session.get(User, user_id)
    if not user:
        raise NotFound(f"User {user_id} not found")
    profile = user.profile

    language = _resolve_language(profile)
    minutes_per_question = current_app.config.get("PLAN_MIN_PER_QUESTION", 5)
    default_questions = current_app.config.get("PLAN_DEFAULT_QUESTIONS", 12)
    plan_question_pref = getattr(profile, "daily_plan_questions", None) if profile else None
    masteries = get_mastery_snapshot(user_id)
    if plan_question_pref:
        base_minutes = max(plan_question_pref * minutes_per_question, minutes_per_question)
        total_minutes = base_minutes
    else:
        base_minutes = (
            profile.daily_available_minutes
            if profile
            else current_app.config.get("PLAN_DEFAULT_MINUTES", 60)
        )
        total_minutes = _adjust_minutes_for_history(user_id, base_minutes, today)
    section_split = _estimate_section_split(profile)
    blocks, summary = _build_blocks_v2(user_id, total_minutes, masteries, section_split, today, language)
    target_questions = summary["total_questions"]

    detail = {
        "protocol_version": PLAN_PROTOCOL_VERSION,
        "plan_date": today.isoformat(),
        "target_minutes": total_minutes,
        "target_questions": target_questions,
        "blocks": blocks,
        "section_split": section_split,
        "allocation": {
            "section_minutes_target": summary["section_minutes_target"],
            "section_minutes_assigned": summary["section_minutes_assigned"],
        },
        "insights": summary["insights"],
    }

    if plan is None:
        plan = StudyPlan(
            user_id=user_id,
            plan_date=today,
            target_minutes=total_minutes,
            target_questions=target_questions,
            generated_detail=detail,
        )
        db.session.add(plan)
    else:
        plan.target_minutes = total_minutes
        plan.target_questions = target_questions
        plan.generated_detail = detail
        plan.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    _ensure_plan_tasks(plan)
    return plan


def get_or_generate_plan(user_id: int, plan_date: date | None = None) -> StudyPlan:
    _ensure_diagnostic_completed(user_id)
    plan = StudyPlan.query.filter_by(user_id=user_id, plan_date=plan_date or _resolve_today()).first()
    if plan:
        _ensure_plan_tasks(plan)
        return plan
    return generate_daily_plan(user_id, plan_date)


def get_plan_with_tasks(
    user_id: int, plan_date: date | None = None
) -> Tuple[StudyPlan, List[dict]]:
    _ensure_diagnostic_completed(user_id)
    plan = get_or_generate_plan(user_id, plan_date)
    tasks = (
        StudyPlanTask.query.filter_by(user_id=user_id, plan_date=plan.plan_date)
        .order_by(StudyPlanTask.id.asc())
        .all()
    )
    if tasks:
        from . import session_service  # local import to avoid circular dependency

        for task in tasks:
            session = task.session
            if session and session.ended_at is None:
                session_service.refresh_assigned_questions(session)
    return plan, [serialize_task(task) for task in tasks]


def start_plan_task(user_id: int, block_id: str) -> Tuple[StudySession, dict]:
    from . import session_service  # local import to avoid circular dependency

    _ensure_diagnostic_completed(user_id)
    plan, task, block = _resolve_plan_task(user_id, block_id)
    session = task.session
    if session and session.ended_at is None:
        session_service.refresh_assigned_questions(session)
        _ensure_session_question_target(session, task, block)
        return session, serialize_task(task)

    questions = _select_questions_for_block(user_id, block, plan.plan_date, block.get("block_id"))
    if not questions:
        raise BadRequest("No questions available for this block")

    session = _create_plan_session(user_id, questions, block["block_id"])
    session_service.refresh_assigned_questions(session)
    _ensure_session_question_target(session, task, block)
    task.session_id = session.id
    task.status = TASK_ACTIVE
    task.started_at = task.started_at or datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    return session, serialize_task(task)


def serialize_task(task: StudyPlanTask) -> dict:
    session = task.session
    completed = 0
    if session and session.questions_done:
        completed = len([entry for entry in session.questions_done if entry.get("log_id")])
    status = task.status
    if session and session.ended_at and status == TASK_ACTIVE:
        status = TASK_COMPLETED
    return {
        "block_id": task.block_id,
        "status": status,
        "questions_target": task.questions_target,
        "questions_completed": min(completed, task.questions_target),
        "session_id": task.session_id,
        "plan_date": task.plan_date.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }


def handle_session_end(session: StudySession) -> None:
    if not session.plan_block_id:
        return
    task = _find_task_by_block(session.user_id, session.plan_block_id)
    if not task:
        return
    task.status = TASK_COMPLETED
    task.completed_at = datetime.now(timezone.utc)
    task.updated_at = datetime.now(timezone.utc)
    task.session_id = session.id
    db.session.commit()


def handle_session_abort(session: StudySession) -> None:
    if not session.plan_block_id:
        return
    task = _find_task_by_block(session.user_id, session.plan_block_id)
    if not task or task.status == TASK_COMPLETED:
        return
    task.status = TASK_PENDING
    task.session_id = None
    task.updated_at = datetime.now(timezone.utc)
    db.session.commit()


def _ensure_plan_tasks(plan: StudyPlan) -> None:
    original_detail = plan.generated_detail or {}
    blocks = original_detail.get("blocks") or []
    updated_blocks: List[dict] = []
    updated = False
    for idx, block in enumerate(blocks):
        mutable_block = dict(block)
        if "block_id" not in mutable_block:
            mutable_block["block_id"] = f"{plan.plan_date.isoformat()}-{idx}"
            updated = True
        updated_blocks.append(mutable_block)
    if updated:
        detail = dict(original_detail)
        detail["blocks"] = updated_blocks
        plan.generated_detail = detail
        db.session.commit()
    else:
        detail = original_detail

    existing = {
        task.block_id: task
        for task in StudyPlanTask.query.filter_by(user_id=plan.user_id, plan_date=plan.plan_date)
    }
    for block in (detail.get("blocks") or []):
        block_id = block["block_id"]
        if block_id in existing:
            continue
        task = StudyPlanTask(
            user_id=plan.user_id,
            plan_date=plan.plan_date,
            block_id=block_id,
            section=_normalize_section(block.get("section")),
            focus_skill=block.get("focus_skill"),
            questions_target=block.get("questions", 0) or 0,
            status=TASK_PENDING,
        )
        db.session.add(task)
    db.session.commit()


def _expire_previous_tasks(user_id: int, today: date) -> None:
    stale_tasks = (
        StudyPlanTask.query.filter(
            StudyPlanTask.user_id == user_id,
            StudyPlanTask.plan_date < today,
            StudyPlanTask.status.in_([TASK_PENDING, TASK_ACTIVE]),
        ).all()
    )
    if not stale_tasks:
        return
    from . import session_service  # local import to avoid circular dependency

    for task in stale_tasks:
        if task.session_id:
            session = StudySession.query.filter_by(id=task.session_id).first()
            if session and session.ended_at is None:
                session_service.abort_session(session)
        task.status = TASK_EXPIRED
        task.session_id = None
        task.updated_at = datetime.now(timezone.utc)
    db.session.commit()


def _resolve_plan_task(user_id: int, block_id: str):
    plan = get_or_generate_plan(user_id)
    task = _find_task_by_block(user_id, block_id, plan.plan_date)
    if not task:
        raise NotFound("Plan task not found")
    block = _find_block(plan, block_id)
    if not block:
        raise NotFound("Plan block not found")
    return plan, task, block


def _find_block(plan: StudyPlan, block_id: str | None) -> dict | None:
    if not block_id:
        return None
    for block in (plan.generated_detail or {}).get("blocks", []):
        if block.get("block_id") == block_id:
            return block
    return None


def _find_task_by_block(user_id: int, block_id: str, plan_date: date | None = None):
    query = StudyPlanTask.query.filter_by(user_id=user_id, block_id=block_id)
    if plan_date:
        query = query.filter_by(plan_date=plan_date)
    return query.first()


def _collect_plan_question_ids(
    user_id: int,
    plan_date: date,
    exclude_block_id: str | None = None,
) -> set[int]:
    question_ids: set[int] = set()
    tasks = StudyPlanTask.query.filter_by(user_id=user_id, plan_date=plan_date).all()
    for task in tasks:
        if exclude_block_id and task.block_id == exclude_block_id:
            continue
        session = task.session
        if not session:
            continue
        for assigned in session.questions_assigned or []:
            question_id = assigned.get("question_id")
            if question_id:
                question_ids.add(int(question_id))
    return question_ids


def _select_questions_for_block(
    user_id: int,
    block: dict,
    plan_date: date,
    block_id: str | None,
) -> List:
    section = _normalize_section(block.get("section"))
    focus_skill = block.get("focus_skill")
    num_questions = block.get("questions") or 5
    from . import session_service  # local import to avoid circular dependency

    exclude_ids = _collect_plan_question_ids(user_id, plan_date, block_id)
    return session_service.select_questions(
        user_id=user_id,
        num_questions=num_questions,
        section=section,
        focus_skill=focus_skill,
        exclude_ids=exclude_ids,
    )


def _create_plan_session(user_id: int, questions: List, plan_block_id: str) -> StudySession:
    from . import session_service  # local import to avoid circular dependency

    return session_service.create_session(
        user_id=user_id,
        questions=questions,
        plan_block_id=plan_block_id,
        session_type="plan",
    )


def _normalize_section(section: str | None) -> str | None:
    if not section:
        return None
    normalized = section.upper()
    if normalized in {"RW", "MATH"}:
        return normalized
    return None


def _ensure_session_question_target(session: StudySession, task: StudyPlanTask, block: dict) -> None:
    from . import session_service  # local import to avoid circular dependency

    target = task.questions_target or block.get("questions") or len(session.questions_assigned or [])
    assigned = session.questions_assigned or []
    deficit = max(target - len(assigned), 0)
    if deficit <= 0:
        return

    existing_ids = {
        entry.get("question_id")
        for entry in assigned
        if entry.get("question_id")
    }

    additions: List[dict] = []
    attempts = 0
    section = _normalize_section(block.get("section"))
    focus_skill = block.get("focus_skill")

    while deficit > 0 and attempts < 3:
        attempts += 1
        candidates = session_service.select_questions(
            user_id=session.user_id,
            num_questions=deficit,
            section=section,
            focus_skill=focus_skill,
        )
        if not candidates:
            break
        for question in candidates:
            if question.id in existing_ids:
                continue
            serialized = session_service.serialize_question(question)
            additions.append(serialized)
            existing_ids.add(question.id)
            deficit -= 1
            if deficit <= 0:
                break

    if additions:
        session.questions_assigned = assigned + additions
        flag_modified(session, "questions_assigned")
        db.session.commit()


"""Learning plan service generating daily study plans."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Dict, List

from flask import current_app
from werkzeug.exceptions import NotFound

from ..extensions import db
from ..models import StudyPlan, User, UserProfile
from .adaptive_engine import get_mastery_snapshot
from .skill_taxonomy import describe_skill


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


def _build_blocks(total_minutes: int, mastery: List[dict], section_split: Dict[str, float]) -> List[dict]:
    minutes_remaining = total_minutes
    blocks: List[dict] = []
    slot_minutes = current_app.config.get("PLAN_BLOCK_MINUTES", 25)
    review_minutes = current_app.config.get("PLAN_REVIEW_MINUTES", 10)

    ordered_skills = sorted(mastery, key=lambda m: (m["mastery_score"], m["skill_tag"]))

    for skill in ordered_skills:
        if minutes_remaining <= 0:
            break
        focus_tag = skill["skill_tag"]
        descriptor = describe_skill(focus_tag)
        domain = skill.get("domain") or descriptor["domain"]
        focus_section = "RW" if domain == "Reading & Writing" else "Math"
        focus_label = skill.get("label") or descriptor["label"]
        block_minutes = min(slot_minutes, minutes_remaining)
        blocks.append(
            {
                "focus_skill": focus_tag,
                "focus_skill_label": focus_label,
                "domain": domain,
                "section": focus_section,
                "minutes": block_minutes,
                "questions": max(round(block_minutes / 5), 1),
                "notes": "Target low mastery skill",
            }
        )
        minutes_remaining -= block_minutes

    if minutes_remaining > 0 and mastery:
        blocks.append(
            {
                "focus_skill": "review",
                "focus_skill_label": "Mixed Review",
                "domain": "Mixed",
                "section": "mixed",
                "minutes": min(minutes_remaining, review_minutes),
                "questions": 3,
                "notes": "Review flagged questions",
            }
        )

    return blocks


def generate_daily_plan(user_id: int, plan_date: date | None = None) -> StudyPlan:
    today = plan_date or _resolve_today()
    plan = StudyPlan.query.filter_by(user_id=user_id, plan_date=today).first()
    user = db.session.get(User, user_id)
    if not user:
        raise NotFound(f"User {user_id} not found")
    profile = user.profile

    masteries = get_mastery_snapshot(user_id)
    total_minutes = profile.daily_available_minutes if profile else current_app.config.get("PLAN_DEFAULT_MINUTES", 60)
    target_questions = max(round(total_minutes / 5), 5)
    section_split = _estimate_section_split(profile)
    blocks = _build_blocks(total_minutes, masteries, section_split)

    detail = {
        "protocol_version": "plan.v1",
        "plan_date": today.isoformat(),
        "target_minutes": total_minutes,
        "target_questions": target_questions,
        "blocks": blocks,
        "section_split": section_split,
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
    return plan


def get_or_generate_plan(user_id: int, plan_date: date | None = None) -> StudyPlan:
    plan = StudyPlan.query.filter_by(user_id=user_id, plan_date=plan_date or _resolve_today()).first()
    if plan:
        return plan
    return generate_daily_plan(user_id, plan_date)


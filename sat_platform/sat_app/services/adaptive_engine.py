"""Adaptive engine for mastery tracking and question selection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from flask import current_app

from ..extensions import db
from ..models import Question, SkillMastery, UserQuestionLog
from . import spaced_repetition


def _initial_mastery() -> float:
    return float(current_app.config.get("ADAPTIVE_DEFAULT_MASTERY", 0.5))


def _get_increment(correct: bool) -> float:
    key = "ADAPTIVE_CORRECT_INCREMENT" if correct else "ADAPTIVE_INCORRECT_DECREMENT"
    return float(current_app.config.get(key, 0.05 if correct else 0.1))


def load_user_mastery(user_id: int) -> Dict[str, SkillMastery]:
    records = SkillMastery.query.filter_by(user_id=user_id).all()
    return {record.skill_tag: record for record in records}


def get_mastery_snapshot(user_id: int) -> list[dict]:
    records = (
        SkillMastery.query.filter_by(user_id=user_id)
        .order_by(SkillMastery.mastery_score.asc())
        .all()
    )
    return [
        {
            "skill_tag": record.skill_tag,
            "mastery_score": record.mastery_score,
            "success_streak": record.success_streak,
            "last_practiced_at": record.last_practiced_at.isoformat() if record.last_practiced_at else None,
        }
        for record in records
    ]


def _ensure_mastery(user_id: int, skill_tag: str) -> SkillMastery:
    mastery = SkillMastery.query.filter_by(user_id=user_id, skill_tag=skill_tag).first()
    if mastery is None:
        mastery = SkillMastery(
            user_id=user_id,
            skill_tag=skill_tag,
            mastery_score=_initial_mastery(),
        )
        db.session.add(mastery)
        db.session.flush()
    return mastery


def update_mastery_from_log(log_entry: UserQuestionLog, question: Question) -> None:
    skill_tags = question.skill_tags or []
    if not skill_tags:
        return

    now = datetime.now(timezone.utc)
    increment = _get_increment(correct=True)
    decrement = _get_increment(correct=False)

    for tag in skill_tags:
        mastery = _ensure_mastery(log_entry.user_id, tag)
        if log_entry.is_correct:
            mastery.mastery_score = min(1.0, mastery.mastery_score + increment)
            mastery.success_streak += 1
        else:
            mastery.mastery_score = max(0.0, mastery.mastery_score - decrement)
            mastery.success_streak = 0
        mastery.last_practiced_at = now
        mastery.due_at = None
        db.session.add(mastery)
    db.session.flush()


def _score_question(question: Question, mastery_map: Dict[str, SkillMastery]) -> float:
    tags = question.skill_tags or []
    if not tags:
        return _initial_mastery()

    now = datetime.now(timezone.utc)
    total = 0.0
    for tag in tags:
        mastery = mastery_map.get(tag)
        score = mastery.mastery_score if mastery else _initial_mastery()
        if mastery and mastery.last_practiced_at:
            days_since = (now - mastery.last_practiced_at).total_seconds() / 86400
            recency_penalty = min(days_since * 0.01, 0.1)
            score -= recency_penalty
        total += score
    return total / len(tags)


def select_next_questions(user_id: int, num_questions: int, section: str | None = None) -> List[Question]:
    selected: List[Question] = []
    seen_ids: set[int] = set()

    due_questions = spaced_repetition.get_due_questions(user_id, limit=num_questions, section=section)
    for q in due_questions:
        if q.id in seen_ids:
            continue
        selected.append(q)
        seen_ids.add(q.id)
        if len(selected) >= num_questions:
            return selected

    mastery_map = load_user_mastery(user_id)
    query = Question.query
    if section:
        query = query.filter_by(section=section)
    candidates = query.all()

    scored = []
    for question in candidates:
        if question.id in seen_ids:
            continue
        scored.append((_score_question(question, mastery_map), question.id, question))

    scored.sort(key=lambda entry: (entry[0], entry[1]))

    for _, _, question in scored:
        selected.append(question)
        seen_ids.add(question.id)
        if len(selected) >= num_questions:
            break

    if len(selected) < num_questions:
        remaining = num_questions - len(selected)
        fallback = query.filter(~Question.id.in_(seen_ids)).limit(remaining).all()
        for question in fallback:
            if question.id not in seen_ids:
                selected.append(question)
                seen_ids.add(question.id)
                if len(selected) >= num_questions:
                    break

    return selected


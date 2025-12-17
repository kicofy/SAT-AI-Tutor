"""Adaptive engine for mastery tracking and question selection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List

from flask import current_app

from ..extensions import db
from ..models import Question, SkillMastery, UserQuestionLog
from . import spaced_repetition
from .skill_taxonomy import canonicalize_tag, canonicalize_tags, describe_skill, iter_skill_tags


def _initial_mastery() -> float:
    return float(current_app.config.get("ADAPTIVE_DEFAULT_MASTERY", 0.5))


def _get_increment(correct: bool) -> float:
    key = "ADAPTIVE_CORRECT_INCREMENT" if correct else "ADAPTIVE_INCORRECT_DECREMENT"
    return float(current_app.config.get(key, 0.05 if correct else 0.1))


def load_user_mastery(user_id: int) -> Dict[str, SkillMastery]:
    records = SkillMastery.query.filter_by(user_id=user_id).all()
    normalized: Dict[str, SkillMastery] = {}
    duplicates: List[SkillMastery] = []
    renames: List[tuple[SkillMastery, str]] = []

    for record in records:
        canonical = canonicalize_tag(record.skill_tag)
        if not canonical:
            duplicates.append(record)
            continue

        survivor = normalized.get(canonical)
        if survivor is None:
            normalized[canonical] = record
            if record.skill_tag != canonical:
                renames.append((record, canonical))
            continue

        survivor.mastery_score = (survivor.mastery_score + record.mastery_score) / 2
        survivor.success_streak = max(survivor.success_streak, record.success_streak)
        if record.last_practiced_at and (
            not survivor.last_practiced_at or record.last_practiced_at > survivor.last_practiced_at
        ):
            survivor.last_practiced_at = record.last_practiced_at
        duplicates.append(record)

    if duplicates:
        for record in duplicates:
            db.session.delete(record)
        db.session.flush()

    if renames:
        for record, canonical in renames:
            record.skill_tag = canonical
        db.session.flush()

    return normalized


def get_mastery_snapshot(user_id: int) -> list[dict]:
    mastery_map = load_user_mastery(user_id)
    aggregates = {
        tag: {"score_sum": 0.0, "count": 0, "success_streak": 0, "last": None}
        for tag in iter_skill_tags()
    }

    for tag, record in mastery_map.items():
        bucket = aggregates.setdefault(tag, {"score_sum": 0.0, "count": 0, "success_streak": 0, "last": None})
        bucket["score_sum"] += record.mastery_score
        bucket["count"] += 1
        bucket["success_streak"] = max(bucket["success_streak"], record.success_streak)
        if record.last_practiced_at and (
            bucket["last"] is None or record.last_practiced_at > bucket["last"]
        ):
            bucket["last"] = record.last_practiced_at

    snapshot: List[dict] = []
    for tag in iter_skill_tags():
        bucket = aggregates[tag]
        meta = describe_skill(tag)
        count = bucket["count"]
        observed_score = bucket["score_sum"] / count if count else None
        fallback_score = observed_score if observed_score is not None else _initial_mastery()
        snapshot.append(
            {
                "skill_tag": tag,
                "label": meta["label"],
                "domain": meta["domain"],
                "description": meta["description"],
                "mastery_score": fallback_score,
                "observed_score": observed_score,
                "has_data": bool(count),
                "sample_count": count,
                "success_streak": bucket["success_streak"] if count else 0,
                "last_practiced_at": bucket["last"].isoformat() if bucket["last"] else None,
            }
        )
    return snapshot


def _ensure_mastery(user_id: int, skill_tag: str) -> SkillMastery:
    mastery = SkillMastery.query.filter_by(user_id=user_id, skill_tag=skill_tag).first()
    if mastery is not None:
        return mastery

    legacy_records = SkillMastery.query.filter_by(user_id=user_id).all()
    for record in legacy_records:
        if canonicalize_tag(record.skill_tag) == skill_tag:
            record.skill_tag = skill_tag
            db.session.flush()
            return record

    mastery = SkillMastery(
        user_id=user_id,
        skill_tag=skill_tag,
        mastery_score=_initial_mastery(),
    )
    db.session.add(mastery)
    db.session.flush()
    return mastery


def _question_skill_tags(question: Question) -> List[str]:
    raw = question.skill_tags
    if isinstance(raw, list):
        source = raw
    elif isinstance(raw, str):
        source = [raw]
    else:
        source = []
    return canonicalize_tags(source, limit=None)


def update_mastery_from_log(log_entry: UserQuestionLog, question: Question) -> None:
    skill_tags = _question_skill_tags(question)
    if not skill_tags:
        return

    now = datetime.now(timezone.utc)
    increment = _get_increment(correct=True)
    decrement = _get_increment(correct=False)

    question.skill_tags = skill_tags

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


def _score_question(
    question: Question,
    mastery_map: Dict[str, SkillMastery],
    summary_bias: Dict[str, float],
) -> float:
    tags = _question_skill_tags(question)
    if not tags:
        return _initial_mastery()

    now = datetime.now(timezone.utc)
    total = 0.0
    for tag in tags:
        mastery = mastery_map.get(tag)
        score = mastery.mastery_score if mastery else _initial_mastery()
        if mastery and mastery.last_practiced_at:
            last = mastery.last_practiced_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            days_since = (now - last).total_seconds() / 86400
            recency_penalty = min(days_since * 0.01, 0.1)
            score -= recency_penalty
        score -= summary_bias.get(tag, 0.0)
        total += score
    return total / len(tags)


def select_next_questions(
    user_id: int,
    num_questions: int,
    section: str | None = None,
    *,
    focus_skill: str | None = None,
    include_due: bool = True,
    last_summary: dict | None = None,
) -> List[Question]:
    selected: List[Question] = []
    seen_ids: set[int] = set()

    if include_due:
        due_questions = spaced_repetition.get_due_questions(
            user_id, limit=num_questions, section=section, focus_skill=focus_skill
        )
        for q in due_questions:
            if q.id in seen_ids:
                continue
            selected.append(q)
            seen_ids.add(q.id)
            if len(selected) >= num_questions:
                return selected

    mastery_map = load_user_mastery(user_id)
    summary_bias = _build_summary_bias(last_summary)
    query = Question.query
    if section:
        query = query.filter_by(section=section)
    base_query = query
    if focus_skill:
        skill_filtered = query.filter(Question.skill_tags.contains([focus_skill]))
        candidates = skill_filtered.all()
        if not candidates:
            candidates = base_query.all()
        else:
            query = skill_filtered
    else:
        candidates = query.all()

    scored = []
    for question in candidates:
        if question.id in seen_ids:
            continue
        score = _score_question(question, mastery_map, summary_bias)
        if focus_skill:
            tags = question.skill_tags or []
            if focus_skill in tags:
                score -= 0.05
            else:
                score += 0.05
        scored.append((score, question.id, question))

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


def _build_summary_bias(summary: dict | None) -> Dict[str, float]:
    if not summary:
        return {}
    skill_stats = summary.get("skills") or {}
    bias_strength = float(current_app.config.get("ADAPTIVE_SESSION_BIAS", 0.2))
    bias_map: Dict[str, float] = {}
    for tag, stats in skill_stats.items():
        total_count = stats.get("total") or 0
        if not total_count:
            continue
        accuracy = stats.get("accuracy")
        if accuracy is None:
            correct = stats.get("correct", 0)
            accuracy = correct / total_count if total_count else 0
        delta = max(0.0, 0.5 - accuracy)
        if delta:
            bias_map[tag] = delta * bias_strength
    return bias_map


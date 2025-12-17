"""Spaced repetition helpers for scheduling review questions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List

from flask import current_app

from ..extensions import db
from ..models import Question, QuestionReview, UserQuestionLog


def _review_interval_days() -> int:
    return int(current_app.config.get("ADAPTIVE_REVIEW_INTERVAL_DAYS", 1))


def schedule_from_log(log_entry: UserQuestionLog) -> None:
    now = datetime.now(timezone.utc)
    record = QuestionReview.query.filter_by(
        user_id=log_entry.user_id,
        question_id=log_entry.question_id,
    ).first()

    if log_entry.is_correct:
        if record:
            db.session.delete(record)
    else:
        due_at = now + timedelta(days=_review_interval_days())
        if record is None:
            record = QuestionReview(
                user_id=log_entry.user_id,
                question_id=log_entry.question_id,
                due_at=due_at,
            )
            db.session.add(record)
        else:
            record.due_at = due_at
            record.status = "due"
            db.session.add(record)
    db.session.flush()


def get_due_questions(
    user_id: int,
    limit: int,
    section: str | None = None,
    focus_skill: str | None = None,
) -> List[Question]:
    now = datetime.now(timezone.utc)
    query = (
        QuestionReview.query.join(Question, QuestionReview.question)
        .filter(
            QuestionReview.user_id == user_id,
            QuestionReview.due_at <= now,
            QuestionReview.status == "due",
        )
        .order_by(QuestionReview.due_at.asc())
    )
    if section:
        query = query.filter(Question.section == section)

    reviews = query.limit(limit * 2).all()  # fetch extra to allow skill filtering
    results: List[Question] = []
    candidate_count = len(reviews)
    for review in reviews:
        question = review.question
        if not question:
            continue
        if focus_skill and focus_skill not in (question.skill_tags or []):
            continue
        results.append(question)
        if len(results) >= limit:
            break
    logger = getattr(current_app, "logger", None)
    if logger:
        try:
            logger.info(
                "due_questions_filter",
                extra={
                    "event": "due_questions_filter",
                    "user_id": user_id,
                    "section": section,
                    "focus_skill": focus_skill,
                    "requested": limit,
                    "due_candidate_count": candidate_count,
                    "filtered_count": len(results),
                    "question_ids": [q.id for q in results],
                },
            )
        except Exception:
            pass
    return results


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


def get_due_questions(user_id: int, limit: int, section: str | None = None) -> List[Question]:
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

    reviews = query.limit(limit).all()
    return [review.question for review in reviews if review.question]


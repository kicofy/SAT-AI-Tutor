"""Analytics helpers for progress metrics and predictions."""

from __future__ import annotations

from datetime import datetime, timezone, date
from typing import List

from flask import current_app

from ..extensions import db
from ..models import DailyMetric, Question
from . import score_predictor


def _resolve_day(day: date | None = None) -> date:
    return day or datetime.now(timezone.utc).date()


def _get_daily_metric(user_id: int, day: date | None = None) -> DailyMetric:
    resolved_day = _resolve_day(day)
    metric = DailyMetric.query.filter_by(user_id=user_id, day=resolved_day).first()
    if metric is None:
        metric = DailyMetric(user_id=user_id, day=resolved_day)
        db.session.add(metric)
        db.session.flush()
    return metric


def record_question_result(user_id: int, question: Question, is_correct: bool) -> None:
    metric = _get_daily_metric(user_id)
    metric.questions_answered += 1
    if is_correct:
        metric.correct_questions += 1
    if question.difficulty_level is not None:
        current_total = (metric.questions_answered - 1) or 1
        prev_avg = metric.avg_difficulty or 0.0
        metric.avg_difficulty = prev_avg + (
            (question.difficulty_level - prev_avg) / current_total
        )
    db.session.add(metric)


def record_session_complete(user_id: int) -> None:
    metric = _get_daily_metric(user_id)
    metric.sessions_completed += 1
    scores = score_predictor.estimate_scores(user_id)
    metric.predicted_score_rw = scores["rw"]
    metric.predicted_score_math = scores["math"]
    db.session.add(metric)


def get_progress(user_id: int, limit: int | None = None) -> List[dict]:
    limit = limit or current_app.config.get("ANALYTICS_HISTORY_DAYS", 30)
    query = (
        DailyMetric.query.filter_by(user_id=user_id)
        .order_by(DailyMetric.day.desc())
        .limit(limit)
    )
    results = []
    for metric in reversed(query.all()):
        accuracy = (
            metric.correct_questions / metric.questions_answered
            if metric.questions_answered
            else None
        )
        results.append(
            {
                "day": metric.day.isoformat(),
                "sessions_completed": metric.sessions_completed,
                "questions_answered": metric.questions_answered,
                "accuracy": accuracy,
                "avg_difficulty": metric.avg_difficulty,
                "predicted_score_rw": metric.predicted_score_rw,
                "predicted_score_math": metric.predicted_score_math,
            }
        )
    return results


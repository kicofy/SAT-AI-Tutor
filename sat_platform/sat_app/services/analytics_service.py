"""Analytics helpers for progress metrics and predictions."""

from __future__ import annotations

from datetime import datetime, timezone, date
from statistics import mean
from typing import List, Dict, Any, Tuple

from flask import current_app

from ..extensions import db
from ..models import DailyMetric, Question, UserQuestionLog
from . import score_predictor
from .skill_taxonomy import describe_skill


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


def get_efficiency_summary(user_id: int, limit: int | None = None) -> dict:
    limit = limit or current_app.config.get("ANALYTICS_EFFICIENCY_SAMPLE", 50)
    logs = (
        UserQuestionLog.query.filter_by(user_id=user_id)
        .order_by(UserQuestionLog.answered_at.desc())
        .limit(limit)
        .all()
    )
    samples: List[Tuple[UserQuestionLog, Question]] = []
    for log in logs:
        if not log.time_spent_sec:
            continue
        question = log.question
        if question is None:
            continue
        samples.append((log, question))
    recommended = current_app.config.get(
        "SAT_RECOMMENDED_TIMES",
        {"RW": 65, "Math": 75},
    )
    by_section: Dict[str, List[int]] = {}
    for log, question in samples:
        section = question.section or "RW"
        by_section.setdefault(section, []).append(log.time_spent_sec)

    sections_payload = []
    for section, times in by_section.items():
        sections_payload.append(
            {
                "section": section,
                "avg_time_sec": mean(times),
                "recommended_time_sec": recommended.get(section, 70),
                "question_count": len(times),
            }
        )

    slow_skills_map: Dict[str, List[int]] = {}
    for log, question in samples:
        tags = question.skill_tags or []
        for tag in tags[:2]:
            slow_skills_map.setdefault(tag, []).append(log.time_spent_sec)
    slow_skills = []
    for tag, times in slow_skills_map.items():
        if len(times) < 2:
            continue
        descriptor = describe_skill(tag)
        avg_time = mean(times)
        section = descriptor.get("section") or ("Math" if "Math" in tag else "RW")
        target = recommended.get(section, 70)
        if avg_time > target + 10:
            slow_skills.append(
                {
                    "skill_tag": tag,
                    "label": descriptor.get("label") or tag,
                    "avg_time_sec": avg_time,
                    "question_count": len(times),
                    "section": section,
                    "recommended_time_sec": target,
                }
            )
    overall_times = [log.time_spent_sec for log, _ in samples]
    overall_avg = mean(overall_times) if overall_times else None
    total_section_samples = sum(len(times) for times in by_section.values())
    overall_recommended = (
        sum(recommended.get(section, 70) * len(times) for section, times in by_section.items())
        / total_section_samples
        if total_section_samples
        else None
    )
    return {
        "sample_size": len(samples),
        "sections": sections_payload,
        "slow_skills": sorted(slow_skills, key=lambda item: item["avg_time_sec"], reverse=True),
        "overall_avg_time_sec": overall_avg,
        "overall_recommended_time_sec": overall_recommended,
    }


def get_mistake_queue(user_id: int, limit: int | None = None) -> dict:
    limit = limit or current_app.config.get("ANALYTICS_MISTAKE_SAMPLE", 15)
    logs = (
        UserQuestionLog.query.filter_by(user_id=user_id)
        .filter(UserQuestionLog.is_correct.is_(False))
        .order_by(UserQuestionLog.answered_at.desc())
        .limit(limit)
        .all()
    )
    items = []
    pending_explanations = 0
    for log in logs:
        question = log.question
        if question is None:
            continue
        pending_explanations += 0 if log.viewed_explanation else 1
        items.append(
            {
                "log_id": log.id,
                "question_id": question.id,
                "question_uid": question.question_uid,
                "section": question.section,
                "sub_section": question.sub_section,
                "skill_tags": question.skill_tags or [],
                "answered_at": log.answered_at.isoformat() if log.answered_at else None,
                "time_spent_sec": log.time_spent_sec,
                "viewed_explanation": log.viewed_explanation,
            }
        )
    return {
        "items": items,
        "pending_explanations": pending_explanations,
        "total_mistakes": len(items),
    }


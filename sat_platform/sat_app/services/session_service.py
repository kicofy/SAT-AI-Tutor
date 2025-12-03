"""Learning session service functions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ..extensions import db
from ..models import Question, StudySession, UserQuestionLog
from . import adaptive_engine, spaced_repetition, analytics_service


def select_questions(user_id: int, num_questions: int, section: str | None = None) -> List[Question]:
    questions = adaptive_engine.select_next_questions(user_id=user_id, num_questions=num_questions, section=section)
    if questions:
        return questions
    query = Question.query
    if section:
        query = query.filter_by(section=section)
    return query.order_by(db.func.random()).limit(num_questions).all()


def create_session(user_id: int, questions: List[Question]) -> StudySession:
    serialized = [
        {"question_id": q.id, "section": q.section, "stem_text": q.stem_text, "choices": q.choices}
        for q in questions
    ]
    session = StudySession(user_id=user_id, questions_assigned=serialized)
    db.session.add(session)
    db.session.commit()
    return session


def log_answer(session: StudySession, question: Question, payload: dict, user_id: int) -> UserQuestionLog:
    is_correct = payload["user_answer"] == question.correct_answer
    log = UserQuestionLog(
        user_id=user_id,
        study_session_id=session.id,
        question_id=question.id,
        is_correct=is_correct,
        user_answer=payload["user_answer"],
        time_spent_sec=payload.get("time_spent_sec"),
    )
    db.session.add(log)
    db.session.flush()
    adaptive_engine.update_mastery_from_log(log, question)
    spaced_repetition.schedule_from_log(log)
    analytics_service.record_question_result(user_id, question, is_correct)
    return log


def end_session(session: StudySession) -> StudySession:
    session.ended_at = datetime.now(timezone.utc)
    db.session.commit()
    analytics_service.record_session_complete(session.user_id)
    db.session.commit()
    return session


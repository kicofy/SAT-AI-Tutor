"""Question CRUD service functions."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Passage, Question, QuestionExplanationCache, QuestionFigure


def list_questions(
    page: int,
    per_page: int,
    section: Optional[str] = None,
    question_uid: Optional[str] = None,
    question_id: Optional[int] = None,
    source_id: Optional[int] = None,
):
    query = Question.query.options(joinedload(Question.passage), joinedload(Question.source))
    if section:
        query = query.filter(Question.section == section)
    if question_id:
        query = query.filter(Question.id == question_id)
    if question_uid:
        query = query.filter(Question.question_uid.ilike(f"%{question_uid.strip()}%"))
    if source_id:
        query = query.filter(Question.source_id == source_id)
    return query.order_by(Question.created_at.desc()).paginate(page=page, per_page=per_page)


def get_question(question_id: int) -> Question:
    question = (
        Question.query.options(joinedload(Question.passage))
        .filter(Question.id == question_id)
        .first()
    )
    if question is None:
        from flask import abort

        abort(404)
    return question


def create_or_get_passage(passage_payload: dict | None) -> Passage | None:
    if not passage_payload:
        return None
    passage = Passage(**passage_payload)
    db.session.add(passage)
    db.session.flush()
    return passage


def create_question(payload: dict) -> Question:
    passage_payload = payload.pop("passage", None)
    passage = create_or_get_passage(passage_payload)
    question = Question(**payload)
    if passage is not None:
        question.passage_id = passage.id
    db.session.add(question)
    db.session.commit()
    return question


def update_question(question: Question, payload: dict) -> Question:
    passage_payload = payload.pop("passage", None)
    if passage_payload:
        passage = create_or_get_passage(passage_payload)
        question.passage_id = passage.id
    for key, value in payload.items():
        setattr(question, key, value)
    db.session.commit()
    return question


def delete_question(question: Question) -> None:
    QuestionExplanationCache.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    QuestionFigure.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    db.session.delete(question)
    db.session.commit()


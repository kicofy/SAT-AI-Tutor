"""Question CRUD service functions."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import (
    Passage,
    Question,
    QuestionDraft,
    QuestionExplanationCache,
    QuestionFigure,
    QuestionImportJob,
    QuestionSource,
    QuestionReview,
    UserQuestionLog,
)


def list_questions(
    page: int,
    per_page: int,
    section: Optional[str] = None,
    question_uid: Optional[str] = None,
    question_id: Optional[int] = None,
    source_id: Optional[int] = None,
    skill_tag: Optional[str] = None,
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
    if skill_tag:
        query = query.filter(Question.skill_tags.contains([skill_tag]))
    return query.order_by(Question.created_at.desc()).paginate(page=page, per_page=per_page)


def get_question(question_id: int) -> Question:
    question = (
        Question.query.options(
            joinedload(Question.passage),
            joinedload(Question.source),
        )
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


def create_question(payload: dict, *, commit: bool = True) -> Question:
    passage_payload = payload.pop("passage", None)
    metadata_payload = None
    if "metadata_json" in payload:
        metadata_payload = payload.pop("metadata_json")
    elif "metadata" in payload:
        metadata_payload = payload.pop("metadata")
    passage = create_or_get_passage(passage_payload)
    if metadata_payload is not None:
        payload["metadata_json"] = metadata_payload
    question = Question(**payload)
    if passage is not None:
        question.passage_id = passage.id
    db.session.add(question)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
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


def delete_question(question: Question, *, commit: bool = True) -> None:
    source_id = question.source_id
    UserQuestionLog.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    QuestionReview.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    QuestionExplanationCache.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    QuestionFigure.query.filter_by(question_id=question.id).delete(synchronize_session=False)
    db.session.delete(question)
    db.session.flush()
    if source_id:
        cleanup_source_if_unused(source_id)
    if commit:
        db.session.commit()


def _delete_source_if_unused(source_id: int) -> None:
    remaining_questions = Question.query.filter_by(source_id=source_id).count()
    if remaining_questions:
        return
    remaining_drafts = QuestionDraft.query.filter_by(source_id=source_id).count()
    if remaining_drafts:
        return
    source = db.session.get(QuestionSource, source_id)
    if not source:
        return
    QuestionImportJob.query.filter_by(source_id=source_id).update(
        {"source_id": None}, synchronize_session=False
    )
    db.session.delete(source)


def cleanup_source_if_unused(source_id: int) -> None:
    """Public helper to prune question sources with no references left."""
    _delete_source_if_unused(source_id)


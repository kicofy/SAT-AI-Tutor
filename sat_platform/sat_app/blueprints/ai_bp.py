"""AI blueprint for explainer endpoints."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, current_user
from marshmallow import Schema, fields, ValidationError
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Question, StudySession, UserQuestionLog, QuestionExplanationCache
from ..services import (
    ai_explainer,
    ai_diagnostic,
    session_service,
    membership_service,
    question_explanation_service,
)

ai_bp = Blueprint("ai_bp", __name__)


class ExplainRequestSchema(Schema):
    question_id = fields.Integer(required=True)
    user_answer = fields.Dict(required=True)
    user_language = fields.String(load_default="bilingual")
    depth = fields.String(load_default="standard")


explain_schema = ExplainRequestSchema()

class ExplainDetailSchema(Schema):
    question_id = fields.Integer(required=True)
    log_id = fields.Integer(load_default=None, allow_none=True)


detail_schema = ExplainDetailSchema()


@ai_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST


@ai_bp.get("/ping")
def ping():
    return jsonify({"module": "ai", "status": "ok"})


@ai_bp.post("/explain")
@jwt_required()
def explain():
    payload = explain_schema.load(request.get_json() or {})
    question = Question.query.filter_by(id=payload["question_id"]).first()
    if question is None:
        abort(404)
    language = payload.get("user_language") or _resolve_user_language(current_user)
    try:
        quota = membership_service.consume_ai_explain_quota(current_user)
    except membership_service.AiQuotaExceeded as exc:
        return jsonify({"error": exc.code, **exc.payload}), HTTPStatus.TOO_MANY_REQUESTS
    explanation = ai_explainer.generate_explanation(
        question=question,
        user_answer=payload["user_answer"],
        user_language=language,
        depth=payload["depth"],
    )
    return jsonify({"explanation": explanation, "quota": quota})


@ai_bp.post("/diagnose")
@jwt_required()
def diagnose():
    report = ai_diagnostic.generate_report(current_user.id)
    return jsonify({"predictor": report.predictor_payload, "narrative": report.narrative})


@ai_bp.get("/explain/history")
@jwt_required()
def explain_history():
    args = request.args
    status = (args.get("status") or "all").lower()
    section = args.get("section")
    difficulty = args.get("difficulty")
    search = args.get("search")
    per_page = min(max(int(args.get("per_page", 20)), 1), 50)
    page = max(int(args.get("page", 1)), 1)

    base_query = (
        db.session.query(
            UserQuestionLog.id.label("log_id"),
            UserQuestionLog.question_id.label("question_id"),
            Question.question_uid.label("question_uid"),
            Question.section.label("section"),
            Question.sub_section.label("sub_section"),
            Question.skill_tags.label("skill_tags"),
            Question.difficulty_level.label("difficulty"),
            UserQuestionLog.is_correct.label("is_correct"),
            UserQuestionLog.answered_at.label("answered_at"),
            UserQuestionLog.time_spent_sec.label("time_spent_sec"),
            StudySession.session_type.label("session_type"),
            StudySession.plan_block_id.label("plan_block_id"),
            func.row_number()
            .over(
                partition_by=UserQuestionLog.question_id,
                order_by=UserQuestionLog.answered_at.desc(),
            )
            .label("row_num"),
            func.count()
            .over(partition_by=UserQuestionLog.question_id)
            .label("attempt_count"),
        )
        .join(Question, Question.id == UserQuestionLog.question_id)
        .join(StudySession, StudySession.id == UserQuestionLog.study_session_id)
        .filter(UserQuestionLog.user_id == current_user.id)
    )

    if section and section.lower() not in {"all", "any"}:
        base_query = base_query.filter(func.lower(Question.section) == section.lower())

    if difficulty and difficulty.isdigit():
        base_query = base_query.filter(Question.difficulty_level == int(difficulty))

    if search:
        if search.isdigit():
            base_query = base_query.filter(
                db.or_(
                    Question.id == int(search),
                    Question.question_uid.ilike(f"%{search.strip()}%"),
                )
            )
        else:
            base_query = base_query.filter(Question.question_uid.ilike(f"%{search.strip()}%"))

    latest_subquery = base_query.subquery()
    latest_query = db.session.query(
        latest_subquery.c.log_id,
        latest_subquery.c.question_id,
        latest_subquery.c.question_uid,
        latest_subquery.c.section,
        latest_subquery.c.sub_section,
        latest_subquery.c.skill_tags,
        latest_subquery.c.difficulty,
        latest_subquery.c.is_correct,
        latest_subquery.c.answered_at,
        latest_subquery.c.time_spent_sec,
        latest_subquery.c.session_type,
        latest_subquery.c.plan_block_id,
        latest_subquery.c.attempt_count,
    ).filter(latest_subquery.c.row_num == 1)

    if status == "correct":
        latest_query = latest_query.filter(latest_subquery.c.is_correct.is_(True))
    elif status == "incorrect":
        latest_query = latest_query.filter(latest_subquery.c.is_correct.is_(False))

    latest_query = latest_query.order_by(latest_subquery.c.answered_at.desc())
    pagination = latest_query.paginate(page=page, per_page=per_page, error_out=False)

    language = _resolve_user_language(current_user)
    question_ids = [item.question_id for item in pagination.items]
    explained_ids: set[int] = set()
    if question_ids:
        rows = (
            QuestionExplanationCache.query.filter(
                QuestionExplanationCache.question_id.in_(question_ids),
                QuestionExplanationCache.language == language,
            ).all()
        )
        explained_ids = {row.question_id for row in rows}

    history_items = []
    for item in pagination.items:
        entry = _serialize_history_entry(item)
        entry["has_ai_explanation"] = entry["question_id"] in explained_ids
        history_items.append(entry)

    return jsonify(
        {
            "items": history_items,
            "pagination": {
                "page": pagination.page,
                "pages": pagination.pages,
                "total": pagination.total,
                "per_page": pagination.per_page,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }
    )


@ai_bp.post("/explain/detail")
@jwt_required()
def explain_detail():
    payload = detail_schema.load(request.get_json() or {})
    question = (
        Question.query.options(
            joinedload(Question.passage),
        )
        .filter_by(id=payload["question_id"])
        .first()
    )
    if question is None:
        abort(404)

    if payload.get("log_id"):
        log = (
            UserQuestionLog.query.options(joinedload(UserQuestionLog.study_session))
            .filter_by(id=payload["log_id"], user_id=current_user.id, question_id=question.id)
            .first()
        )
        if log is None:
            abort(404)
    else:
        log = (
            UserQuestionLog.query.options(joinedload(UserQuestionLog.study_session))
            .filter_by(user_id=current_user.id, question_id=question.id)
            .order_by(UserQuestionLog.answered_at.desc())
            .first()
        )

    language = _resolve_user_language(current_user)
    cache = question_explanation_service.get_explanation(question.id, language)
    explanation_payload = cache.explanation if cache else None
    if log and explanation_payload and not log.explanation:
        log.explanation = explanation_payload
        db.session.commit()
    attempt_count = (
        UserQuestionLog.query.filter_by(user_id=current_user.id, question_id=question.id).count()
    )

    meta = _serialize_detail_meta(question, log)
    meta["attempt_count"] = attempt_count
    meta["has_ai_explanation"] = bool(cache)
    meta["explanation_language"] = language

    detail = {
        "question": session_service.serialize_question(question),
        "meta": meta,
        "text_explanation": _resolve_text_explanation(question),
        "ai_explanation": explanation_payload,
    }
    return jsonify(detail)


@ai_bp.post("/explain/generate")
@jwt_required()
def explain_generate():
    payload = detail_schema.load(request.get_json() or {})
    question = (
        Question.query.options(joinedload(Question.passage))
        .filter_by(id=payload["question_id"])
        .first()
    )
    if question is None:
        abort(404)
    if payload.get("log_id"):
        log = (
            UserQuestionLog.query.options(joinedload(UserQuestionLog.study_session))
            .filter_by(id=payload["log_id"], user_id=current_user.id, question_id=question.id)
            .first()
        )
        if log is None:
            abort(404)
    else:
        log = (
            UserQuestionLog.query.options(joinedload(UserQuestionLog.study_session))
            .filter_by(user_id=current_user.id, question_id=question.id)
            .order_by(UserQuestionLog.answered_at.desc())
            .first()
        )
        if log is None:
            abort(404)

    language = _resolve_user_language(current_user)
    cache = question_explanation_service.get_explanation(question.id, language)
    if cache:
        log.explanation = cache.explanation
        log.viewed_explanation = True
        db.session.commit()
        quota_status = membership_service.describe_ai_explain_quota(current_user)
        return jsonify({"explanation": cache.explanation, "quota": quota_status})

    try:
        quota = membership_service.consume_ai_explain_quota(current_user)
    except membership_service.AiQuotaExceeded as exc:
        return jsonify({"error": exc.code, **exc.payload}), HTTPStatus.TOO_MANY_REQUESTS

    cache = question_explanation_service.ensure_explanation(
        question=question,
        language=language,
        source="runtime",
    )
    log.explanation = cache.explanation
    log.viewed_explanation = True
    db.session.commit()
    return jsonify({"explanation": cache.explanation, "quota": quota})


def _resolve_user_language(user):
    profile = getattr(user, "profile", None)
    preference = getattr(profile, "language_preference", None)
    if not preference:
        return "en"
    lowered = preference.lower()
    if "bilingual" in lowered:
        return "en"
    if "zh" in lowered or "cn" in lowered:
        return "zh"
    if "en" in lowered:
        return "en"
    return preference


def _serialize_history_entry(row) -> dict:
    mapping = getattr(row, "_mapping", row)
    return {
        "log_id": mapping["log_id"],
        "question_id": mapping["question_id"],
        "question_uid": mapping["question_uid"],
        "section": mapping["section"],
        "sub_section": mapping["sub_section"],
        "skill_tags": mapping["skill_tags"] or [],
        "difficulty": mapping["difficulty"],
        "is_correct": mapping["is_correct"],
        "answered_at": mapping["answered_at"].isoformat() if mapping["answered_at"] else None,
        "time_spent_sec": mapping["time_spent_sec"],
        "session_type": mapping["session_type"],
        "plan_block_id": mapping["plan_block_id"],
        "attempt_count": int(mapping["attempt_count"] or 0),
    }


def _serialize_detail_meta(question: Question, log: UserQuestionLog | None) -> dict:
    session = log.study_session if log else None
    return {
        "question_id": question.id,
        "question_uid": question.question_uid,
        "log_id": log.id if log else None,
        "is_correct": log.is_correct if log else None,
        "answered_at": log.answered_at.isoformat() if log and log.answered_at else None,
        "time_spent_sec": log.time_spent_sec if log else None,
        "user_answer": log.user_answer if log else None,
        "correct_answer": question.correct_answer,
        "difficulty": question.difficulty_level,
        "difficulty_label": _difficulty_label(question.difficulty_level),
        "section": question.section,
        "sub_section": question.sub_section,
        "skill_tags": question.skill_tags or [],
        "session_type": session.session_type if session else None,
        "plan_block_id": session.plan_block_id if session else None,
        "source_label": getattr(question.source, "original_name", None) or question.source,
    }


def _difficulty_label(value):
    if value is None:
        return None
    scale = {
        1: "Very Easy",
        2: "Easy",
        3: "Medium",
        4: "Hard",
        5: "Very Hard",
    }
    return scale.get(value, str(value))


def _resolve_text_explanation(question: Question) -> str | None:
    metadata = getattr(question, "metadata_json", None) or {}
    if isinstance(metadata, dict):
        for key in ("text_explanation", "explanation", "rationale", "solution"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


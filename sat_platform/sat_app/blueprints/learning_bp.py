"""Learning blueprint endpoints (practice sessions)."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, abort, send_file
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError

from sqlalchemy.exc import IntegrityError

from ..models import Question, StudySession, UserQuestionLog, QuestionExplanationCache, QuestionFigure
from pathlib import Path
from ..schemas import (
    SessionAnswerSchema,
    SessionSchema,
    SessionStartSchema,
    SessionExplanationSchema,
)
from ..services import session_service, ai_explainer, adaptive_engine
from ..services.learning_plan_service import (
    get_or_generate_plan,
    generate_daily_plan,
)
from ..extensions import db

learning_bp = Blueprint("learning_bp", __name__)

start_schema = SessionStartSchema()
answer_schema = SessionAnswerSchema()
explanation_schema = SessionExplanationSchema()
session_schema = SessionSchema()


@learning_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST


@learning_bp.get("/ping")
def ping():
    return jsonify({"module": "learning", "status": "ok"})


@learning_bp.post("/session/start")
@jwt_required()
def start_session():
    payload = start_schema.load(request.get_json() or {})
    existing = session_service.get_active_session(current_user.id)
    if existing:
        return (
            jsonify(
                {
                    "error": "active_session_exists",
                    "session": session_schema.dump(existing),
                }
            ),
            HTTPStatus.CONFLICT,
        )
    questions = session_service.select_questions(
        user_id=current_user.id,
        num_questions=payload["num_questions"],
        section=payload.get("section"),
    )
    if not questions:
        return jsonify({"message": "No questions available"}), HTTPStatus.BAD_REQUEST
    session = session_service.create_session(current_user.id, questions)
    return jsonify({"session": session_schema.dump(session)}), HTTPStatus.CREATED


@learning_bp.post("/session/answer")
@jwt_required()
def answer_question():
    payload = answer_schema.load(request.get_json() or {})
    session = StudySession.query.filter_by(id=payload["session_id"], user_id=current_user.id).first_or_404()
    question = Question.query.filter_by(id=payload["question_id"]).first()
    if question is None:
        abort(404)
    log = session_service.log_answer(session, question, payload, current_user.id)
    db.session.commit()
    return jsonify({"is_correct": log.is_correct, "log_id": log.id})


@learning_bp.post("/session/explanation")
@jwt_required()
def fetch_explanation():
    payload = explanation_schema.load(request.get_json() or {})
    session = StudySession.query.filter_by(id=payload["session_id"], user_id=current_user.id).first_or_404()
    log = (
        UserQuestionLog.query.filter_by(
            study_session_id=session.id, question_id=payload["question_id"], user_id=current_user.id
        )
        .order_by(UserQuestionLog.answered_at.desc())
        .first()
    )
    if log is None:
        abort(404)
    question = Question.query.filter_by(id=payload["question_id"]).first_or_404()
    user_language = _resolve_user_language(current_user)
    answer_value = _extract_answer_value(log.user_answer)

    if _log_matches_language(log.explanation, user_language):
        return jsonify({"explanation": log.explanation})

    cached = QuestionExplanationCache.query.filter_by(
        question_id=question.id,
        language=user_language,
        answer_value=answer_value,
    ).first()
    if cached:
        log.explanation = cached.explanation
        db.session.commit()
        return jsonify({"explanation": cached.explanation})

    explanation = ai_explainer.generate_explanation(
        question=question,
        user_answer=log.user_answer,
        user_language=user_language,
        depth="standard",
    )
    log.explanation = explanation
    db.session.commit()
    _store_explanation_cache(
        question_id=question.id,
        language=user_language,
        answer_value=answer_value,
        explanation=explanation,
    )
    return jsonify({"explanation": explanation})


@learning_bp.post("/session/explanation/clear")
@jwt_required()
def clear_explanation():
    payload = explanation_schema.load(request.get_json() or {})
    session = StudySession.query.filter_by(id=payload["session_id"], user_id=current_user.id).first_or_404()
    log = (
        UserQuestionLog.query.filter_by(
            study_session_id=session.id, question_id=payload["question_id"], user_id=current_user.id
        )
        .order_by(UserQuestionLog.answered_at.desc())
        .first()
    )
    if log is None:
        abort(404)
    question = Question.query.filter_by(id=payload["question_id"]).first_or_404()
    language = _resolve_user_language(current_user)
    answer_value = _extract_answer_value(log.user_answer)

    log.explanation = None
    QuestionExplanationCache.query.filter_by(
        question_id=question.id,
        language=language,
        answer_value=answer_value,
    ).delete()
    db.session.commit()
    return jsonify({"message": "Explanation cleared"}), HTTPStatus.OK


@learning_bp.post("/session/end")
@jwt_required()
def end_session():
    session_id = request.get_json(force=True).get("session_id")
    session = StudySession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    ended = session_service.end_session(session)
    return jsonify({"session": session_schema.dump(ended)})


@learning_bp.post("/session/abort")
@jwt_required()
def abort_session():
    payload = request.get_json(force=True) or {}
    session_id = payload.get("session_id")
    session = (
        StudySession.query.filter_by(id=session_id, user_id=current_user.id, ended_at=None)
        .order_by(StudySession.started_at.desc())
        .first()
    )
    if session is None:
        return jsonify({"message": "No active session"}), HTTPStatus.OK
    aborted = session_service.abort_session(session)
    return jsonify({"session": session_schema.dump(aborted)})


@learning_bp.get("/session/active")
@jwt_required()
def active_session():
    session = session_service.get_active_session(current_user.id)
    if not session:
        return jsonify({"session": None})
    return jsonify({"session": session_schema.dump(session)})


@learning_bp.get("/mastery")
@jwt_required()
def mastery_snapshot():
    data = adaptive_engine.get_mastery_snapshot(current_user.id)
    return jsonify({"mastery": data})


@learning_bp.get("/plan/today")
@jwt_required()
def plan_today():
    plan = get_or_generate_plan(current_user.id)
    return jsonify({"plan": plan.generated_detail})


@learning_bp.post("/plan/regenerate")
@jwt_required()
def plan_regenerate():
    plan = generate_daily_plan(current_user.id)
    return jsonify({"plan": plan.generated_detail})


def _resolve_user_language(user):
    profile = getattr(user, "profile", None)
    preference = getattr(profile, "language_preference", None)
    if not preference:
        return "en"
    lowered = preference.lower()
    if "zh" in lowered or "cn" in lowered:
        return "zh"
    if "en" in lowered:
        return "en"
    return preference


def _extract_answer_value(user_answer):
    if isinstance(user_answer, dict):
        raw = user_answer.get("value")
        if raw is None:
            return None
        return str(raw)
    if isinstance(user_answer, str):
        return user_answer
    return None


def _log_matches_language(explanation_obj, language):
    if not isinstance(explanation_obj, dict):
        return False
    return explanation_obj.get("language") == language


def _store_explanation_cache(question_id, language, answer_value, explanation):
    cache = QuestionExplanationCache(
        question_id=question_id,
        language=language,
        answer_value=answer_value,
        explanation=explanation,
    )
    db.session.add(cache)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()


@learning_bp.get("/questions/figures/<int:figure_id>/image")
@jwt_required()
def get_question_figure_image(figure_id: int):
    figure = QuestionFigure.query.filter_by(id=figure_id).first()
    if not figure or figure.question_id is None or not figure.image_path:
        abort(404)
    path = Path(figure.image_path)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="image/png")


"""Learning blueprint endpoints (practice sessions)."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError

from ..models import Question, StudySession
from ..schemas import SessionAnswerSchema, SessionSchema, SessionStartSchema
from ..services import session_service, ai_explainer, adaptive_engine
from ..services.learning_plan_service import (
    get_or_generate_plan,
    generate_daily_plan,
)
from ..extensions import db

learning_bp = Blueprint("learning_bp", __name__)

start_schema = SessionStartSchema()
answer_schema = SessionAnswerSchema()
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
    explanation = ai_explainer.generate_explanation(
        question=question,
        user_answer=payload["user_answer"],
        user_language="bilingual",
        depth="standard",
    )
    log.explanation = explanation
    db.session.commit()
    return jsonify({"is_correct": log.is_correct, "explanation": explanation})


@learning_bp.post("/session/end")
@jwt_required()
def end_session():
    session_id = request.get_json(force=True).get("session_id")
    session = StudySession.query.filter_by(id=session_id, user_id=current_user.id).first_or_404()
    ended = session_service.end_session(session)
    return jsonify({"session": session_schema.dump(ended)})


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


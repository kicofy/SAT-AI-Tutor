"""AI blueprint for explainer endpoints."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, current_user
from marshmallow import Schema, fields, ValidationError

from ..models import Question
from ..services import ai_explainer
from ..services import ai_diagnostic

ai_bp = Blueprint("ai_bp", __name__)


class ExplainRequestSchema(Schema):
    question_id = fields.Integer(required=True)
    user_answer = fields.Dict(required=True)
    user_language = fields.String(load_default="bilingual")
    depth = fields.String(load_default="standard")


explain_schema = ExplainRequestSchema()


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
    explanation = ai_explainer.generate_explanation(
        question=question,
        user_answer=payload["user_answer"],
        user_language=payload["user_language"],
        depth=payload["depth"],
    )
    return jsonify({"explanation": explanation})


@ai_bp.post("/diagnose")
@jwt_required()
def diagnose():
    report = ai_diagnostic.generate_report(current_user.id)
    return jsonify({"predictor": report.predictor_payload, "narrative": report.narrative})


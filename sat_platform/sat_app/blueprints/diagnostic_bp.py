"""Diagnostic onboarding endpoints."""

from __future__ import annotations

from http import HTTPStatus

from flask import Blueprint, jsonify
from flask_jwt_extended import current_user, jwt_required
from werkzeug.exceptions import BadRequest

from ..schemas import SessionSchema
from ..services import diagnostic_service

diagnostic_bp = Blueprint("diagnostic_bp", __name__)
session_schema = SessionSchema()


def _status_payload():
    payload, session = diagnostic_service.get_status_payload(current_user.id)
    payload["session"] = session_schema.dump(session) if session else None
    return payload


@diagnostic_bp.get("/status")
@jwt_required()
def diagnostic_status():
    return jsonify(_status_payload())


@diagnostic_bp.post("/start")
@jwt_required()
def diagnostic_start():
    try:
        diagnostic_service.start_attempt(current_user.id)
    except BadRequest as exc:
        return jsonify({"error": exc.description or "diagnostic_error"}), HTTPStatus.BAD_REQUEST
    return jsonify(_status_payload()), HTTPStatus.CREATED


@diagnostic_bp.post("/skip")
@jwt_required()
def diagnostic_skip():
    diagnostic_service.skip_attempt(current_user.id)
    return jsonify(_status_payload())


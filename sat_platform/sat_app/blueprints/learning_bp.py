"""Learning blueprint endpoints (practice sessions)."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, abort, send_file, current_app
from flask_jwt_extended import current_user, jwt_required
from itsdangerous import BadSignature, SignatureExpired
from marshmallow import ValidationError

from werkzeug.exceptions import BadRequest

from ..models import Question, StudySession, UserQuestionLog, QuestionFigure
from ..schemas import (
    SessionAnswerSchema,
    SessionSchema,
    SessionStartSchema,
    SessionExplanationSchema,
)
from ..services import (
    session_service,
    adaptive_engine,
    learning_plan_service,
    tutor_notes_service,
    diagnostic_service,
    membership_service,
    question_explanation_service,
    progress_service,
)
from ..extensions import db, limiter
from ..utils.signed_urls import sign_payload, verify_payload

learning_bp = Blueprint("learning_bp", __name__)

start_schema = SessionStartSchema()
answer_schema = SessionAnswerSchema()
explanation_schema = SessionExplanationSchema()
session_schema = SessionSchema()

FIGURE_SCOPE_PRACTICE = "practice"
FIGURE_SCOPE_PREVIEW = "preview"


def _figure_signing_config():
    cfg = current_app.config
    return {
        "secret": cfg.get("FIGURE_URL_SECRET") or cfg.get("JWT_SECRET_KEY"),
        "salt": cfg.get("FIGURE_URL_SALT", "figure-url"),
        "ttl_practice": int(cfg.get("FIGURE_URL_TTL_PRACTICE", 1800)),
        "ttl_preview": int(cfg.get("FIGURE_URL_TTL_PREVIEW", 600)),
        "limit_practice": cfg.get("FIGURE_URL_RATE_LIMIT_PRACTICE", "60 per minute"),
        "limit_preview": cfg.get("FIGURE_URL_RATE_LIMIT_PREVIEW", "30 per minute"),
    }


def _verify_figure_token(figure_id: int, scope: str, *, allow_admin_fallback: bool = True) -> None:
    """Validate signed token on figure fetch; optionally allow admin fallback."""

    token = request.args.get("sig") or request.args.get("token")
    cfg = _figure_signing_config()
    max_age = cfg["ttl_preview"] if scope == FIGURE_SCOPE_PREVIEW else cfg["ttl_practice"]
    if token:
        try:
            payload = verify_payload(
                token,
                secret=cfg["secret"],
                salt=cfg["salt"],
                max_age=max_age,
            )
        except SignatureExpired:
            abort(401)
        except BadSignature:
            abort(401)
        if int(payload.get("fid", -1)) != int(figure_id) or payload.get("scope") != scope:
            abort(403)
        return

    # Fallback: allow admins with an active JWT to bypass signature (for debugging/tools).
    if allow_admin_fallback and current_user and getattr(current_user, "role", None) == "admin":
        return
    abort(401)


def _serve_figure_file(path: Path, max_age: int):
    response = send_file(path, mimetype="image/png")
    response.headers["Cache-Control"] = f"private, max-age={max_age}"
    return response


def _diagnostic_guard():
    requires = diagnostic_service.requires_diagnostic(current_user.id)
    if not requires:
        return None
    payload, session = diagnostic_service.get_status_payload(current_user.id)
    payload["session"] = session_schema.dump(session) if session else None
    return (
        jsonify(
            {
                "error": "diagnostic_required",
                "diagnostic": payload,
            }
        ),
        HTTPStatus.PRECONDITION_REQUIRED,
    )


def _membership_plan_guard():
    diag_guard = _diagnostic_guard()
    if diag_guard:
        return diag_guard
    try:
        membership_service.ensure_plan_access(current_user)
    except membership_service.PlanAccessDenied as exc:
        payload = {"error": exc.code, **exc.payload}
        return jsonify(payload), HTTPStatus.PAYMENT_REQUIRED
    return None


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
    existing = session_service.get_active_session(current_user.id, include_plan=False)
    if existing:
        session_service.refresh_assigned_questions(existing)
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
        source_id=payload.get("source_id"),
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
        refreshed = session_service.refresh_assigned_questions(session)
        if not refreshed.questions_assigned:
            return (
                jsonify(
                    {
                        "error": "question_unavailable",
                        "message": "No questions available for this session. Please start a new practice set.",
                    }
                ),
                HTTPStatus.CONFLICT,
            )
        return (
            jsonify(
                {
                    "error": "question_reassigned",
                    "session": session_schema.dump(refreshed),
                }
            ),
            HTTPStatus.CONFLICT,
        )
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

    try:
        quota = membership_service.consume_ai_explain_quota(current_user)
    except membership_service.AiQuotaExceeded as exc:
        return jsonify({"error": exc.code, **exc.payload}), HTTPStatus.TOO_MANY_REQUESTS

    cache = question_explanation_service.ensure_explanation(
        question=question,
        language=user_language,
        source="runtime",
    )
    log.explanation = cache.explanation
    log.viewed_explanation = True
    db.session.commit()
    return jsonify({"explanation": cache.explanation, "quota": quota})


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

    log.explanation = None
    question_explanation_service.delete_explanation(question.id, language)
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
    session = session_service.get_active_session(current_user.id, include_plan=False)
    if not session:
        return jsonify({"session": None})
    session_service.refresh_assigned_questions(session)
    return jsonify({"session": session_schema.dump(session)})


@learning_bp.get("/mastery")
@jwt_required()
def mastery_snapshot():
    data = adaptive_engine.get_mastery_snapshot(current_user.id)
    return jsonify({"mastery": data})


@learning_bp.get("/plan/today")
@jwt_required()
def plan_today():
    guard = _membership_plan_guard()
    if guard:
        return guard
    plan, tasks = learning_plan_service.get_plan_with_tasks(current_user.id)
    return jsonify({"plan": plan.generated_detail, "tasks": tasks})


@learning_bp.post("/plan/regenerate")
@jwt_required()
def plan_regenerate():
    guard = _membership_plan_guard()
    if guard:
        return guard
    plan = learning_plan_service.generate_daily_plan(current_user.id)
    _, tasks = learning_plan_service.get_plan_with_tasks(current_user.id, plan.plan_date)
    return jsonify({"plan": plan.generated_detail, "tasks": tasks})


@learning_bp.get("/plan/tasks")
@jwt_required()
def plan_tasks():
    guard = _membership_plan_guard()
    if guard:
        return guard
    _, tasks = learning_plan_service.get_plan_with_tasks(current_user.id)
    return jsonify({"tasks": tasks})


@learning_bp.post("/plan/tasks/<string:block_id>/start")
@jwt_required()
def plan_task_start(block_id: str):
    guard = _membership_plan_guard()
    if guard:
        return guard
    try:
        session, task = learning_plan_service.start_plan_task(current_user.id, block_id)
    except BadRequest as exc:
        return (
            jsonify(
                {
                    "error": "no_questions_for_block",
                    "message": str(exc),
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    session_service.refresh_assigned_questions(session)
    return jsonify({"session": session_schema.dump(session), "task": task})


@learning_bp.get("/tutor-notes/today")
@jwt_required()
def tutor_notes_today():
    guard = _membership_plan_guard()
    if guard:
        return guard
    language = request.args.get("lang")
    refresh = request.args.get("refresh") == "true"
    notes = tutor_notes_service.get_or_generate_tutor_notes(
        current_user.id, language=language, refresh=refresh
    )
    return jsonify(notes)


@learning_bp.get("/coach-notes/today")
@jwt_required()
def coach_notes_legacy():
    return tutor_notes_today()


@learning_bp.get("/progress/today")
@jwt_required()
def progress_today():
    data = progress_service.get_today_progress(current_user.id)
    return jsonify({"progress": data})

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


@learning_bp.get("/questions/figures/<int:figure_id>/image")
@jwt_required(optional=True)
@limiter.limit(lambda: _figure_signing_config()["limit_practice"])
def get_question_figure_image(figure_id: int):
    figure = QuestionFigure.query.filter_by(id=figure_id).first()
    if not figure or figure.question_id is None or not figure.image_path:
        abort(404)
    _verify_figure_token(figure_id, FIGURE_SCOPE_PRACTICE, allow_admin_fallback=True)
    path = Path(figure.image_path)
    if not path.exists():
        abort(404)
    cfg = _figure_signing_config()
    return _serve_figure_file(path, cfg["ttl_practice"])


@learning_bp.get("/questions/preview-figures/<int:figure_id>/image")
@jwt_required(optional=True)
@limiter.limit(lambda: _figure_signing_config()["limit_preview"])
def get_preview_figure_image(figure_id: int):
    """Serve figure images for draft/previews (used in practice preview)."""
    figure = QuestionFigure.query.filter_by(id=figure_id).first()
    if not figure or not figure.image_path:
        abort(404)
    # Allow either question-linked or draft-linked figures.
    if figure.question_id is None and figure.draft_id is None:
        abort(404)
    _verify_figure_token(figure_id, FIGURE_SCOPE_PREVIEW, allow_admin_fallback=True)
    path = Path(figure.image_path)
    if not path.exists():
        abort(404)
    cfg = _figure_signing_config()
    return _serve_figure_file(path, cfg["ttl_preview"])


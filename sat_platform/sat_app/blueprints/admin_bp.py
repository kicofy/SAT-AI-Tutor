"""Admin blueprint endpoints."""

from __future__ import annotations

import json
import string
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
import base64
from io import BytesIO
from pathlib import Path
from threading import Thread
from uuid import uuid4
import shutil

import pdfplumber
from flask import Blueprint, Response, abort, current_app, jsonify, request, send_file, url_for, stream_with_context
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError
from werkzeug.utils import secure_filename
from sqlalchemy import func, or_, case

from ..extensions import db
from ..models import (
    QuestionDraft,
    QuestionFigure,
    QuestionImportJob,
    QuestionExplanationCache,
    QuestionSource,
    StudyPlanTask,
    DailyMetric,
    UserQuestionLog,
    User,
    Question,
)
from ..schemas import ManualParseSchema, QuestionCreateSchema, QuestionSchema, UserSchema
from ..services import question_service, openai_log, mail_service
from ..services.skill_taxonomy import canonicalize_tags
from ..services.job_events import job_event_broker
from ..tasks.question_tasks import process_job
from ..utils import hash_password

admin_bp = Blueprint("admin_bp", __name__)

question_create_schema = QuestionCreateSchema()
question_schema = QuestionSchema()
manual_parse_schema = ManualParseSchema()
admin_user_schema = UserSchema()
FIGURE_DIR_NAME = "question_figures"


def _paginate(query, page: int, per_page: int):
    per_page = max(1, min(per_page, 100))
    page = max(page, 1)
    return query.paginate(page=page, per_page=per_page, error_out=False)


def _serialize_user(user: User) -> dict:
    data = admin_user_schema.dump(user)
    data["profile"] = data.get("profile") or {}
    data["created_at"] = user.created_at.isoformat() if user.created_at else None
    return data


def _serialize_question(question: Question) -> dict:
    data = question_schema.dump(question)
    data["source"] = _serialize_source(question.source)
    figures = []
    figure_query = getattr(question, "figures", None)
    if figure_query is not None:
        try:
            figure_list = figure_query.all()
        except Exception:  # pragma: no cover
            figure_list = []
        figures = [_serialize_figure(fig) for fig in figure_list if fig.image_path]
    if figures:
        data["figures"] = figures
    return data


def _serialize_plan_task(task: StudyPlanTask) -> dict:
    if not task:
        return {}
    return {
        "block_id": task.block_id,
        "status": task.status,
        "section": task.section,
        "focus_skill": task.focus_skill,
        "questions_target": task.questions_target,
        "plan_date": task.plan_date.isoformat() if task.plan_date else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _learning_snapshot(user_id: int) -> dict | None:
    stats = (
        db.session.query(
            func.count(UserQuestionLog.id),
            func.sum(case((UserQuestionLog.is_correct == True, 1), else_=0)),  # noqa: E712
            func.avg(UserQuestionLog.time_spent_sec),
            func.max(UserQuestionLog.answered_at),
        )
        .filter(UserQuestionLog.user_id == user_id)
        .one()
    )
    total_questions = int(stats[0] or 0)
    correct_questions = int(stats[1] or 0)
    avg_time = float(stats[2]) if stats[2] is not None else None
    last_active = stats[3].isoformat() if stats[3] else None
    accuracy = round((correct_questions / total_questions) * 100, 1) if total_questions else None

    plan_stats = (
        db.session.query(
            func.count(StudyPlanTask.id),
            func.sum(case((StudyPlanTask.status == "completed", 1), else_=0)),
        )
        .filter(StudyPlanTask.user_id == user_id)
        .one()
    )
    plan_total = int(plan_stats[0] or 0)
    plan_completed = int(plan_stats[1] or 0)

    active_task = (
        StudyPlanTask.query.filter(
            StudyPlanTask.user_id == user_id,
            StudyPlanTask.status.in_(("pending", "in_progress")),
        )
        .order_by(StudyPlanTask.updated_at.desc())
        .first()
    )

    latest_metric = (
        DailyMetric.query.filter_by(user_id=user_id)
        .order_by(DailyMetric.day.desc())
        .first()
    )

    snapshot = {
        "last_active_at": last_active,
        "total_questions": total_questions,
        "accuracy_percent": accuracy,
        "avg_time_sec": avg_time,
        "plan_tasks_completed": plan_completed,
        "plan_tasks_total": plan_total,
        "active_plan": _serialize_plan_task(active_task) if active_task else None,
        "predicted_score_rw": latest_metric.predicted_score_rw if latest_metric else None,
        "predicted_score_math": latest_metric.predicted_score_math if latest_metric else None,
        "avg_difficulty": latest_metric.avg_difficulty if latest_metric else None,
    }
    if (
        total_questions == 0
        and plan_total == 0
        and not snapshot["active_plan"]
        and snapshot["predicted_score_rw"] is None
    ):
        return None
    return snapshot


def _pagination_payload(pagination) -> dict:
    return {
        "page": pagination.page,
        "per_page": pagination.per_page,
        "pages": pagination.pages,
        "total": pagination.total,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    }


def _create_question_source(*, filename: str, stored_path: Path, uploader_id: int, original_name: str | None = None) -> QuestionSource:
    source = QuestionSource(
        filename=filename,
        original_name=original_name or filename,
        stored_path=str(stored_path),
        uploaded_by=uploader_id,
    )
    db.session.add(source)
    db.session.flush()
    return source


def _serialize_source(source: QuestionSource | None) -> dict | None:
    if not source:
        return None
    return {
        "id": source.id,
        "filename": source.filename,
        "original_name": source.original_name,
        "total_pages": source.total_pages,
        "created_at": source.created_at.isoformat() if source.created_at else None,
    }


def _coerce_draft_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    data = dict(payload)

    choices = data.get("choices")
    if isinstance(choices, list):
        mapped: dict[str, str] = {}
        labels = list(string.ascii_uppercase)
        for idx, choice in enumerate(choices):
            if not isinstance(choice, dict):
                continue
            label = (choice.get("label") or (labels[idx] if idx < len(labels) else str(idx))).strip().upper()
            text = choice.get("text") or choice.get("value") or ""
            if label:
                mapped[label] = text
        if mapped:
            data["choices"] = mapped
    elif isinstance(choices, dict):
        normalized_choices: dict[str, str] = {}
        for key, value in choices.items():
            label = str(key).strip().upper()
            if not label:
                continue
            normalized_choices[label] = value
        data["choices"] = normalized_choices
    else:
        data["choices"] = {}

    correct = data.get("correct_answer")
    if isinstance(correct, str):
        data["correct_answer"] = {"value": correct.strip() or None}
    elif isinstance(correct, dict):
        if "value" not in correct and "answer" in correct:
            correct["value"] = correct.get("answer")
    else:
        data["correct_answer"] = {"value": None}

    skill_tags = data.get("skill_tags")
    if isinstance(skill_tags, str):
        skill_tags = [skill_tags]
    elif not isinstance(skill_tags, list):
        skill_tags = []
    data["skill_tags"] = canonicalize_tags(skill_tags, limit=2)

    section = data.get("section")
    if isinstance(section, str):
        lowered = section.strip().lower()
        if lowered.startswith("m"):
            data["section"] = "Math"
        else:
            data["section"] = "RW"

    if not data.get("stem_text") and data.get("prompt"):
        data["stem_text"] = data["prompt"]
    data.pop("prompt", None)

    passage_payload = data.get("passage")
    normalized_passage = None
    if isinstance(passage_payload, dict):
        passage_copy = dict(passage_payload)
        metadata_from_json = passage_copy.pop("metadata_json", None)
        if metadata_from_json and not passage_copy.get("metadata"):
            passage_copy["metadata"] = metadata_from_json
        if passage_copy.get("content_text"):
            normalized_passage = passage_copy
    elif isinstance(passage_payload, str):
        text = passage_payload.strip()
        if text:
            normalized_passage = {"content_text": text, "metadata": {"source": "legacy"}}
    if normalized_passage:
        data["passage"] = normalized_passage
    elif "passage" in data:
        data["passage"] = None

    metadata_json = data.pop("metadata_json", None)
    if metadata_json and not data.get("metadata"):
        data["metadata"] = metadata_json

    data["has_figure"] = bool(data.get("has_figure"))

    if isinstance(data.get("sub_section"), str) and not data["sub_section"].strip():
        data["sub_section"] = None

    return data


def _figure_root() -> Path:
    root = Path(current_app.instance_path) / FIGURE_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def _delete_figure_file(figure: QuestionFigure) -> None:
    if figure.image_path:
        try:
            Path(figure.image_path).unlink(missing_ok=True)
        except OSError:
            pass


def _serialize_figure(figure: QuestionFigure) -> dict:
    return {
        "id": figure.id,
        "description": figure.description,
        "bbox": figure.bbox,
        "url": url_for("admin_bp.get_figure_image", figure_id=figure.id, _external=False),
    }


def _extract_draft_page(draft: QuestionDraft) -> int:
    payload = draft.payload or {}
    page_value = payload.get("page") or payload.get("metadata", {}).get("page")
    try:
        page_int = int(str(page_value))
        return max(1, page_int)
    except (TypeError, ValueError):
        return 1


def _render_pdf_page_base64(pdf_path: str | Path, page_number: int) -> tuple[str, int, int]:
    resolution = current_app.config.get("PDF_INGEST_RESOLUTION", 220)
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(path)
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        if page_number < 1 or page_number > total_pages:
            raise ValueError(f"Page {page_number} out of range (1-{total_pages})")
        page = pdf.pages[page_number - 1]
        image = page.to_image(resolution=resolution).original.convert("RGB")
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}", image.width, image.height


def _get_draft_or_404(draft_id: int) -> QuestionDraft:
    draft = db.session.get(QuestionDraft, draft_id)
    if not draft:
        abort(404)
    return draft


def _resolve_question_page_number(question: Question, requested_page: str | None) -> int | None:
    if requested_page and requested_page.isdigit():
        return max(1, int(requested_page))
    if getattr(question, "source_page", None):
        try:
            return max(1, int(question.source_page))
        except (TypeError, ValueError):
            pass
    candidate = getattr(question, "page", None)
    if candidate:
        try:
            return max(1, int(str(candidate)))
        except (TypeError, ValueError):
            return None
    return None


def _attach_figure_to_question(figure: QuestionFigure, question_id: int) -> None:
    figure.question_id = question_id
    figure.draft_id = None
    if figure.image_path:
        src = Path(figure.image_path)
        if src.exists():
            dest_dir = _figure_root() / f"question_{question_id}"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = dest_dir / src.name
            try:
                shutil.move(str(src), dest_path)
            except Exception:  # pragma: no cover - best effort
                dest_path = src
            figure.image_path = str(dest_path)
    db.session.add(figure)


def require_admin():
    return current_user is not None and current_user.role == "admin"


def _prune_stale_jobs(max_age_hours: int = 2):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    stale_jobs = (
        QuestionImportJob.query.filter(
            QuestionImportJob.status.in_(("pending", "processing")),
            QuestionImportJob.created_at < cutoff,
        ).all()
    )
    if not stale_jobs:
        return
    for job in stale_jobs:
        job.status = "failed"
        job.status_message = (
            "Automatically paused after exceeding the maximum processing window. "
            "Please review the drafts and decide whether to resume or cancel."
        )
        job.last_progress_at = datetime.now(timezone.utc)
        db.session.add(job)
        job_event_broker.publish({"type": "job", "payload": job.serialize()})
    db.session.commit()


@admin_bp.errorhandler(ValidationError)
def handle_validation_error(err: ValidationError):
    return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST


@admin_bp.get("/ping")
def ping():
    return jsonify({"module": "admin", "status": "ok"})


@admin_bp.get("/users")
@jwt_required()
def list_users_admin():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN

    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search = (request.args.get("search") or "").strip().lower()
    role = request.args.get("role")
    verified = request.args.get("verified")

    query = User.query.order_by(User.created_at.desc())
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                func.lower(User.email).like(like),
                func.lower(User.username).like(like),
            )
        )
    if role:
        query = query.filter_by(role=role)
    if verified in {"true", "false"}:
        query = query.filter_by(is_email_verified=(verified == "true"))

    pagination = _paginate(query, page, per_page)
    return jsonify(
        {
            "items": [_serialize_user(user) for user in pagination.items],
            "pagination": _pagination_payload(pagination),
        }
    )


@admin_bp.get("/users/<int:user_id>")
@jwt_required()
def get_user_admin(user_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    snapshot = _learning_snapshot(user.id)
    return jsonify({"user": _serialize_user(user), "snapshot": snapshot})


@admin_bp.patch("/users/<int:user_id>")
@jwt_required()
def update_user_admin(user_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    payload = request.get_json() or {}
    allowed_roles = {"student", "admin"}
    updated = False
    email = payload.get("email")
    if email and email.lower() != user.email:
        if User.query.filter_by(email=email.lower()).first():
            return jsonify({"message": "Email already registered"}), HTTPStatus.CONFLICT
        user.email = email.lower()
        updated = True
    username = payload.get("username")
    if username and username.lower() != (user.username or "").lower():
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            return jsonify({"message": "Username already taken"}), HTTPStatus.CONFLICT
        user.username = username
        updated = True
    role = payload.get("role")
    if role and role in allowed_roles and role != user.role:
        user.role = role
        updated = True
    language = payload.get("language_preference")
    if language:
        if not user.profile:
            from ..models import UserProfile

            user.profile = UserProfile(language_preference=language, daily_available_minutes=60)
        else:
            user.profile.language_preference = language
        updated = True
    is_active_payload = payload.get("is_active")
    locked_reason_supplied = "locked_reason" in payload
    locked_reason_value = payload.get("locked_reason")

    if is_active_payload is not None:
        desired_active = bool(is_active_payload)
        if desired_active != user.is_active:
            user.is_active = desired_active
            if desired_active:
                user.locked_at = None
                user.locked_reason = (
                    locked_reason_value or None if locked_reason_supplied else None
                )
            else:
                user.locked_at = datetime.now(timezone.utc)
                if locked_reason_supplied:
                    user.locked_reason = locked_reason_value or None
            updated = True

    if locked_reason_supplied and not user.is_active:
        user.locked_reason = locked_reason_value or None
        updated = True

    if payload.get("reset_password"):
        new_pw = payload["reset_password"]
        user.password_hash = hash_password(new_pw)
        updated = True
    if updated:
        db.session.add(user)
        db.session.commit()
    return jsonify({"user": _serialize_user(user)})


@admin_bp.route("/questions", methods=["GET"])
@jwt_required()
def list_questions():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 20)), 100)
    section = request.args.get("section")
    question_uid = request.args.get("question_uid")
    question_id = request.args.get("question_id", type=int)
    source_id = request.args.get("source_id", type=int)
    pagination = question_service.list_questions(
        page, per_page, section, question_uid, question_id, source_id
    )
    return jsonify(
        {
            "items": question_schema.dump(pagination.items, many=True),
            "page": pagination.page,
            "per_page": pagination.per_page,
            "total": pagination.total,
        }
    )


@admin_bp.post("/questions")
@jwt_required()
def create_question():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    payload = question_create_schema.load(request.get_json() or {})
    question = question_service.create_question(payload)
    return jsonify({"question": question_schema.dump(question)}), HTTPStatus.CREATED


@admin_bp.get("/questions/<int:question_id>")
@jwt_required()
def get_question(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    return jsonify({"question": _serialize_question(question)})


@admin_bp.get("/questions/<int:question_id>/figure-source")
@jwt_required()
def get_question_figure_source(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    source = question.source
    if not source or not source.stored_path:
        return jsonify({"message": "Question is not linked to a PDF source."}), HTTPStatus.BAD_REQUEST
    page = _resolve_question_page_number(question, request.args.get("page"))
    if not page:
        return jsonify({"message": "No page number available for this question."}), HTTPStatus.BAD_REQUEST
    try:
        image, width, height = _render_pdf_page_base64(source.stored_path, page)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"message": f"Unable to render page {page}: {exc}"}), HTTPStatus.BAD_REQUEST
    return jsonify({"page": page, "image": image, "width": width, "height": height})


@admin_bp.get("/questions/<int:question_id>/figures")
@jwt_required()
def list_question_figures(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    figure_query = getattr(question, "figures", None)
    figures = []
    if figure_query is not None:
        try:
            figures = figure_query.all()
        except Exception:  # pragma: no cover
            figures = []
    return jsonify({"figures": [_serialize_figure(fig) for fig in figures]})


@admin_bp.post("/questions/<int:question_id>/figure")
@jwt_required()
def upload_question_figure(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    if not question.source_id:
        return jsonify({"message": "Question must be linked to a PDF source first."}), HTTPStatus.BAD_REQUEST
    file = request.files.get("image")
    if file is None:
        return jsonify({"message": "Image file is required."}), HTTPStatus.BAD_REQUEST
    bbox_raw = request.form.get("bbox")
    description = request.form.get("description") or None
    bbox = None
    if bbox_raw:
        try:
            bbox = json.loads(bbox_raw)
        except json.JSONDecodeError:
            return jsonify({"message": "Invalid bbox payload."}), HTTPStatus.BAD_REQUEST
    target_dir = _figure_root() / f"question_{question.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename or f"question-{question.id}-{uuid4().hex}.png")
    path = target_dir / filename
    file.save(path)
    existing_query = getattr(question, "figures", None)
    if existing_query is not None:
        for existing in existing_query.all():
            _delete_figure_file(existing)
            db.session.delete(existing)
    figure = QuestionFigure(question_id=question.id, image_path=str(path), description=description, bbox=bbox)
    question.has_figure = True
    db.session.add(figure)
    db.session.add(question)
    db.session.commit()
    return jsonify({"figure": _serialize_figure(figure)}), HTTPStatus.CREATED


@admin_bp.delete("/questions/<int:question_id>/figures/<int:figure_id>")
@jwt_required()
def delete_question_figure(question_id: int, figure_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    figure = QuestionFigure.query.filter_by(id=figure_id, question_id=question.id).first()
    if not figure:
        abort(404)
    _delete_figure_file(figure)
    db.session.delete(figure)
    remaining = 0
    figure_query = getattr(question, "figures", None)
    if figure_query is not None:
        try:
            remaining = figure_query.count() - 1  # current deletion not yet committed
        except Exception:
            remaining = 0
    if remaining <= 0:
        question.has_figure = False
        db.session.add(question)
    db.session.commit()
    return "", HTTPStatus.NO_CONTENT


@admin_bp.put("/questions/<int:question_id>")
@jwt_required()
def update_question(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    payload = question_create_schema.load(request.get_json() or {})
    question = question_service.get_question(question_id)
    updated = question_service.update_question(question, payload)
    return jsonify({"question": question_schema.dump(updated)})


@admin_bp.delete("/questions/<int:question_id>")
@jwt_required()
def delete_question(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    question_service.delete_question(question)
    return "", HTTPStatus.NO_CONTENT


@admin_bp.post("/questions/<int:question_id>/explanations/clear")
@jwt_required()
def clear_question_explanations(question_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    question = question_service.get_question(question_id)
    cache_deleted = QuestionExplanationCache.query.filter_by(question_id=question.id).delete(
        synchronize_session=False
    )
    UserQuestionLog.query.filter_by(question_id=question.id).update(
        {"explanation": None, "viewed_explanation": False}, synchronize_session=False
    )
    db.session.commit()
    return jsonify({"message": "Cleared cached explanations", "deleted": cache_deleted}), HTTPStatus.OK


@admin_bp.get("/sources")
@jwt_required()
def list_sources_admin():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    search = (request.args.get("search") or "").strip().lower()

    query = QuestionSource.query.order_by(QuestionSource.created_at.desc())
    if search:
        like = f"%{search}%"
        query = query.filter(func.lower(QuestionSource.filename).like(like))
    pagination = _paginate(query, page, per_page)
    items = []
    for source in pagination.items:
        data = _serialize_source(source)
        data["created_at"] = source.created_at.isoformat() if source.created_at else None
        data["question_count"] = source.questions.count()
        items.append(data)
    return jsonify({"items": items, "pagination": _pagination_payload(pagination)})


@admin_bp.get("/sources/<int:source_id>")
@jwt_required()
def get_source_detail(source_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    source = db.session.get(QuestionSource, source_id)
    if not source:
        abort(404)
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))
    questions_query = Question.query.filter_by(source_id=source.id).order_by(Question.id.asc())
    pagination = _paginate(questions_query, page, per_page)
    return jsonify(
        {
            "source": {
                **(_serialize_source(source) or {}),
                "created_at": source.created_at.isoformat() if source.created_at else None,
                "question_count": source.questions.count(),
            },
            "questions": [_serialize_question(q) for q in pagination.items],
            "pagination": _pagination_payload(pagination),
        }
    )


def _serialize_job(job: QuestionImportJob):
    return job.serialize()


def _run_job_async(app, job_id: int) -> None:
    """Background helper to process import jobs without blocking the request."""

    def _target():
        with app.app_context():
            try:
                process_job(job_id)
            finally:
                db.session.remove()

    thread = Thread(target=_target, daemon=True)
    thread.start()


def _dispatch_job(job: QuestionImportJob) -> None:
    """Run job synchronously in tests, asynchronously otherwise."""
    app = current_app._get_current_object()
    if app.config.get("TESTING") or app.config.get("IMPORT_JOBS_SYNC"):
        process_job(job.id)
        db.session.refresh(job)
        return
    _run_job_async(app, job.id)


@admin_bp.post("/questions/upload")
@jwt_required()
def upload_questions():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    _prune_stale_jobs()
    if "file" not in request.files:
        return jsonify({"message": "No file provided"}), HTTPStatus.BAD_REQUEST
    file = request.files["file"]
    filename = secure_filename(file.filename or f"upload-{uuid4().hex}.txt")
    upload_dir = Path(current_app.instance_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    file.save(path)
    job = QuestionImportJob(
        user_id=current_user.id,
        filename=filename,
        source_path=str(path),
        ingest_strategy="classic",
    )
    db.session.add(job)
    db.session.commit()
    _dispatch_job(job)
    job_event_broker.publish({"type": "job", "payload": job.serialize()})
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.post("/questions/ingest-pdf")
@jwt_required()
def ingest_pdf_questions():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    _prune_stale_jobs()
    if "file" not in request.files:
        return jsonify({"message": "No file provided"}), HTTPStatus.BAD_REQUEST
    file = request.files["file"]
    if not file.filename:
        return jsonify({"message": "Filename missing"}), HTTPStatus.BAD_REQUEST
    filename = secure_filename(file.filename)
    force_raw = (request.form.get("force") or request.args.get("force") or "").strip().lower()
    force_replace = force_raw in {"1", "true", "yes", "force", "on"}
    existing_source = (
        QuestionSource.query.filter(func.lower(QuestionSource.filename) == filename.lower())
        .order_by(QuestionSource.created_at.desc())
        .first()
    )
    if existing_source and not force_replace:
        return (
            jsonify(
                {
                    "error": "duplicate_source",
                    "message": "A PDF with this filename already exists in Collections.",
                    "source": _serialize_source(existing_source),
                }
            ),
            HTTPStatus.CONFLICT,
        )
    upload_dir = Path(current_app.instance_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    if path.exists():
        path = upload_dir / f"{uuid4().hex}-{filename}"
    file.save(path)
    source = _create_question_source(
        filename=filename,
        stored_path=path,
        uploader_id=current_user.id,
        original_name=file.filename,
    )
    job = QuestionImportJob(
        user_id=current_user.id,
        filename=filename,
        source_path=str(path),
        source_id=source.id,
        ingest_strategy="vision_pdf",
    )
    db.session.add(job)
    db.session.commit()
    _dispatch_job(job)
    job_event_broker.publish({"type": "job", "payload": job.serialize()})
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.post("/questions/parse")
@jwt_required()
def parse_blocks():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    _prune_stale_jobs()
    payload = manual_parse_schema.load(request.get_json() or {})
    job = QuestionImportJob(
        user_id=current_user.id,
        filename="manual-blocks",
        payload_json=payload["blocks"],
    )
    db.session.add(job)
    db.session.commit()
    _dispatch_job(job)
    job_event_broker.publish({"type": "job", "payload": job.serialize()})
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.get("/questions/imports")
@jwt_required()
def list_imports():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    _prune_stale_jobs()
    jobs = (
        QuestionImportJob.query.order_by(QuestionImportJob.created_at.desc())
        .limit(20)
        .all()
    )
    drafts = [
        draft.serialize()
        for job in jobs
        for draft in job.drafts
    ]
    return jsonify(
        {
            "jobs": [_serialize_job(job) for job in jobs],
            "drafts": drafts,
        }
    )


@admin_bp.get("/questions/drafts/<int:draft_id>/figure-source")
@jwt_required()
def get_draft_figure_source(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = _get_draft_or_404(draft_id)
    job = draft.job
    if not job or not job.source_path:
        return jsonify({"message": "Original upload not available"}), HTTPStatus.BAD_REQUEST
    requested_page = request.args.get("page")
    page = (
        int(requested_page)
        if requested_page and requested_page.isdigit()
        else _extract_draft_page(draft)
    )
    try:
        image, width, height = _render_pdf_page_base64(job.source_path, page)
    except Exception as exc:  # pragma: no cover - defensive
        return jsonify({"message": f"Unable to render page {page}: {exc}"}), HTTPStatus.BAD_REQUEST
    return jsonify({"page": page, "image": image, "width": width, "height": height})


@admin_bp.get("/questions/drafts/<int:draft_id>/figures")
@jwt_required()
def list_draft_figures(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = _get_draft_or_404(draft_id)
    return jsonify({"figures": [_serialize_figure(fig) for fig in draft.figures]})


@admin_bp.post("/questions/drafts/<int:draft_id>/figure")
@jwt_required()
def upload_draft_figure(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = _get_draft_or_404(draft_id)
    if not draft.payload.get("has_figure"):
        return jsonify({"message": "This draft does not require a figure."}), HTTPStatus.BAD_REQUEST
    file = request.files.get("image")
    if file is None:
        return jsonify({"message": "Image file is required."}), HTTPStatus.BAD_REQUEST
    bbox_raw = request.form.get("bbox")
    description = request.form.get("description") or None
    bbox = None
    if bbox_raw:
        try:
            bbox = json.loads(bbox_raw)
        except json.JSONDecodeError:
            return jsonify({"message": "Invalid bbox payload."}), HTTPStatus.BAD_REQUEST
    target_dir = _figure_root() / f"draft_{draft.id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(file.filename or f"draft-{draft.id}-{uuid4().hex}.png")
    path = target_dir / filename
    file.save(path)
    # Replace existing figures for this draft
    for existing in draft.figures.all():
        _delete_figure_file(existing)
        db.session.delete(existing)
    figure = QuestionFigure(draft_id=draft.id, image_path=str(path), description=description, bbox=bbox)
    db.session.add(figure)
    db.session.commit()
    job_event_broker.publish(
        {
            "type": "draft",
            "payload": draft.serialize(),
        }
    )
    return jsonify({"figure": _serialize_figure(figure)}), HTTPStatus.CREATED


@admin_bp.delete("/questions/drafts/<int:draft_id>/figures/<int:figure_id>")
@jwt_required()
def delete_draft_figure(draft_id: int, figure_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = _get_draft_or_404(draft_id)
    figure = draft.figures.filter_by(id=figure_id).first()
    if not figure:
        abort(404)
    _delete_figure_file(figure)
    db.session.delete(figure)
    db.session.commit()
    job_event_broker.publish(
        {
            "type": "draft",
            "payload": draft.serialize(),
        }
    )
    return "", HTTPStatus.NO_CONTENT


@admin_bp.get("/questions/figures/<int:figure_id>/image")
@jwt_required()
def get_figure_image(figure_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    figure = db.session.get(QuestionFigure, figure_id)
    if not figure or not figure.image_path:
        abort(404)
    path = Path(figure.image_path)
    if not path.exists():
        abort(404)
    return send_file(path, mimetype="image/png")


@admin_bp.get("/logs/openai")
@jwt_required()
def get_openai_logs():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    limit = int(request.args.get("limit", 100))
    return jsonify({"logs": openai_log.get_logs(limit)})


@admin_bp.post("/email/test")
@jwt_required()
def send_test_email():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN

    payload = request.get_json() or {}
    recipient = (payload.get("email") or current_user.email or "").strip()
    if not recipient:
        return jsonify({"message": "Recipient email required"}), HTTPStatus.BAD_REQUEST

    subject = (payload.get("subject") or "SAT AI Tutor test email").strip()
    message = (
        payload.get("message")
        or "This is a test email generated by SAT AI Tutor."
    )
    html = payload.get("html") or f"<p>{message}</p>"

    try:
        mail_service.send_email(
            to=recipient,
            subject=subject,
            text=message,
            html=html,
        )
    except mail_service.MailServiceError as exc:
        return (
            jsonify({"message": "mail_failed", "detail": str(exc)}),
            HTTPStatus.BAD_GATEWAY,
        )

    return jsonify({"message": "mail_sent", "recipient": recipient})


@admin_bp.get("/questions/imports/events")
@jwt_required()
def import_events():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN

    def event_stream():
        jobs = (
            QuestionImportJob.query.order_by(QuestionImportJob.created_at.desc())
            .limit(20)
            .all()
        )
        yield f"data: {json.dumps({'type': 'snapshot', 'payload': [job.serialize() for job in jobs]})}\n\n"
        drafts = [draft.serialize() for job in jobs for draft in job.drafts]
        yield f"data: {json.dumps({'type': 'draft_snapshot', 'payload': drafts})}\n\n"
        for message in job_event_broker.listen():
            yield f"data: {message}\n\n"

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@admin_bp.delete("/questions/drafts/<int:draft_id>")
@jwt_required()
def delete_draft(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = db.session.get(QuestionDraft, draft_id)
    if not draft:
        abort(404)
    for figure in draft.figures.all():
        _delete_figure_file(figure)
    db.session.delete(draft)
    db.session.commit()
    job_event_broker.publish({"type": "draft_removed", "payload": {"id": draft_id}})
    return "", HTTPStatus.NO_CONTENT


@admin_bp.post("/questions/drafts/<int:draft_id>/publish")
@jwt_required()
def publish_draft(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = db.session.get(QuestionDraft, draft_id)
    if not draft:
        abort(404)
    payload = _coerce_draft_payload(draft.payload)
    requires_figure = payload.get("has_figure")
    if requires_figure and draft.figures.count() == 0:
        return (
            jsonify(
                {
                    "message": "Figure required",
                    "detail": "Please capture and upload the associated chart before publishing.",
                }
            ),
            HTTPStatus.BAD_REQUEST,
        )
    question_payload = question_create_schema.load(payload)
    if draft.source_id and not question_payload.get("source_id"):
        question_payload["source_id"] = draft.source_id
    question = question_service.create_question(question_payload)
    if requires_figure:
        question.has_figure = True
        db.session.add(question)
    for figure in draft.figures.all():
        _attach_figure_to_question(figure, question.id)
    db.session.delete(draft)
    db.session.commit()
    job_event_broker.publish({"type": "draft_removed", "payload": {"id": draft_id}})
    return jsonify({"question": question_schema.dump(question)}), HTTPStatus.CREATED


@admin_bp.patch("/questions/drafts/<int:draft_id>")
@jwt_required()
def update_draft(draft_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    draft = db.session.get(QuestionDraft, draft_id)
    if not draft:
        abort(404)
    payload = request.get_json() or {}
    try:
        normalized = question_create_schema.load(payload)
    except ValidationError as err:
        return jsonify({"errors": err.messages}), HTTPStatus.BAD_REQUEST
    draft.payload = normalized
    draft.updated_at = datetime.now(timezone.utc)
    db.session.add(draft)
    db.session.commit()
    job_event_broker.publish({"type": "draft", "payload": draft.serialize()})
    return jsonify({"draft": draft.serialize()})


@admin_bp.delete("/questions/imports/<int:job_id>")
@jwt_required()
def cancel_import(job_id: int):
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    job = db.session.get(QuestionImportJob, job_id)
    if not job:
        return jsonify({"message": "Not found"}), HTTPStatus.NOT_FOUND
    if job.status == "processing":
        job.status = "cancelled"
        job.status_message = "Cancelled by admin"
    draft_ids = [draft.id for draft in job.drafts]
    for draft in job.drafts:
        for figure in draft.figures.all():
            _delete_figure_file(figure)
        db.session.delete(draft)
    db.session.delete(job)
    db.session.commit()
    job_event_broker.publish({"type": "job_removed", "payload": {"id": job_id}})
    for draft_id in draft_ids:
        job_event_broker.publish({"type": "draft_removed", "payload": {"id": draft_id}})
    return "", HTTPStatus.NO_CONTENT


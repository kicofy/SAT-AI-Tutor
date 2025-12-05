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

from ..extensions import db
from ..models import (
    QuestionDraft,
    QuestionFigure,
    QuestionImportJob,
    QuestionExplanationCache,
    QuestionSource,
    UserQuestionLog,
)
from ..schemas import ManualParseSchema, QuestionCreateSchema, QuestionSchema
from ..services import question_service, openai_log
from ..services.skill_taxonomy import canonicalize_tags
from ..services.job_events import job_event_broker
from ..tasks.question_tasks import process_job

admin_bp = Blueprint("admin_bp", __name__)

question_create_schema = QuestionCreateSchema()
question_schema = QuestionSchema()
manual_parse_schema = ManualParseSchema()
FIGURE_DIR_NAME = "question_figures"


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

    if not data.get("difficulty_level"):
        data["difficulty_level"] = 2
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
    return jsonify({"question": question_schema.dump(question)})


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
    upload_dir = Path(current_app.instance_path) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
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
    return jsonify(
        {
            "jobs": [_serialize_job(job) for job in jobs],
            "drafts": [
                {
                    "id": draft.id,
                    "job_id": draft.job_id,
                    "source_id": draft.source_id,
                    "source": _serialize_source(draft.source),
                    "is_verified": draft.is_verified,
                    "payload": draft.payload,
                    "figure_count": draft.figures.count(),
                    "figures": [_serialize_figure(fig) for fig in draft.figures],
                }
                for job in jobs
                for draft in job.drafts
            ],
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


@admin_bp.get("/questions/imports/events")
@jwt_required()
def import_events():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN

    def event_stream():
        # send initial snapshot
        jobs = (
            QuestionImportJob.query.order_by(QuestionImportJob.created_at.desc())
            .limit(20)
            .all()
        )
        snapshot = json.dumps(
            {"type": "snapshot", "payload": [job.serialize() for job in jobs]}
        )
        yield f"data: {snapshot}\n\n"
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
    return jsonify({"question": question_schema.dump(question)}), HTTPStatus.CREATED


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
    for draft in job.drafts:
        for figure in draft.figures.all():
            _delete_figure_file(figure)
        db.session.delete(draft)
    db.session.delete(job)
    db.session.commit()
    job_event_broker.publish({"type": "job_removed", "payload": {"id": job_id}})
    return "", HTTPStatus.NO_CONTENT


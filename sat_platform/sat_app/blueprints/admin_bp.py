"""Admin blueprint endpoints."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import current_user, jwt_required
from marshmallow import ValidationError
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import QuestionImportJob, QuestionDraft
from ..schemas import QuestionCreateSchema, QuestionSchema, ManualParseSchema
from ..services import question_service
from ..tasks.question_tasks import process_job

admin_bp = Blueprint("admin_bp", __name__)

question_create_schema = QuestionCreateSchema()
question_schema = QuestionSchema()
manual_parse_schema = ManualParseSchema()


def require_admin():
    return current_user is not None and current_user.role == "admin"


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
    pagination = question_service.list_questions(page, per_page, section)
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


def _serialize_job(job: QuestionImportJob):
    return {
        "id": job.id,
        "filename": job.filename,
        "ingest_strategy": job.ingest_strategy,
        "status": job.status,
        "total_blocks": job.total_blocks,
        "parsed_questions": job.parsed_questions,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


@admin_bp.post("/questions/upload")
@jwt_required()
def upload_questions():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
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
    process_job(job.id)
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.post("/questions/ingest-pdf")
@jwt_required()
def ingest_pdf_questions():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
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
    job = QuestionImportJob(
        user_id=current_user.id,
        filename=filename,
        source_path=str(path),
        ingest_strategy="vision_pdf",
    )
    db.session.add(job)
    db.session.commit()
    process_job(job.id)
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.post("/questions/parse")
@jwt_required()
def parse_blocks():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
    payload = manual_parse_schema.load(request.get_json() or {})
    job = QuestionImportJob(
        user_id=current_user.id,
        filename="manual-blocks",
        payload_json=payload["blocks"],
    )
    db.session.add(job)
    db.session.commit()
    process_job(job.id)
    return jsonify({"job": _serialize_job(job)}), HTTPStatus.ACCEPTED


@admin_bp.get("/questions/imports")
@jwt_required()
def list_imports():
    if not require_admin():
        return jsonify({"message": "Forbidden"}), HTTPStatus.FORBIDDEN
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
                    "is_verified": draft.is_verified,
                    "payload": draft.payload,
                }
                for job in jobs
                for draft in job.drafts
            ],
        }
    )


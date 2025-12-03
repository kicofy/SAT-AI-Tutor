"""Tasks for processing question imports."""

from __future__ import annotations

import json
from pathlib import Path

from ..extensions import db
from ..models import QuestionImportJob, QuestionDraft
from ..utils.file_parser import parse_file
from ..services import ai_question_parser, pdf_ingest_service


def _save_draft(job: QuestionImportJob, payload: dict) -> None:
    draft = QuestionDraft(job_id=job.id, payload=payload)
    db.session.add(draft)


def process_job(job_id: int) -> QuestionImportJob:
    job = db.session.get(QuestionImportJob, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    job.status = "processing"
    db.session.commit()
    try:
        if job.ingest_strategy == "vision_pdf":
            normalized = pdf_ingest_service.ingest_pdf_document(job.source_path)
            job.total_blocks = len(normalized)
            for payload in normalized:
                _save_draft(job, payload)
                job.parsed_questions += 1
                db.session.commit()
        else:
            blocks = _load_blocks(job)
            job.total_blocks = len(blocks)
            for block in blocks:
                payload = ai_question_parser.parse_raw_question_block(block)
                _save_draft(job, payload)
                job.parsed_questions += 1
                db.session.commit()
        job.status = "completed"
        job.error_message = None
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.error_message = str(exc)
    finally:
        db.session.commit()
    return job


def _load_blocks(job: QuestionImportJob):
    if job.source_path:
        path = Path(job.source_path)
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("rb") as stream:
            return parse_file(stream, job.filename or path.name)
    raw = job.payload_json
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [{"type": "text", "content": raw, "metadata": {"source": "manual"}}]
    return raw


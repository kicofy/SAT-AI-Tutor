"""Tasks for processing question imports."""

from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError

from ..extensions import db
from ..models import QuestionImportJob, QuestionDraft
from ..services.job_events import job_event_broker
from ..utils.file_parser import parse_file
from ..services import ai_question_parser, pdf_ingest_service


def _save_draft(job: QuestionImportJob, payload: dict) -> None:
    draft = QuestionDraft(job_id=job.id, payload=payload, source_id=job.source_id)
    db.session.add(draft)
    db.session.flush()
    job_event_broker.publish({"type": "draft", "payload": draft.serialize()})
    db.session.flush()
    job_event_broker.publish({"type": "draft", "payload": draft.serialize()})


def _commit_with_retry(attempts: int = 5, base_delay: float = 0.2) -> None:
    """Commit with simple backoff to reduce SQLite 'database is locked' errors."""
    for attempt in range(attempts):
        try:
            db.session.commit()
            return
        except OperationalError as exc:
            # SQLite lock message commonly contains "database is locked"
            if "locked" not in str(exc).lower():
                raise
            db.session.rollback()
            time.sleep(base_delay * (attempt + 1))
    # final attempt
    db.session.commit()


def process_job(job_id: int, cancel_event=None) -> QuestionImportJob:
    job = db.session.get(QuestionImportJob, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    # Resume-aware: keep existing drafts and continue from next page
    existing_drafts = list(job.drafts)
    base_questions = len(existing_drafts)
    max_page_done = 0
    for draft in existing_drafts:
        try:
            payload_page = draft.payload.get("source_page") or draft.payload.get("page")
            if payload_page is not None:
                max_page_done = max(max_page_done, int(payload_page))
        except Exception:
            continue

    job.status = "processing"
    job.error_message = None
    job.processed_pages = max_page_done
    job.total_pages = job.total_pages or 0
    job.parsed_questions = base_questions
    job.current_page = max_page_done
    job.status_message = (
        "Initializing ingestion"
        if max_page_done == 0
        else f"Resuming from page {max_page_done + 1}"
    )
    job.last_progress_at = datetime.now(timezone.utc)
    _commit_with_retry()
    job_event_broker.publish({"type": "job", "payload": job.serialize()})
    try:
        if job.ingest_strategy == "vision_pdf":
            saved_questions = {"count": base_questions}

            def _progress(page_idx: int, total_pages: int, normalized_count: int, message: str | None = None) -> None:
                job.processed_pages = page_idx
                job.total_pages = total_pages
                if job.source and total_pages:
                    job.source.total_pages = total_pages
                job.parsed_questions = normalized_count
                job.current_page = page_idx
                if message:
                    job.status_message = message
                job.last_progress_at = datetime.now(timezone.utc)
                _commit_with_retry()
                job_event_broker.publish({"type": "job", "payload": job.serialize()})

            def _on_question(payload: dict) -> None:
                _save_draft(job, payload)
                saved_questions["count"] += 1

            pdf_ingest_service.ingest_pdf_document(
                job.source_path,
                progress_cb=_progress,
                question_cb=_on_question,
                job_id=job.id,
                cancel_event=cancel_event,
                start_page=max_page_done + 1,
                base_pages_completed=max_page_done,
                base_questions=base_questions,
            )
            job.total_blocks = saved_questions["count"]
        else:
            blocks = _load_blocks(job)
            job.total_blocks = len(blocks)
            for index, block in enumerate(blocks, start=1):
                payload = ai_question_parser.parse_raw_question_block(block)
                _save_draft(job, payload)
                job.parsed_questions += 1
                job.current_page = index
                job.status_message = f"Normalized block {index}/{len(blocks)}"
                job.last_progress_at = datetime.now(timezone.utc)
                _commit_with_retry()
                job_event_broker.publish({"type": "job", "payload": job.serialize()})
        job.status = "completed"
        job.status_message = "Completed"
        job.error_message = None
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.error_message = str(exc)
        job.status_message = f"Failed: {exc}"
    finally:
        job.last_progress_at = datetime.now(timezone.utc)
        _commit_with_retry()
        job_event_broker.publish({"type": "job", "payload": job.serialize()})
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


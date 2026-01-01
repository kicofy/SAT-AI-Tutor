"""Tasks for processing question imports."""

from __future__ import annotations

import json
import time
from pathlib import Path
from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import ObjectDeletedError

from ..extensions import db
from ..models import QuestionImportJob, QuestionDraft, Question
from ..services.job_events import job_event_broker
from ..utils.file_parser import parse_file
from ..services import ai_question_parser, pdf_ingest_service


def _flush_with_retry(attempts: int = 5, base_delay: float = 0.2) -> None:
    for attempt in range(attempts):
        try:
            db.session.flush()
            return
        except OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            db.session.rollback()
            time.sleep(base_delay * (attempt + 1))
    db.session.flush()


def _save_draft(job: QuestionImportJob, payload: dict) -> None:
    """Upsert draft by coarse_uid to avoid duplicates on resume."""
    coarse_uid = payload.get("coarse_uid")
    if coarse_uid:
        for draft in list(job.drafts):
            try:
                if (draft.payload or {}).get("coarse_uid") == coarse_uid:
                    draft.payload = payload
                    draft.updated_at = datetime.now(timezone.utc)
                    db.session.add(draft)
                    _flush_with_retry()
                    job_event_broker.publish({"type": "draft", "payload": draft.serialize()})
                    return
            except Exception:
                continue
    draft = QuestionDraft(job_id=job.id, payload=payload, source_id=job.source_id)
    db.session.add(draft)
    _flush_with_retry()
    # publish twice (existing behavior) with flush retries to survive locks
    job_event_broker.publish({"type": "draft", "payload": draft.serialize()})
    _flush_with_retry()
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
                db.session.rollback()
                raise
            db.session.rollback()
            time.sleep(base_delay * (attempt + 1))
        except ObjectDeletedError:
            db.session.rollback()
            raise
        except Exception:
            # Any other failure (e.g., row missing -> expected to update 1 row(s); PendingRollbackError)
            db.session.rollback()
            raise
    # final attempt
    db.session.commit()


def _job_exists(job_id: int) -> bool:
    return db.session.get(QuestionImportJob, job_id) is not None


def process_job(job_id: int, cancel_event=None) -> QuestionImportJob:
    job = db.session.get(QuestionImportJob, job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")
    job_id_int = job.id  # stable id to avoid expired attribute access after delete
    # Resume-aware: use already materialized items as the source of truth: drafts + published questions for this source.
    existing_drafts = list(job.drafts)
    draft_count = len(existing_drafts)
    # Count already published questions tied to the same source.
    published_count = (
        db.session.query(Question).filter(Question.source_id == job.source_id).count() if job.source_id else 0
    )
    normalized_count = draft_count + published_count
    max_page_done = job.processed_pages or 0
    source_total_pages = (getattr(job, "source", None) or getattr(job, "source_obj", None))
    try:
        source_total_pages = source_total_pages.total_pages if source_total_pages else 0
    except Exception:
        source_total_pages = 0
    coarse_cache = job.payload_json if isinstance(job.payload_json, list) else []
    # Determine max page present in coarse cache
    coarse_max_page = 0
    for it in coarse_cache:
        try:
            pval = it.get("page") or it.get("page_index")
            if pval is not None:
                coarse_max_page = max(coarse_max_page, int(pval))
        except Exception:
            continue
    # Determine max page from existing drafts (normalized questions)
    max_page_from_drafts = 0
    for draft in existing_drafts:
        try:
            payload_page = draft.payload.get("source_page") or draft.payload.get("page")
            if payload_page is not None:
                max_page_from_drafts = max(max_page_from_drafts, int(payload_page))
        except Exception:
            continue
    # Determine max page from published questions (if any)
    max_page_from_published = 0
    if job.source_id:
        try:
            max_page_from_published = (
                db.session.query(db.func.max(Question.source_page))
                .filter(Question.source_id == job.source_id)
                .scalar()
                or 0
            )
        except Exception:
            max_page_from_published = 0

    max_page_done = max(max_page_done, max_page_from_drafts, max_page_from_published)
    # If coarse pages are already extracted up to processed_pages, skip page extraction on resume
    pages_done = bool(coarse_cache) and max_page_done >= max(coarse_max_page, 0)
    base_questions = normalized_count

    # Use drafts as the only skip baseline. Optionally trim coarse cache so iteration starts after completed items.
    coarse_items_for_ingest = coarse_cache
    if normalized_count > 0 and coarse_cache:
        if normalized_count >= len(coarse_cache):
            coarse_items_for_ingest = []
        else:
            coarse_items_for_ingest = coarse_cache[normalized_count:]
    # If we trim the coarse cache up front, we no longer need to skip inside ingest.
    skip_normalized = 0 if coarse_items_for_ingest is not coarse_cache else normalized_count
    full_total_pages = max(job.total_pages or 0, source_total_pages or 0, coarse_max_page, max_page_done)

    job.status = "processing"
    job.error_message = None
    job.processed_pages = max_page_done
    job.total_pages = full_total_pages
    job.parsed_questions = normalized_count
    job.current_page = max_page_done
    job.status_message = (
        "Initializing ingestion"
        if max_page_done == 0 and not pages_done
        else ("Resuming normalization (pages already extracted)" if pages_done else f"Resuming from page {max_page_done + 1}")
    )
    job.last_progress_at = datetime.now(timezone.utc)
    _commit_with_retry()
    job_event_broker.publish({"type": "job", "payload": job.serialize()})
    try:
        if job.ingest_strategy == "vision_pdf":

            def _progress(
                page_idx: int, total_pages: int, normalized_count: int, message: str | None = None
            ) -> None:
                # if job row was deleted (e.g., cancel/import delete), stop gracefully
                if not _job_exists(job_id_int):
                    raise ObjectDeletedError(f"Job {job_id_int} no longer exists; aborting ingest.", None, None)
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

            def _persist_coarse(items: list[dict]) -> None:
                if not _job_exists(job_id_int):
                    raise ObjectDeletedError(f"Job {job_id_int} no longer exists; aborting ingest.", None, None)
                job.payload_json = items
                _commit_with_retry()

            def _on_question(payload: dict) -> None:
                if not _job_exists(job_id_int):
                    raise ObjectDeletedError(f"Job {job_id_int} no longer exists; aborting ingest.", None, None)
                _save_draft(job, payload)
                job.parsed_questions += 1
                _commit_with_retry()

            pdf_ingest_service.ingest_pdf_document(
                job.source_path,
                progress_cb=_progress,
                question_cb=_on_question,
                job_id=job_id_int,
                cancel_event=cancel_event,
                # If pages already extracted, skip page loop by setting end_page < start_page
                start_page=(max_page_done + 1) if not pages_done else (max_page_done + 1),
                end_page=None if not pages_done else max_page_done,
                base_pages_completed=max_page_done,
                base_questions=base_questions,
                coarse_items=coarse_items_for_ingest,
                skip_normalized_count=skip_normalized,
                coarse_persist=_persist_coarse,
                total_pages_hint=full_total_pages,
            )
            job.total_blocks = job.parsed_questions
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
    except ObjectDeletedError:
        db.session.rollback()
        return job
    except Exception as exc:  # pragma: no cover
        job.status = "failed"
        job.error_message = str(exc)
        job.status_message = f"Failed: {exc}"
    finally:
        try:
            if _job_exists(job_id_int):
                job.last_progress_at = datetime.now(timezone.utc)
                _commit_with_retry()
                job_event_broker.publish({"type": "job", "payload": job.serialize()})
            else:
                db.session.rollback()
        except ObjectDeletedError:
            db.session.rollback()
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



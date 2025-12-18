from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
import random
from datetime import datetime, timedelta
import re
from typing import Any, Dict, List, Optional, Set

from flask import current_app
from sqlalchemy import inspect, text

from ..extensions import db
from ..models import AIPaperJob, QuestionSource, User
from ..models.question import Question
from . import question_service
from .ai_paper_prompts import (
    DIGITAL_SAT_BLUEPRINT,
    build_outline_prompt,
    build_rw_question_prompt,
    build_math_question_prompt,
    build_explanation_prompt,
    build_figure_prompt_guidance,
    RW_TOPIC_SEEDS,
    MATH_TOPIC_SEEDS,
)
from .openai_log import log_event
from .pdf_ingest_service import _call_responses_api
from .validation_service import validate_question, record_issues


_JOB_CANCEL_EVENTS: Dict[int, threading.Event] = {}
_JOB_THREADS: Dict[int, threading.Thread] = {}
_JOB_REGISTRY_LOCK = threading.Lock()
DEFAULT_CANCEL_TIMEOUT = 15
DEFAULT_AUTO_RESUME_SECONDS = 180


DEFAULT_ENGLISH_M1 = [
    {"number_range": [1, 4], "type": "main_idea", "difficulty": "medium", "requires_passage": True},
    {"number_range": [5, 8], "type": "inference", "difficulty": "medium", "requires_passage": True},
    {"number_range": [9, 11], "type": "vocabulary", "difficulty": "medium", "requires_passage": True},
    {"number_range": [12, 14], "type": "logic", "difficulty": "medium", "requires_passage": True},
    {"number_range": [15, 18], "type": "evidence_pair", "difficulty": "medium", "requires_passage": True},
    {"number_range": [19, 27], "type": "grammar", "difficulty": "medium", "requires_passage": False},
]

DEFAULT_ENGLISH_M2 = [
    {"number_range": [1, 6], "type": "inference", "difficulty": "hard", "requires_passage": True},
    {"number_range": [7, 11], "type": "vocabulary", "difficulty": "hard", "requires_passage": True},
    {"number_range": [12, 16], "type": "evidence_pair", "difficulty": "hard", "requires_passage": True},
    {"number_range": [17, 20], "type": "logic", "difficulty": "hard", "requires_passage": True},
    {"number_range": [21, 27], "type": "grammar_complex", "difficulty": "hard", "requires_passage": False},
]

DEFAULT_MATH_M1 = [
    {"number_range": [1, 6], "type": "algebra", "difficulty": "medium"},
    {"number_range": [7, 11], "type": "quadratic", "difficulty": "medium"},
    {"number_range": [12, 15], "type": "ratio_statistics", "difficulty": "medium"},
    {"number_range": [16, 18], "type": "geometry", "difficulty": "medium"},
    {"number_range": [19, 22], "type": "mixed_model", "difficulty": "medium"},
]

DEFAULT_MATH_M2 = [
    {"number_range": [1, 5], "type": "algebra", "difficulty": "hard"},
    {"number_range": [6, 10], "type": "parameter_quadratic", "difficulty": "hard"},
    {"number_range": [11, 14], "type": "statistics", "difficulty": "hard"},
    {"number_range": [15, 18], "type": "advanced_geometry", "difficulty": "hard"},
    {"number_range": [19, 22], "type": "modeling", "difficulty": "hard"},
]


def default_blueprint() -> Dict[str, Any]:
    return {
        "version": "2025.01",
        "modules": [
            {
                "code": "ENG_M1",
                "label": "English · Module 1",
                "subject": "reading_writing",
                "difficulty": "medium",
                "questions": DEFAULT_ENGLISH_M1,
            },
            {
                "code": "ENG_M2",
                "label": "English · Module 2",
                "subject": "reading_writing",
                "difficulty": "hard",
                "questions": DEFAULT_ENGLISH_M2,
            },
            {
                "code": "MATH_M1",
                "label": "Math · Module 1",
                "subject": "math",
                "difficulty": "medium",
                "questions": DEFAULT_MATH_M1,
            },
            {
                "code": "MATH_M2",
                "label": "Math · Module 2",
                "subject": "math",
                "difficulty": "hard",
                "questions": DEFAULT_MATH_M2,
            },
        ],
    }


def _ensure_ai_paper_columns_runtime() -> None:
    inspector = inspect(db.engine)
    if "ai_paper_jobs" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("ai_paper_jobs")}
    dialect = db.engine.dialect.name
    text_type = "TEXT" if dialect == "sqlite" else "VARCHAR(255)"

    statements: List[str] = []
    if "stage" not in columns:
        statements.append(
            f"ALTER TABLE ai_paper_jobs ADD COLUMN stage {text_type} NOT NULL DEFAULT 'pending'"
        )
    if "stage_index" not in columns:
        statements.append(
            "ALTER TABLE ai_paper_jobs ADD COLUMN stage_index INTEGER NOT NULL DEFAULT 0"
        )
    if "status_message" not in columns:
        statements.append("ALTER TABLE ai_paper_jobs ADD COLUMN status_message TEXT")

    if not statements:
        return

    connection = db.engine.connect()
    trans = connection.begin()
    try:
        for statement in statements:
            connection.execute(text(statement))
        trans.commit()
    except Exception:  # pragma: no cover - defensive logging
        trans.rollback()
        current_app.logger.warning(
            "Unable to patch ai_paper_jobs columns automatically", exc_info=True
        )
    finally:
        connection.close()


def _difficulty_level(difficulty: str) -> int:
    diff = (difficulty or "").lower()
    if diff == "hard":
        return 4
    if diff == "easy":
        return 2
    return 3


def _section_for_module(module: dict) -> str:
    return "Math" if (module.get("subject") or "").lower() == "math" else "RW"


def _slot_uid(job_id: int, module_code: str, slot_number: int) -> str:
    return f"JOB{job_id}-{module_code}-{slot_number:02d}"


def _legacy_slot_uid(module_code: str, slot_number: int) -> str:
    return f"{module_code}-{slot_number:02d}"


def _collect_processed_slots(source_id: int, job_id: int, blueprint: dict | None = None) -> Set[str]:
    processed: Set[str] = set()
    fallback_counts: Dict[str, int] = defaultdict(int)
    questions = Question.query.filter_by(source_id=source_id).all()
    for question in questions:
        meta = getattr(question, "metadata_json", None) or {}
        slot_uid = meta.get("slot_uid")
        if slot_uid:
            processed.add(slot_uid)
            continue
        module_code = meta.get("module_code")
        slot_number = meta.get("slot_number") or meta.get("slot")
        if module_code and slot_number is not None:
            try:
                slot_int = int(slot_number)
            except (ValueError, TypeError):
                continue
            processed.add(_slot_uid(job_id, module_code, slot_int))
            continue
        if blueprint:
            module_index = (question.source_page or 0) - 1
            if 0 <= module_index < len(blueprint.get("modules", [])):
                module_code = blueprint["modules"][module_index]["code"]
                fallback_counts[module_code] += 1
                processed.add(_slot_uid(job_id, module_code, fallback_counts[module_code]))
    return processed


def _collect_topic_seeds_for_source(source_id: int) -> Set[str]:
    rows = (
        db.session.query(Question.metadata_json)
        .filter(Question.source_id == source_id, Question.metadata_json.isnot(None))
        .all()
    )
    seeds: Set[str] = set()
    for (meta,) in rows:
        if not meta:
            continue
        seed_id = meta.get("topic_seed")
        if seed_id:
            seeds.add(seed_id)
    return seeds


def _load_recent_topic_seeds(limit: int = 200) -> Set[str]:
    rows = (
        db.session.query(Question.metadata_json)
        .filter(Question.metadata_json.isnot(None))
        .order_by(Question.id.desc())
        .limit(limit)
        .all()
    )
    seeds: Set[str] = set()
    for (meta,) in rows:
        if not meta:
            continue
        seed_id = meta.get("topic_seed")
        if seed_id:
            seeds.add(seed_id)
    return seeds


def _topic_seed_pool(subject: str, question_type: str) -> List[Dict[str, str]]:
    library = RW_TOPIC_SEEDS if subject == "reading_writing" else MATH_TOPIC_SEEDS
    pool = library.get(question_type) or library.get("default", [])
    return [dict(entry) for entry in pool]


def _select_topic_seed(
    *,
    subject: str,
    question_type: str,
    used_ids: Set[str],
    recent_ids: Set[str],
) -> Optional[Dict[str, str]]:
    pool = _topic_seed_pool(subject, question_type)
    if not pool:
        return None
    random.shuffle(pool)

    def _pick(predicate):
        for candidate in pool:
            seed_id = candidate.get("id")
            if not seed_id:
                continue
            if predicate(seed_id):
                used_ids.add(seed_id)
                return candidate
        return None

    choice = _pick(lambda seed_id: seed_id not in used_ids and seed_id not in recent_ids)
    if choice:
        return choice
    choice = _pick(lambda seed_id: seed_id not in used_ids)
    if choice:
        return choice

    fallback = random.choice(pool)
    seed_id = fallback.get("id")
    if seed_id:
        used_ids.add(seed_id)
    return fallback


INLINE_UNDERLINE_PATTERN = re.compile(r"<u>(.*?)</u>", re.IGNORECASE | re.DOTALL)


def _strip_inline_underlines(
    text: str | None,
    *,
    target: str,
) -> tuple[str, List[dict]]:
    if not text:
        return "", []
    if "<u" not in text.lower():
        return text, []
    decorations: List[dict] = []

    def _replace(match: re.Match) -> str:
        snippet = (match.group(1) or "").strip()
        if snippet:
            decorations.append(
                {
                    "target": target,
                    "text": snippet,
                    "action": "underline",
                }
            )
        return match.group(1) or ""

    cleaned = INLINE_UNDERLINE_PATTERN.sub(_replace, text)
    return cleaned, decorations


def _normalize_choices(choices: Any) -> Dict[str, str]:
    normalized: Dict[str, str] = {}
    if isinstance(choices, dict):
        iterator = choices.items()
    elif isinstance(choices, list):
        iterator = []
        for entry in choices:
            if isinstance(entry, dict):
                label = entry.get("label") or entry.get("key")
                text = entry.get("text") or entry.get("value")
                if label and text:
                    iterator.append((label, text))
    else:
        iterator = []
    for label, text in iterator:
        if label is None or text is None:
            continue
        key = str(label).strip().upper()
        if not key:
            continue
        normalized[key] = str(text).strip()
    return normalized


def _prepare_correct_answer(data: dict) -> Dict[str, str] | None:
    correct = data.get("correct_answer")
    if isinstance(correct, dict):
        value = correct.get("value") or correct.get("answer")
    else:
        value = correct
    if not value:
        return None
    return {"value": str(value).strip().upper()}


def _call_question_model(prompt_text: str, *, purpose: str, job_id: int | None) -> dict | None:
    system_prompt = (
        "You are the lead Digital SAT test developer. Respond with STRICT JSON only—no prose, "
        "no markdown. Follow the provided instructions exactly and ensure every object includes "
        "all required fields."
    )
    payload = {
        "model": current_app.config.get("AI_PAPER_GENERATOR_MODEL", "gpt-5.1"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt_text}]},
        ],
        "temperature": 0.3,
    }
    raw = _call_responses_api(payload, purpose=purpose, job_id=job_id)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        current_app.logger.warning("AI paper generator produced invalid JSON: %s", raw[:400])
        return None


def _build_question_payload(
    *,
    data: dict,
    module: dict,
    section_info: dict,
    slot_number: int,
    source_id: int,
    source_page: int,
    prompt_text: str,
    blueprint_version: str,
    job_id: int,
    topic_seed: Optional[dict] = None,
    requires_figure_override: bool = False,
) -> dict | None:
    stem = (data.get("stem_text") or data.get("question") or "").strip()
    stem, stem_decorations = _strip_inline_underlines(stem, target="stem")
    if not stem:
        return None
    choices = _normalize_choices(data.get("choices"))
    if len(choices) < 4:
        return None
    correct = _prepare_correct_answer(data)
    if not correct or correct["value"] not in choices:
        return None
    passage_text = (data.get("passage") or "").strip()
    decorations: List[dict] = []
    decorations.extend(stem_decorations)
    passage_payload = None
    if passage_text:
        passage_text, passage_decorations = _strip_inline_underlines(passage_text, target="passage")
        decorations.extend(passage_decorations)
        passage_payload = {
            "content_text": passage_text,
            "metadata": {"source": "ai_paper", "module": module["code"], "slot": slot_number},
        }
        if passage_decorations:
            passage_payload["metadata"]["decorations"] = passage_decorations

    skill_tags = data.get("skill_tags")
    if isinstance(skill_tags, list):
        normalized_tags = [str(tag).strip() for tag in skill_tags if str(tag).strip()]
        if not normalized_tags:
            normalized_tags = [section_info["type"]]
    else:
        normalized_tags = [section_info["type"]]

    metadata = data.get("metadata") or {}
    if decorations:
        existing = metadata.get("decorations")
        if isinstance(existing, list):
            metadata["decorations"] = existing + decorations
        else:
            metadata["decorations"] = decorations
    if topic_seed:
        metadata["topic_seed"] = topic_seed.get("id")
        metadata["topic_context"] = topic_seed.get("scenario")
        if topic_seed.get("voice"):
            metadata["topic_voice"] = topic_seed["voice"]
        if topic_seed.get("context"):
            metadata["topic_context_detail"] = topic_seed["context"]
    metadata.update(
        {
            "generator": "ai_paper",
            "blueprint_version": blueprint_version,
            "module_code": module["code"],
            "module_label": module["label"],
            "question_type": section_info["type"],
            "slot_number": slot_number,
            "slot_uid": _slot_uid(job_id, module["code"], slot_number),
            "job_id": job_id,
            "prompt": prompt_text,
            "figure_prompt": data.get("figure_prompt"),
            "explanation_plan": data.get("explanation_plan"),
        }
    )

    estimated_time = data.get("expected_time_sec") or data.get("estimated_time_sec")
    try:
        estimated_time = int(estimated_time)
    except (ValueError, TypeError):
        estimated_time = 75 if module.get("subject") == "reading_writing" else 90

    payload = {
        "section": _section_for_module(module),
        "sub_section": None,
        "passage": passage_payload,
        "stem_text": stem,
        "choices": choices,
        "correct_answer": correct,
        "difficulty_level": _difficulty_level(section_info.get("difficulty") or module["difficulty"]),
        "has_figure": bool(data.get("has_figure") or requires_figure_override),
        "skill_tags": normalized_tags,
        "metadata": metadata,
        "estimated_time_sec": estimated_time,
        "source_id": source_id,
        "source_page": source_page,
    }
    # If we forced a figure (e.g., tabular stats), ensure a default figure prompt exists.
    if payload["has_figure"]:
        figure_prompt = data.get("figure_prompt") or metadata.get("figure_prompt")
        if not figure_prompt:
            if module.get("subject") == "math":
                figure_prompt = (
                    "Render a clean SAT-style table summarizing the given data with labeled rows/columns and units."
                )
            else:
                figure_prompt = "Provide a concise diagram/table description suitable for SAT."
        metadata["figure_prompt"] = figure_prompt
    return payload


def _create_question_from_prompt(
    *,
    prompt_text: str,
    module: dict,
    section_info: dict,
    slot_number: int,
    source_id: int,
    source_page: int,
    job_id: int,
    blueprint_version: str,
    stage_label: str | None = None,
    topic_seed: Optional[dict] = None,
    requires_figure_override: bool = False,
) -> Question | None:
    max_attempts = current_app.config.get("AI_PAPER_SLOT_RETRIES", 2)
    for attempt in range(1, max_attempts + 1):
        try:
            data = _call_question_model(
                prompt_text,
                purpose=f"ai-paper {module['code']} slot {slot_number}",
                job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.warning(
                "AI paper slot %s call failed on attempt %s/%s: %s",
                slot_number,
                attempt,
                max_attempts,
                exc,
            )
            continue
        if not data:
            continue
        if isinstance(data, list):
            dict_candidate = next((item for item in data if isinstance(item, dict)), None)
            data = dict_candidate or {}
        if not isinstance(data, dict) or not data:
            _log_job_event(
                job_id,
                stage=stage_label or module.get("code", "ai-paper"),
                message=f"Malformed response for slot {slot_number} (expected JSON object).",
                state="warning",
                extra={"slot": slot_number, "attempt": attempt},
            )
            continue
        try:
            payload = _build_question_payload(
                data=data,
                module=module,
                section_info=section_info,
                slot_number=slot_number,
                source_id=source_id,
                source_page=source_page,
                prompt_text=prompt_text,
                blueprint_version=blueprint_version,
                job_id=job_id,
                topic_seed=topic_seed,
                requires_figure_override=requires_figure_override,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.exception(
                "AI paper slot %s produced malformed structure (attempt %s/%s): %s",
                slot_number,
                attempt,
                max_attempts,
                exc,
            )
            _log_job_event(
                job_id,
                stage=stage_label or module.get("code", "ai-paper"),
                message=f"Slot {slot_number} response could not be parsed ({type(exc).__name__})",
                state="warning",
                extra={"slot": slot_number, "attempt": attempt},
            )
            continue
        if not payload:
            current_app.logger.warning(
                "AI paper slot %s produced incomplete payload (attempt %s/%s)",
                slot_number,
                attempt,
                max_attempts,
            )
            continue
        try:
            question = question_service.create_question(payload, commit=False)
            # Validate before committing
            valid, issues = validate_question(question)
            if not valid:
                record_issues(question, issues)
                current_app.logger.warning(
                    "AI paper slot %s failed validation: %s", slot_number, issues
                )
                continue
            return question
        except Exception as exc:  # pragma: no cover - defensive logging
            current_app.logger.exception(
                "Failed to create AI paper question for slot %s: %s", slot_number, exc
            )
    _log_job_event(
        job_id,
        stage=stage_label or module.get("code", "ai-paper"),
        message=f"Slot {slot_number} failed after {max_attempts} attempt(s)",
        state="warning",
        extra={"slot": slot_number},
    )
    return None


def create_ai_paper_job(name: str, user: User, config: Dict[str, Any] | None = None) -> AIPaperJob:
    if not user or not getattr(user, "id", None):
        raise ValueError("A valid user is required to create an AI paper job.")
    _ensure_ai_paper_columns_runtime()
    job = AIPaperJob(
        name=name,
        status="pending",
        config=config or {},
        created_by_id=user.id if user else None,
    )
    db.session.add(job)
    db.session.commit()

    _spawn_background_job(job.id)
    return job


def list_ai_paper_jobs(page: int = 1, per_page: int = 20):
    return (
        AIPaperJob.query.order_by(AIPaperJob.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )


def get_ai_paper_job(job_id: int) -> AIPaperJob | None:
    return AIPaperJob.query.get(job_id)


def _spawn_background_job(job_id: int) -> None:
    app = current_app._get_current_object()
    cancel_event = threading.Event()

    def _runner():
        try:
            with app.app_context():
                _run_job(job_id, cancel_event)
        finally:
            with _JOB_REGISTRY_LOCK:
                _JOB_CANCEL_EVENTS.pop(job_id, None)
                _JOB_THREADS.pop(job_id, None)

    thread = threading.Thread(target=_runner, name=f"ai-paper-job-{job_id}", daemon=True)
    with _JOB_REGISTRY_LOCK:
        _JOB_CANCEL_EVENTS[job_id] = cancel_event
        _JOB_THREADS[job_id] = thread
    thread.start()


def _log_job_event(
    job_id: int,
    *,
    stage: str,
    message: str,
    state: str = "info",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "job_id": job_id,
        "purpose": "ai-paper",
        "stage": stage,
        "state": state,
        "message": message,
    }
    if extra:
        payload.update(extra)
    try:
        log_event("ai_paper_event", payload)
    except Exception:
        pass


def _run_job(job_id: int, cancel_event: Optional[threading.Event] = None) -> None:
    job = AIPaperJob.query.get(job_id)
    if not job:
        return

    if job.status == "completed":
        return

    stage_index_map: Dict[str, int] = {}

    def should_cancel() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def abort_if_cancelled(message: str = "Job cancelled") -> bool:
        if not should_cancel():
            return False
        job.status = "cancelled"
        job.status_message = message
        job.error = "Cancelled by admin"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(job.id, stage="cancelled", message=message, state="warning")
        return True

    def set_stage(stage_key: str, message: str):
        if abort_if_cancelled("Cancelling job…"):
            return
        job.stage = stage_key
        job.stage_index = stage_index_map.get(stage_key, job.stage_index)
        job.status_message = message
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(job.id, stage=stage_key, message=message, extra={"progress": job.progress})

    try:
        job.status = "running"
        job.stage = job.stage or "queued"
        job.stage_index = job.stage_index or 0
        if job.progress is None:
            job.progress = 0
        if not job.status_message:
            job.status_message = "Queued for generation"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(job.id, stage="queued", message="Job scheduled", extra={"progress": job.progress})
        if abort_if_cancelled("Job cancelled before start"):
            return

        blueprint = job.config.get("blueprint")
        question_prompt_bundles: Dict[str, List[Dict[str, Any]]] = job.config.get("question_prompts") or {}
        if not blueprint:
            blueprint = default_blueprint()
            total_slots = sum(
                section["number_range"][1] - section["number_range"][0] + 1
                for module in blueprint["modules"]
                for section in module["questions"]
            )
            job.total_tasks = total_slots
            job.completed_tasks = 0
            job.progress = 0
            question_prompt_bundles = {}
            job.config = {
                **job.config,
                "blueprint": blueprint,
                "outline_prompt": build_outline_prompt(job.name),
                "figure_prompt_guide": build_figure_prompt_guidance(),
                "explanation_prompts": {
                    "english": build_explanation_prompt("English"),
                    "chinese": build_explanation_prompt("Chinese"),
                },
                "question_prompts": question_prompt_bundles,
            }
            db.session.commit()

        total_slots = job.total_tasks or sum(
            section["number_range"][1] - section["number_range"][0] + 1
            for module in blueprint["modules"]
            for section in module["questions"]
        )
        job.total_tasks = total_slots

        stage_plan = [("outline", "Generating full SAT outline and difficulty map")]
        stage_plan.extend(
            [
                (
                    f"module_{module['code'].lower()}",
                    f"Building {module['label']} ({module['difficulty'].title()} level)",
                )
                for module in blueprint["modules"]
            ]
        )
        stage_plan.append(("finalizing", "Finalizing collection and linking to question bank"))
        stage_index_map = {key: idx for idx, (key, _) in enumerate(stage_plan)}

        uploader_id = job.created_by_id
        if not uploader_id:
            admin_user = User.query.filter_by(is_admin=True).first()
            uploader_id = admin_user.id if admin_user else None
        if not uploader_id:
            job.status = "failed"
            job.error = "No uploader available for generated paper."
            job.updated_at = datetime.utcnow()
            db.session.commit()
            _log_job_event(job.id, stage="error", message="No uploader available", state="error")
            return

        source = db.session.get(QuestionSource, job.source_id) if job.source_id else None
        if not source:
            source = QuestionSource(
                filename=f"{job.name}.json",
                original_name=job.name,
                stored_path=f"ai-generated/{job.id}.json",
                uploaded_by=uploader_id,
                total_pages=len(blueprint["modules"]),
            )
            db.session.add(source)
            db.session.flush()
            job.source_id = source.id
            db.session.commit()

        processed_slots = _collect_processed_slots(source.id, job.id, blueprint)
        recent_topic_ids = _load_recent_topic_seeds()
        used_topic_ids: Set[str] = set(_collect_topic_seeds_for_source(source.id))
        job.completed_tasks = min(len(processed_slots), job.total_tasks or len(processed_slots))
        if job.total_tasks:
            job.progress = int((job.completed_tasks / job.total_tasks) * 100)
        job.stage = "outline"
        job.stage_index = stage_index_map["outline"]
        job.status_message = "Blueprint ready; continuing generation"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(job.id, stage="outline", message="Blueprint ready", extra={"total_tasks": job.total_tasks})

        failed_slots: List[str] = []
        for module_index, module in enumerate(blueprint["modules"], start=1):
            module_prompts: List[Dict[str, Any]] = question_prompt_bundles.setdefault(
                module["code"], []
            )
            for entry in module_prompts:
                seed_info = entry.get("topic_seed")
                if isinstance(seed_info, dict):
                    seed_id = seed_info.get("id")
                    if seed_id:
                        used_topic_ids.add(seed_id)
            stage_key = f"module_{module['code'].lower()}"
            module_has_work = False
            for section in module["questions"]:
                requires_passage = section.get("requires_passage", module.get("subject") == "reading_writing")
                requires_figure = section.get("requires_figure", False)
                force_figure = requires_figure or (
                    module.get("subject") == "math" and section.get("type") in {"ratio_statistics", "statistics"}
                )
                slot_start, slot_end = section["number_range"]
                for slot_number in range(slot_start, slot_end + 1):
                    if abort_if_cancelled("Job cancelled"):
                        return
                    slot_id = _slot_uid(job.id, module["code"], slot_number)
                    legacy_id = _legacy_slot_uid(module["code"], slot_number)
                    if slot_id in processed_slots or legacy_id in processed_slots:
                        continue
                    if not module_has_work:
                        set_stage(stage_key, f"Generating {module['label']} ({module['difficulty'].title()} level)")
                        module_has_work = True
                    slot_entry = next((entry for entry in module_prompts if entry.get("slot") == slot_number), None)
                    config_dirty = False
                    subject = module.get("subject", "")
                    topic_seed = None
                    if slot_entry is None:
                        topic_seed = _select_topic_seed(
                            subject=subject,
                            question_type=section["type"],
                            used_ids=used_topic_ids,
                            recent_ids=recent_topic_ids,
                        )
                        if topic_seed and topic_seed.get("id"):
                            recent_topic_ids.add(topic_seed["id"])
                        prompt_text = (
                            build_rw_question_prompt(
                                module["label"],
                                section.get("difficulty", module["difficulty"]),
                                section["type"],
                                requires_passage,
                                requires_figure,
                                topic_seed=topic_seed,
                            )
                            if subject == "reading_writing"
                            else build_math_question_prompt(
                                module["label"],
                                section.get("difficulty", module["difficulty"]),
                                section["type"],
                                force_figure,
                                topic_seed=topic_seed,
                            )
                        )
                        slot_entry = {
                            "question_type": section["type"],
                            "slot": slot_number,
                            "prompt": prompt_text,
                            "requires_passage": requires_passage,
                            "requires_figure": force_figure,
                            "topic_seed": topic_seed,
                        }
                        module_prompts.append(slot_entry)
                        config_dirty = True
                    else:
                        topic_seed = slot_entry.get("topic_seed")
                        if not topic_seed:
                            topic_seed = _select_topic_seed(
                                subject=subject,
                                question_type=section["type"],
                                used_ids=used_topic_ids,
                                recent_ids=recent_topic_ids,
                            )
                            slot_entry["topic_seed"] = topic_seed
                            config_dirty = True
                        if topic_seed and topic_seed.get("id"):
                            used_topic_ids.add(topic_seed["id"])
                            recent_topic_ids.add(topic_seed["id"])
                        prompt_text = slot_entry.get("prompt")
                        if not prompt_text:
                            prompt_text = (
                                build_rw_question_prompt(
                                    module["label"],
                                    section.get("difficulty", module["difficulty"]),
                                    section["type"],
                                    requires_passage,
                                    requires_figure,
                                    topic_seed=topic_seed,
                                )
                                if subject == "reading_writing"
                                else build_math_question_prompt(
                                    module["label"],
                                    section.get("difficulty", module["difficulty"]),
                                    section["type"],
                                    force_figure,
                                    topic_seed=topic_seed,
                                )
                            )
                            slot_entry["prompt"] = prompt_text
                            config_dirty = True
                    if topic_seed and topic_seed.get("id"):
                        used_topic_ids.add(topic_seed["id"])
                    if config_dirty:
                        job.config = {**job.config, "question_prompts": question_prompt_bundles}
                        db.session.commit()
                    _log_job_event(
                        job.id,
                        stage=stage_key,
                        message=f"Generating slot {slot_number}",
                        extra={"slot": slot_number},
                    )
                    question = _create_question_from_prompt(
                        prompt_text=prompt_text,
                        module=module,
                        section_info=section,
                        slot_number=slot_number,
                        source_id=source.id,
                        source_page=module_index,
                        job_id=job.id,
                        blueprint_version=blueprint["version"],
                        stage_label=stage_key,
                        topic_seed=topic_seed,
                        requires_figure_override=force_figure,
                    )
                    if question:
                        processed_slots.add(slot_id)
                        job.completed_tasks = min(job.completed_tasks + 1, job.total_tasks)
                        if job.total_tasks:
                            job.progress = max(
                                1,
                                min(99, int((job.completed_tasks / job.total_tasks) * 100)),
                            )
                        job.status_message = f"{module['label']} · question {slot_number} generated"
                        _log_job_event(
                            job.id,
                            stage=stage_key,
                            message=f"Slot {slot_number} generated",
                            state="success",
                            extra={
                                "slot": slot_number,
                                "completed": job.completed_tasks,
                                "total": job.total_tasks,
                                "progress": job.progress,
                            },
                        )
                    else:
                        job.status_message = f"{module['label']} · question {slot_number} failed, continuing"
                        failed_slots.append(f"{module['code']}-{slot_number}")
                        _log_job_event(
                            job.id,
                            stage=stage_key,
                            message=f"Slot {slot_number} failed, will continue",
                            state="warning",
                            extra={"slot": slot_number},
                        )
                    job.updated_at = datetime.utcnow()
                    db.session.commit()
                    if abort_if_cancelled("Job cancelled"):
                        return

        set_stage("finalizing", "Finalizing collection and linking to question bank")
        if job.total_tasks:
            job.progress = min(100, int((job.completed_tasks / job.total_tasks) * 100))
        if failed_slots:
            job.status = "completed"
            job.error = (
                f"Failed slots: {', '.join(failed_slots[:8])}" + ("..." if len(failed_slots) > 8 else "")
            )
            job.status_message = (
                f"Generated {job.completed_tasks}/{job.total_tasks} questions "
                f"({len(failed_slots)} failed)."
            )
        else:
            job.completed_tasks = job.total_tasks
            job.progress = 100
            job.status = "completed"
            job.status_message = "AI paper ready for review"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(
            job.id,
            stage="completed",
            message="AI paper generation complete",
            state="success",
            extra={"completed": job.completed_tasks, "total": job.total_tasks},
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        db.session.rollback()
        current_app.logger.exception("AI paper job %s crashed: %s", job_id, exc)
        job = AIPaperJob.query.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.error = str(exc)
        short_error = str(exc)
        if len(short_error) > 140:
            short_error = short_error[:137] + "..."
        job.status_message = f"Generation failed: {short_error}"
        job.updated_at = datetime.utcnow()
        db.session.commit()
        _log_job_event(job_id, stage="error", message=short_error, state="error")


def _queue_job_for_resume(job: AIPaperJob, message: str) -> AIPaperJob:
    job.status = "pending"
    job.stage = "queued"
    job.stage_index = 0
    job.status_message = message
    job.error = None
    job.updated_at = datetime.utcnow()
    db.session.commit()
    _log_job_event(job.id, stage="queued", message=message, state="info", extra={"progress": job.progress})
    _spawn_background_job(job.id)
    return job


def resume_ai_paper_job(job_id: int) -> AIPaperJob:
    job = AIPaperJob.query.get(job_id)
    if not job:
        raise ValueError("Job not found")
    if job.status == "completed":
        return job
    return _queue_job_for_resume(job, "Resuming generator")


def auto_resume_stalled_jobs(max_age_seconds: int | None = None) -> list[int]:
    """Automatically re-queue any job that has been idle for too long."""
    threshold = max_age_seconds or int(
        current_app.config.get("AI_PAPER_AUTO_RESUME_SECONDS", DEFAULT_AUTO_RESUME_SECONDS)
    )
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=threshold)
    candidates = (
        AIPaperJob.query.filter(
            AIPaperJob.status.in_(("running", "pending")), AIPaperJob.updated_at < stale_before
        )
        .order_by(AIPaperJob.updated_at.asc())
        .all()
    )
    restarted: list[int] = []
    for job in candidates:
        _queue_job_for_resume(job, "Auto-resume after inactivity")
        restarted.append(job.id)
    return restarted


def delete_ai_paper_job(job_id: int) -> None:
    job = AIPaperJob.query.get(job_id)
    if not job:
        raise ValueError("Job not found")
    with _JOB_REGISTRY_LOCK:
        cancel_event = _JOB_CANCEL_EVENTS.get(job_id)
        thread = _JOB_THREADS.get(job_id)
    if job.status == "running":
        job.status = "cancelling"
        job.status_message = "Cancelling job before deletion…"
        job.error = None
        job.updated_at = datetime.utcnow()
        db.session.commit()
        if cancel_event:
            cancel_event.set()
        if thread and thread.is_alive():
            timeout = current_app.config.get("AI_PAPER_CANCEL_TIMEOUT", DEFAULT_CANCEL_TIMEOUT)
            thread.join(timeout=timeout)
            if thread.is_alive():
                raise RuntimeError("job_cancel_timeout")
        job = AIPaperJob.query.get(job_id)
        if not job:
            return
    source_id = job.source_id
    if source_id:
        questions = Question.query.filter_by(source_id=source_id).all()
        for question in questions:
            question_service.delete_question(question, commit=False)
        db.session.flush()
        question_service.cleanup_source_if_unused(source_id)
    db.session.delete(job)
    db.session.commit()


"""Vision-aware PDF ingestion powered by multimodal AI."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeout,
    CancelledError,
    wait,
    FIRST_COMPLETED,
)
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import pdfplumber
import requests
from flask import current_app

from ..schemas.question_schema import QuestionCreateSchema
from .openai_log import log_event
from .skill_taxonomy import canonicalize_tags, iter_skill_tags
from .difficulty_service import difficulty_prompt_block
from .validation_service import validate_question, record_issues
from . import ai_explainer
from . import question_explanation_service

question_schema = QuestionCreateSchema()
SKILL_TAG_PROMPT = ", ".join(iter_skill_tags())
ProgressCallback = Callable[[int, int, int, Optional[str]], None]

AttemptHook = Callable[
    [Literal["start", "retry", "success", "heartbeat"], int, int, float, Optional[Exception]],
    None,
]


def _parse_numeric_str(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 2:
            try:
                return float(parts[0]) / float(parts[1])
            except Exception:
                return None
    try:
        return float(text)
    except Exception:
        return None

def _extract_question_number(payload: Dict[str, Any]) -> str | int | None:
    for key in (
        "question_number",
        "original_question_number",
        "source_question_number",
        "question_index",
    ):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def ingest_pdf_document(
    source_path: str | Path,
    progress_cb: Optional[ProgressCallback] = None,
    question_cb: Optional[Callable[[dict], None]] = None,
    job_id: int | None = None,
    cancel_event: Optional[threading.Event] = None,
    *,
    start_page: int = 1,
    base_pages_completed: int = 0,
    base_questions: int = 0,
) -> List[dict]:
    """Parse a PDF file and return normalized question payloads."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)

    if cancel_event and cancel_event.is_set():
        return []
    pages = _extract_pages(path)
    normalized: List[dict] = []
    total_pages = len(pages)
    app = current_app._get_current_object()
    worker_limit = max(1, int(current_app.config.get("PDF_INGEST_MAX_WORKERS", 4)))
    max_workers = min(worker_limit, max(1, total_pages))
    if progress_cb:
        progress_cb(
            base_pages_completed,
            total_pages,
            base_questions,
            f"Starting PDF ingestion with {max_workers} worker(s)",
        )

    max_wait = current_app.config.get("AI_READ_TIMEOUT_SEC", 60)

    def _make_attempt_hook(
        stage: str,
        page_idx: int,
        total_pages: int,
        count_getter: Callable[[], int],
        job_id: int | None,
        progress_callback: Optional[ProgressCallback] = progress_cb,
    ):
        def _hook(
            state: Literal["start", "retry", "success", "heartbeat"],
            attempt: int,
            max_attempts: int,
            wait_seconds: float,
            error: Exception | None,
        ) -> None:
            normalized_count = count_getter()
            message: str
            if state == "start":
                message = (
                    f"{stage} (attempt {attempt}/{max_attempts}) — this step can take up to {max_wait}s."
                )
            elif state == "success":
                message = f"{stage} completed (attempt {attempt}/{max_attempts})."
            elif state == "heartbeat":
                elapsed = int(max(wait_seconds, 0))
                message = f"{stage} still running (elapsed {elapsed}s)..."
            else:
                message = (
                    f"{stage} attempt {attempt}/{max_attempts} failed"
                    + (f": {error}" if error else "")
                    + (f"; retrying in {wait_seconds:.1f}s" if wait_seconds else "")
                )
            if progress_callback:
                progress_callback(page_idx, total_pages, normalized_count, message)
            kind = {
                "start": "openai_attempt",
                "retry": "openai_retry",
                "success": "openai_stage_complete",
                "heartbeat": "openai_wait",
            }.get(state, "openai_event")
            log_event(
                kind,
                {
                    "job_id": job_id,
                    "stage": stage,
                    "state": state,
                    "page": page_idx,
                    "total_pages": total_pages,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "normalized_count": normalized_count,
                    "wait_seconds": wait_seconds,
                    "error": str(error) if error else None,
                    "message": message,
                },
            )

        return _hook

    def _process_page(page_index: int, page_data: Dict[str, Any]):
        if cancel_event and cancel_event.is_set():
            return page_index, [], "Cancelled"
        with app.app_context():
            local_normalized: List[dict] = []
            message: str | None = None
            try:
                questions = _request_page_questions(
                    page_data,
                    page_index=page_index,
                    attempt_hook=_make_attempt_hook(
                        f"Extracting page {page_index}/{total_pages}",
                        page_index,
                        total_pages,
                        lambda: len(local_normalized),
                        job_id,
                        progress_callback=None,
                    ),
                    job_id=job_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                current_app.logger.warning(
                    "PDF ingest: failed to parse page %s, skipping. %s", page_index, exc
                )
                message = f"Skipped page {page_index}/{total_pages}: {exc}"
                return page_index, local_normalized, message
            if not questions:
                message = f"Page {page_index}/{total_pages}: no questions found"
                return page_index, local_normalized, message
            for raw_question in questions:
                if cancel_event and cancel_event.is_set():
                    return page_index, local_normalized, "Cancelled"
                try:
                    payload = _normalize_question(
                        raw_question,
                        page_image_b64=page_data.get("image_b64"),
                        attempt_hook=_make_attempt_hook(
                            f"Normalizing question from page {page_index}/{total_pages}",
                            page_index,
                            total_pages,
                            lambda: len(local_normalized),
                            job_id,
                            progress_callback=None,
                        ),
                        job_id=job_id,
                    )
                    local_normalized.append(payload)
                except Exception as exc:  # pragma: no cover - guarded by unit tests
                    current_app.logger.warning(
                        "PDF ingest: failed to normalize question on page %s: %s",
                        page_index,
                        exc,
                    )
            if not message:
                message = (
                    f"Normalized {len(local_normalized)} question(s) from page "
                    f"{page_index}/{total_pages}"
                )
            return page_index, local_normalized, message

    page_timeout = max(
        90,
        int(
            current_app.config.get(
                "PDF_INGEST_PAGE_TIMEOUT_SEC",
                (current_app.config.get("AI_CONNECT_TIMEOUT_SEC", 15) + current_app.config.get("AI_READ_TIMEOUT_SEC", 120)) * current_app.config.get("AI_API_MAX_RETRIES", 3)
                + 30,
            )
        ),
    )
    heartbeat_interval = 5.0
    futures = []
    future_started_at: dict = {}
    future_page: dict = {}
    completed_pages = base_pages_completed
    normalized_count = base_questions
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, page in enumerate(pages, start=1):
            if idx < start_page:
                continue
            if cancel_event and cancel_event.is_set():
                break
            future = executor.submit(_process_page, idx, page)
            futures.append(future)
            future_started_at[future] = time.perf_counter()
            future_page[future] = idx

        while futures:
            done, pending = wait(futures, timeout=heartbeat_interval, return_when=FIRST_COMPLETED)
            now = time.perf_counter()

            # Cancel and report any pages that exceeded the watchdog timeout
            for future in list(pending):
                started_at = future_started_at.get(future, now)
                elapsed = now - started_at
                if elapsed >= page_timeout:
                    page_idx = future_page.get(future)
                    future.cancel()
                    futures.remove(future)
                    future_started_at.pop(future, None)
                    future_page.pop(future, None)
                    if progress_cb:
                        progress_cb(
                            completed_pages,
                            total_pages,
                            normalized_count,
                            f"Page {page_idx}/{total_pages} timed out after {int(elapsed)}s; skipped",
                        )
                    current_app.logger.warning(
                        "PDF ingest: page %s timed out after %.1fs; cancelled", page_idx, elapsed
                    )

            if not done:
                continue

            for future in done:
                futures.remove(future)
                page_index = future_page.pop(future, None)
                future_started_at.pop(future, None)
                if cancel_event and cancel_event.is_set():
                    break
                try:
                    page_result = future.result()
                    if page_result is None:
                        continue
                    page_index, payloads, message = page_result
                except CancelledError:
                    continue
                except Exception as exc:  # pragma: no cover - defensive logging
                    current_app.logger.exception("PDF ingest: worker failed", exc_info=exc)
                    if progress_cb:
                        progress_cb(
                            completed_pages,
                            total_pages,
                            len(normalized),
                            f"Worker error on page {page_index}: {exc}",
                        )
                    continue

                completed_pages += 1
                for payload in payloads:
                    normalized.append(payload)
                    normalized_count += 1
                    # Pre-generate explanations for all questions (choice/fill, with or without figures)
                    _attach_precomputed_explanations(payload)
                    if question_cb:
                        question_cb(payload)
                if progress_cb:
                    progress_cb(
                        completed_pages,
                        total_pages,
                        normalized_count,
                        message or f"Finished page {page_index}/{total_pages}",
                    )
    return normalized


def _extract_pages(path: Path) -> List[Dict[str, Any]]:
    """Render each page to base64 PNG plus extract plain text."""
    app = current_app
    resolution = app.config.get("PDF_INGEST_RESOLUTION", 220)
    max_pages = app.config.get("PDF_INGEST_MAX_PAGES", 200)
    pages: List[Dict[str, Any]] = []
    try:
        with pdfplumber.open(path) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                if idx > max_pages:
                    break
                try:
                    text = (page.extract_text() or "").strip()
                except Exception as exc:
                    app.logger.warning("PDF ingest: extract_text failed on page %s: %s", idx, exc)
                    text = ""
                image_b64 = _page_to_base64_safe(page, resolution)
                pages.append({"page_number": idx, "text": text, "image_b64": image_b64})
        return pages
    except Exception as exc:
        app.logger.warning("PDF ingest: pdfplumber failed on %s (%s). Falling back to text-only.", path, exc)

    # Fallback: text-only extraction via PyPDF2 (no images)
    try:
        from PyPDF2 import PdfReader
    except Exception as exc:
        app.logger.error("PDF ingest: PyPDF2 not available for fallback: %s", exc)
        return pages

    try:
        reader = PdfReader(str(path))
        for idx, page in enumerate(reader.pages, start=1):
            if idx > max_pages:
                break
            try:
                text = (page.extract_text() or "").strip()
            except Exception:
                text = ""
            pages.append({"page_number": idx, "text": text, "image_b64": None})
    except Exception as exc:
        app.logger.error("PDF ingest: fallback reader failed on %s: %s", path, exc)
    return pages


def _page_to_base64_safe(page, resolution: int) -> str | None:
    try:
        page_image = page.to_image(resolution=resolution).original.convert("RGB")
        buffer = io.BytesIO()
        page_image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        current_app.logger.warning("PDF ingest: page render failed, using text-only. %s", exc)
        return None


def _request_page_questions(
    page_data: Dict[str, Any],
    page_index: int,
    attempt_hook: Optional[
        Callable[[Literal["start", "retry"], int, int, float, Exception | None], None]
    ] = None,
    job_id: int | None = None,
) -> List[dict]:
    text = page_data.get("text", "")
    image_b64 = page_data.get("image_b64")
    if not text and not image_b64:
        return []

    schema = {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_number": {"type": "string"},
                        "section": {"type": "string"},
                        "passage": {"type": "string"},
                        "prompt": {"type": "string"},
                        "has_figure": {"type": "boolean"},
                        "choices": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["label", "text"],
                            },
                        },
                        "highlights": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                },
                                "required": ["text"],
                            },
                            "default": [],
                        },
                    },
                    "required": ["question_number", "prompt", "choices", "has_figure"],
                },
            }
        },
        "required": ["questions"],
    }

    schema_hint = json.dumps(schema, ensure_ascii=False, indent=2)
    system_prompt = (
        "You are an SAT content extraction assistant. Your ONLY task is to emit JSON "
        "that matches the provided schema exactly. Each question entry must include:\n"
        "- `passage`: ONLY the supporting narrative text that precedes the question (no questions and no tables/charts). If details appear only inside a table/figure, DO NOT copy the numbers/text; simply leave the passage empty or refer to the figure in words (e.g., \"Refer to the pyramid table\").\n"
        "- `prompt`: ONLY the interrogative sentence(s) that ask what the student must do (e.g., the 'Which choice...' line).\n"
        "- `choices`: every answer choice with explicit labels (A/B/C/...).\n"
        "- `has_figure`: true if the question references a chart, table, graph, map, image or any visual data (including ASCII tables). When true, DO NOT copy the figure contents into `passage` or `prompt`; the platform will display the cropped figure separately.\n"
        "- `skill_tags`: choose up to two tags from this canonical list only: "
        f"{SKILL_TAG_PROMPT}. If none apply, use an empty array.\n"
        "- `highlights`: SAT passages occasionally contain underlined phrases. Capture ONLY those passage snippets (no other targets) as {\"text\": \"exact underlined substring\"}. Always pull from the passage text.\n"
        "If a page has zero questions, respond with {\"questions\": []}. Never include commentary, markdown, explanations, or figure text."
    )
    user_prompt = (
        f"You are examining page {page_index} of an SAT prep PDF. Identify each complete question, "
        "including passages or tables if they are part of the item. Return JSON that follows this schema:\n"
        f"{schema_hint}\nRemember: respond with STRICT JSON only, and never copy raw table/figure text into the passage or choices—simply reference the figure verbally if needed."
    )

    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if text:
        user_content.append({"type": "input_text", "text": text[:12000]})
    if image_b64:
        user_content.append({"type": "input_image", "image_url": image_b64})

    payload = {
        "model": current_app.config.get("AI_PDF_VISION_MODEL", "gpt-5.1"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    raw_text = _call_responses_api(
        payload,
        purpose=f"page {page_index} extraction",
        attempt_hook=attempt_hook,
        job_id=job_id,
    )
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        current_app.logger.warning("PDF ingest: invalid JSON on page %s: %s", page_index, raw_text[:200])
        return []
    questions = data.get("questions", [])
    if isinstance(questions, list):
        normalized_questions = []
        for q in questions:
            entry = dict(q)
            entry["page"] = page_index
            entry["has_figure"] = bool(entry.get("has_figure"))
            entry["highlights"] = _sanitize_highlights(entry.get("highlights"))
            source_number = _extract_question_number(entry)
            if source_number is not None:
                entry["source_question_number"] = source_number
            normalized_questions.append(entry)
        return normalized_questions
    return []


def _normalize_question(
    question_payload: dict,
    *,
    page_image_b64: str | None = None,
    attempt_hook: Optional[
        Callable[[Literal["start", "retry"], int, int, float, Exception | None], None]
    ] = None,
    job_id: int | None = None,
) -> dict:
    system_prompt = (
        "You are an SAT content normalizer. Convert extracted question snippets into the canonical "
        "JSON schema used by the SAT AI Tutor platform. Output MUST be a single JSON object with:\n"
        "- section: \"RW\" or \"Math\".\n"
        "- sub_section: optional string or null.\n"
        "- passage: ONLY the supporting narrative text (introductory paragraphs). Do NOT include chart/table contents, figure titles, or the question sentence. Leave as null if no prose passage exists.\n"
        "- stem_text: ONLY the interrogative portion (e.g., \"Which choice ...?\"). Never prepend the passage or restate figure/table data verbatim. Preserve math notation in LaTeX form; allow inline $...$ or \\(...\\) and block $$...$$ without escaping backslashes.\n"
        "- choices: object whose keys are capital letters (A,B,C,...) and values are choice texts. If the item is NOT multiple-choice, set choices to {}.\n"
        "- question_type: \"choice\" for multiple-choice, \"fill\" for student-produced response (SPR). If there are no valid lettered choices, default to \"fill\".\n"
        "- correct_answer: object like {\"value\": \"A\"} for MCQ, or {\"value\": \"3.5\"} for fill.\n"
        "- answer_schema: for fill questions, include a dict: {\"type\": \"numeric\" or \"text\", \"acceptable\": [...], \"tolerance\": number|null, \"allow_fraction\": true, \"allow_pi\": true, \"strip_spaces\": true}. **List EVERY scoring-equivalent form** (fractions, decimals, π forms, simplified radicals, sign variants when applicable). If only a canonical value is known, still place it in acceptable.\n"
        "  SAT grid-in length rule: each acceptable answer must be ≤5 characters; decimal point counts; leading minus sign does NOT count. Prefer exact/simplified fractions or terminating decimals that fit; for repeating decimals, provide a rounded form within 5 chars.\n"
        "- has_figure: boolean for figures/tables that belong to the passage/stem (not the answer options).\n"
        "- choice_figure_keys: array of choice letters that rely on their OWN figure/table/image inside the option. Use uppercase letters. If no option has its own figure, return an empty array. Do NOT set has_figure just because an option contains a figure; use choice_figure_keys instead.\n"
        "- difficulty_level: integer 1-5. "
        "Use the rubric below and also provide a difficulty_assessment object describing reasoning and expected_time_sec.\n"
        "- skill_tags: choose up to TWO entries from this canonical list only: "
        f"{SKILL_TAG_PROMPT}. Return an empty array if unsure.\n"
        "- metadata: optional dict for provenance info.\n"
        "Do NOT include legacy fields such as prompt, metadata_json, or explanations. Respond with JSON only.\n"
        f"{difficulty_prompt_block()}\n"
        "difficulty_assessment must be shaped like "
        '{"level":3,"expected_time_sec":75,"rationale":"Two-step evidence match."}'
    )
    schema_hint = ""
    user_prompt = json.dumps(question_payload, ensure_ascii=False, indent=2)
    payload = {
        "model": current_app.config.get("AI_PDF_NORMALIZE_MODEL", "gpt-5.1"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": f"{system_prompt} {schema_hint}"}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Normalize the following extracted SAT question and return ONLY JSON:\n"
                        + user_prompt,
                    }
                ],
            },
        ],
        "temperature": 0.1,
    }
    if page_image_b64:
        payload["input"][1]["content"].append({"type": "input_image", "image_url": page_image_b64})
    if page_image_b64:
        payload["input"][1]["content"].append({"type": "input_image", "image_url": page_image_b64})
    raw_text = _call_responses_api(
        payload,
        purpose="question normalization",
        attempt_hook=attempt_hook,
        job_id=job_id,
    )
    data = json.loads(raw_text)
    difficulty_assessment = data.pop("difficulty_assessment", None)

    data["section"] = _coerce_section(data.get("section"))
    # Normalize choice figure keys: list of uppercase letters.
    raw_choice_keys = data.get("choice_figure_keys") or []
    normalized_choice_keys: list[str] = []
    if isinstance(raw_choice_keys, list):
        for key in raw_choice_keys:
            if not isinstance(key, str):
                continue
            k = key.strip().upper()
            if len(k) == 1 and k.isalpha():
                normalized_choice_keys.append(k)
    data["choice_figure_keys"] = normalized_choice_keys
    data["has_figure"] = bool(question_payload.get("has_figure") or normalized_choice_keys)
    if question_payload.get("page"):
        page_value = question_payload.get("page")
        data.setdefault("page", str(page_value))
        try:
            data["source_page"] = int(page_value)
        except (TypeError, ValueError):
            pass
    source_number = _extract_question_number(question_payload)
    if source_number is not None:
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["source_question_number"] = source_number
        data["metadata"] = metadata
    raw_choices = data.get("choices")
    normalized_choices = _normalize_choices(raw_choices)
    if normalized_choices:
        data["choices"] = normalized_choices
    if not normalized_choices:
        data["question_type"] = data.get("question_type") or "fill"
    else:
        data["question_type"] = data.get("question_type") or "choice"

    # Build/validate answer_schema for fill-in questions; require acceptable answers
    if data["question_type"] == "fill":
        answer_schema = data.get("answer_schema") or {}
        if not isinstance(answer_schema, dict):
            answer_schema = {}
        correct_val = data.get("correct_answer", {}).get("value")
        if correct_val is not None:
            acc = answer_schema.get("acceptable") or []
            if not acc:
                answer_schema["acceptable"] = [str(correct_val).strip()]
        answer_schema.setdefault("type", "numeric" if _parse_numeric_str(correct_val) is not None else "text")
        answer_schema.setdefault("allow_fraction", True)
        answer_schema.setdefault("allow_pi", True)
        answer_schema.setdefault("strip_spaces", True)
        acceptable = answer_schema.get("acceptable") or []
        if not acceptable:
            raise ValueError("Fill question missing acceptable answers")
        data["answer_schema"] = answer_schema
    raw_answer = data.get("correct_answer")
    if isinstance(raw_answer, str):
        data["correct_answer"] = {"value": raw_answer.strip() or None}
    elif not isinstance(raw_answer, dict):
        data["correct_answer"] = {"value": None}
    passage_payload = data.get("passage")
    normalized_passage = _normalize_passage(passage_payload)
    if normalized_passage:
        data["passage"] = normalized_passage
    elif "passage" in data:
        data["passage"] = None
    data["skill_tags"] = _sanitize_skill_tags(data.get("skill_tags"))
    normalized = question_schema.load(data)
    if difficulty_assessment:
        metadata = normalized.get("metadata") or {}
        metadata["difficulty_assessment"] = difficulty_assessment
        normalized["metadata"] = metadata
        expected_time = difficulty_assessment.get("expected_time_sec")
        if expected_time and not normalized.get("estimated_time_sec"):
            normalized["estimated_time_sec"] = int(expected_time)
    decorations = _extract_decorations(question_payload)
    if decorations:
        metadata = normalized.get("metadata") or {}
        metadata["decorations"] = decorations
        normalized["metadata"] = metadata
    solver_result = None
    correct_answer = normalized.get("correct_answer") or {}
    correct_value = correct_answer.get("value") if isinstance(correct_answer, dict) else None
    if not correct_value:
        solver_result = _solve_question_with_ai(
            normalized,
            question_payload=question_payload,
            page_image_b64=page_image_b64,
            job_id=job_id,
        )
    if solver_result:
        answer_value = solver_result.get("answer_value")
        reasoning = solver_result.get("solution")
        if answer_value:
            if not normalized.get("correct_answer"):
                normalized["correct_answer"] = {}
            normalized["correct_answer"]["value"] = answer_value
        if reasoning:
            metadata = normalized.get("metadata") or {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["ai_solution"] = reasoning
            normalized["metadata"] = metadata
    # Validate normalized question; if invalid, record issues and skip
    temp_question = Question(**normalized)
    valid, issues = validate_question(temp_question)
    if not valid:
        record_issues(temp_question, issues)
        return None
    return normalized


def _attach_precomputed_explanations(payload: dict) -> None:
    # Skip pre-generation when the item depends on cropped figures (main or option images).
    has_main_figure = bool(payload.get("has_figure"))
    choice_keys = payload.get("choice_figure_keys") or []
    if has_main_figure or (isinstance(choice_keys, list) and any(str(k).strip() for k in choice_keys)):
        return
    try:
        explanations = question_explanation_service.generate_explanations_for_payload(payload)
    except ai_explainer.AiExplainerError as exc:  # pragma: no cover - logging only
        current_app.logger.warning(
            "PDF ingest: explanation skipped due to AI error",
            extra={"error": str(exc), "question_uid": payload.get("question_uid")},
        )
        return
    except Exception:  # pragma: no cover - defensive logging
        current_app.logger.exception(
            "PDF ingest: unexpected failure during explanation generation",
            extra={"question_uid": payload.get("question_uid")},
        )
        return
    if explanations:
        payload["_ai_explanations"] = explanations


def _sanitize_skill_tags(raw_tags: Any) -> List[str]:
    if isinstance(raw_tags, list):
        return canonicalize_tags(raw_tags, limit=2)
    return []


def _sanitize_highlights(raw_highlights: Any) -> List[dict]:
    if not isinstance(raw_highlights, list):
        return []
    cleaned: List[dict] = []
    for entry in raw_highlights:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        if not text:
            continue
        cleaned.append({"text": str(text)})
    return cleaned


def _extract_decorations(question_payload: dict) -> List[dict]:
    highlights = _sanitize_highlights(question_payload.get("highlights"))
    decorations: List[dict] = []
    for highlight in highlights:
        snippet = (highlight.get("text") or "").strip()
        if not snippet:
            continue
        decorations.append({"target": "passage", "text": snippet, "action": "underline"})
    return decorations

def _normalize_choices(raw_choices: Any) -> Dict[str, str]:
    if isinstance(raw_choices, dict):
        normalized: Dict[str, str] = {}
        for key, value in raw_choices.items():
            label = str(key).strip().upper()
            if not label:
                continue
            normalized[label] = value if isinstance(value, str) else str(value)
        return normalized
    if isinstance(raw_choices, list):
        normalized: Dict[str, str] = {}
        for idx, choice in enumerate(raw_choices):
            if not isinstance(choice, dict):
                continue
            label = (choice.get("label") or "").strip().upper()
            if not label:
                label = chr(ord("A") + idx)
            text = choice.get("text") or choice.get("value") or ""
            normalized[label] = text
        return normalized
    return {}


def _solve_question_with_ai(
    normalized_question: dict,
    *,
    question_payload: dict,
    page_image_b64: str | None,
    job_id: int | None,
) -> dict | None:
    app = current_app
    choices = normalized_question.get("choices") or {}
    if not choices:
        return None
    model_name = app.config.get("AI_PDF_SOLVER_MODEL") or app.config.get(
        "AI_PDF_NORMALIZE_MODEL", "gpt-5.1"
    )
    system_prompt = (
        "You are an SAT solving assistant. Determine the single best answer choice.\n"
        "Respond with pure JSON: {\"answer_value\": \"A\", \"solution\": \"step-by-step reasoning\"}.\n"
        "The answer_value must be one of the provided choice letters. Be concise but complete."
    )
    passage = normalized_question.get("passage", {}) or {}
    passage_text = passage.get("content_text") if isinstance(passage, dict) else ""
    stem_text = normalized_question.get("stem_text") or question_payload.get("prompt") or ""
    section = normalized_question.get("section") or question_payload.get("section") or ""
    user_lines = [
        f"Section: {section}",
        f"Passage: {passage_text or '(no passage)'}",
        f"Question: {stem_text}",
        f"Choices: {json.dumps(choices, ensure_ascii=False)}",
    ]
    user_prompt = "\n".join(user_lines)
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if page_image_b64 and (
        normalized_question.get("has_figure") or normalized_question.get("choice_figure_keys")
    ):
        user_content.append({"type": "input_image", "image_url": page_image_b64})
    payload = {
        "model": model_name,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    try:
        raw_text = _call_responses_api(
            payload,
            purpose="question solving",
            job_id=job_id,
        )
        data = json.loads(raw_text)
        answer_value = data.get("answer_value")
        if isinstance(answer_value, str):
            answer_value = answer_value.strip().upper()
        if answer_value not in choices:
            app.logger.warning(
                "AI solver returned invalid answer %s; available choices: %s",
                answer_value,
                list(choices.keys()),
            )
            return None
        solution = data.get("solution")
        return {"answer_value": answer_value, "solution": solution}
    except Exception as exc:  # pragma: no cover - defensive logging
        app.logger.warning("AI solver failed: %s", exc)
        return None


def _coerce_section(raw_value: Any) -> str:
    if not raw_value:
        return "RW"
    lowered = str(raw_value).strip().lower()
    if lowered in {"rw", "reading", "reading & writing", "reading/writing", "english", "verbal"}:
        return "RW"
    if lowered in {"math", "mathematics", "quant", "quantitative"}:
        return "Math"
    if "math" in lowered:
        return "Math"
    return "RW"


def _normalize_passage(raw_value: Any) -> dict | None:
    if isinstance(raw_value, dict):
        if raw_value.get("content_text"):
            return raw_value
        return None
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        return {"content_text": text, "metadata": {"source": "pdf_ingest"}}
    return None


AttemptHook = Callable[
    [Literal["start", "retry", "success", "heartbeat"], int, int, float, Optional[Exception]],
    None,
]


def _call_responses_api(
    payload: dict,
    *,
    purpose: str,
    attempt_hook: Optional[AttemptHook] = None,
    job_id: Optional[int] = None,
) -> str:
    app = current_app
    api_key = app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY / AI_API_KEY must be configured for PDF ingestion.")
    base_url = app.config.get("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    timeout = app.config.get("AI_TIMEOUT_SECONDS", 120)
    connect_timeout = app.config.get("AI_CONNECT_TIMEOUT_SEC", 15)
    read_timeout = app.config.get("AI_READ_TIMEOUT_SEC", timeout)
    max_attempts = max(1, int(app.config.get("AI_API_MAX_RETRIES", 3)))
    backoff = float(app.config.get("AI_API_RETRY_BACKOFF", 2.0))
    model_name = payload.get("model")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    attempt = 0
    watchdog_timeout = connect_timeout + read_timeout + 5
    heartbeat_interval = max(5.0, min(15.0, read_timeout / 4))
    while True:
        attempt += 1
        if attempt_hook:
            attempt_hook("start", attempt, max_attempts, 0.0, None)
        start_time = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    requests.post,
                    f"{base_url}/responses",
                    headers=headers,
                    json=payload,
                    timeout=(connect_timeout, read_timeout),
                )
                elapsed = 0.0
                last_timeout_exc: FutureTimeout | None = None
                response = None
                while True:
                    remaining = max(0.5, watchdog_timeout - elapsed)
                    if remaining <= 0:
                        break
                    slice_timeout = min(heartbeat_interval, remaining)
                    try:
                        response = future.result(timeout=slice_timeout)
                        break
                    except FutureTimeout as timeout_exc:
                        last_timeout_exc = timeout_exc
                        elapsed += slice_timeout
                        if elapsed >= watchdog_timeout:
                            break
                        if attempt_hook:
                            attempt_hook("heartbeat", attempt, max_attempts, elapsed, None)
                if response is None:
                    future.cancel()
                    exc = requests.Timeout(
                        f"Client watchdog timed out after {watchdog_timeout}s"
                    )
                    log_event(
                        "openai_timeout",
                        {
                            "job_id": job_id,
                            "purpose": purpose,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "duration_ms": int((time.perf_counter() - start_time) * 1000),
                            "model": model_name,
                            "error": str(exc),
                        },
                    )
                    if attempt_hook:
                        attempt_hook("heartbeat", attempt, max_attempts, elapsed, exc)
                    raise exc from last_timeout_exc
            response.raise_for_status()
            data = response.json()
            log_event(
                "openai_success",
                {
                    "job_id": job_id,
                    "purpose": purpose,
                    "status_code": response.status_code,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "duration_ms": int((time.perf_counter() - start_time) * 1000),
                    "model": model_name,
                },
            )
            if attempt_hook:
                attempt_hook("success", attempt, max_attempts, 0.0, None)
            break
        except requests.RequestException as exc:
            if attempt_hook:
                attempt_hook("retry", attempt, max_attempts, backoff * attempt, exc)
            if attempt >= max_attempts:
                log_event(
                    "openai_failure",
                    {
                        "job_id": job_id,
                        "purpose": purpose,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "duration_ms": int((time.perf_counter() - start_time) * 1000),
                        "model": model_name,
                        "error": str(exc),
                    },
                )
                raise
            sleep_for = backoff * attempt
            app.logger.warning(
                "PDF ingest: %s attempt %s/%s failed (%s). Retrying in %.1fs",
                purpose,
                attempt,
                max_attempts,
                exc,
                sleep_for,
            )
            time.sleep(sleep_for)
    texts: List[str] = []
    for chunk in data.get("output", []):
        for content in chunk.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                texts.append(content.get("text", ""))
    if not texts and data.get("output_text"):
        texts.extend(data["output_text"])
    return "".join(texts).strip()



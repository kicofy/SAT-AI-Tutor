"""Vision-aware PDF ingestion powered by multimodal AI."""

from __future__ import annotations

import base64
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import pdfplumber
import requests
from flask import current_app

from ..schemas.question_schema import QuestionCreateSchema
from .openai_log import log_event
from .skill_taxonomy import canonicalize_tags, iter_skill_tags
from .difficulty_service import difficulty_prompt_block

question_schema = QuestionCreateSchema()
SKILL_TAG_PROMPT = ", ".join(iter_skill_tags())
ProgressCallback = Callable[[int, int, int, Optional[str]], None]


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
) -> List[dict]:
    """Parse a PDF file and return normalized question payloads."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)

    pages = _extract_pages(path)
    normalized: List[dict] = []
    total_pages = len(pages)
    if progress_cb:
        progress_cb(0, total_pages, 0, "Starting PDF ingestion")

    max_wait = current_app.config.get("AI_READ_TIMEOUT_SEC", 60)

    def _make_attempt_hook(
        stage: str,
        page_idx: int,
        total_pages: int,
        count_getter: Callable[[], int],
        job_id: int | None,
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
            if progress_cb:
                progress_cb(page_idx, total_pages, normalized_count, message)
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

    for idx, page in enumerate(pages, start=1):
        if progress_cb:
            progress_cb(idx - 1, total_pages, len(normalized), f"Extracting page {idx}/{total_pages}")
        try:
            questions = _request_page_questions(
                page,
                page_index=idx,
                attempt_hook=_make_attempt_hook(
                    f"Extracting page {idx}/{total_pages}",
                    idx,
                    total_pages,
                    lambda: len(normalized),
                    job_id,
                ),
                job_id=job_id,
            )
        except Exception as exc:  # pragma: no cover - defensive
            current_app.logger.warning(
                "PDF ingest: failed to parse page %s, skipping. %s", idx, exc
            )
            if progress_cb:
                progress_cb(
                    idx,
                    total_pages,
                    len(normalized),
                    f"Skipped page {idx}/{total_pages}: {exc}",
                )
            continue
        if not questions:
            if progress_cb:
                progress_cb(idx, total_pages, len(normalized), f"Page {idx}/{total_pages}: no questions found")
            continue
        for raw_question in questions:
            try:
                payload = _normalize_question(
                    raw_question,
                    page_image_b64=page.get("image_b64"),
                    attempt_hook=_make_attempt_hook(
                        f"Normalizing question #{len(normalized) + 1} (page {idx}/{total_pages})",
                        idx,
                        total_pages,
                        lambda: len(normalized),
                        job_id,
                    ),
                    job_id=job_id,
                )
                normalized.append(payload)
                if question_cb:
                    question_cb(payload)
                if progress_cb:
                    progress_cb(
                        idx,
                        total_pages,
                        len(normalized),
                        f"Normalized question #{len(normalized)} (page {idx}/{total_pages})",
                    )
            except Exception as exc:  # pragma: no cover - guarded by unit tests
                current_app.logger.warning(
                    "PDF ingest: failed to normalize question on page %s: %s", idx, exc
                )
        if progress_cb:
            progress_cb(idx, total_pages, len(normalized), f"Finished page {idx}/{total_pages}")
    return normalized


def _extract_pages(path: Path) -> List[Dict[str, Any]]:
    """Render each page to base64 PNG plus extract plain text."""
    app = current_app
    resolution = app.config.get("PDF_INGEST_RESOLUTION", 220)
    max_pages = app.config.get("PDF_INGEST_MAX_PAGES", 200)
    pages: List[Dict[str, Any]] = []
    with pdfplumber.open(path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            if idx > max_pages:
                break
            text = page.extract_text() or ""
            image_b64 = _page_to_base64(page, resolution)
            pages.append(
                {
                    "page_number": idx,
                    "text": text.strip(),
                    "image_b64": image_b64,
                }
            )
    return pages


def _page_to_base64(page, resolution: int) -> str:
    page_image = page.to_image(resolution=resolution).original.convert("RGB")
    buffer = io.BytesIO()
    page_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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
        "- stem_text: ONLY the interrogative portion (e.g., \"Which choice ...?\"). Never prepend the passage or restate figure/table data verbatim.\n"
        "- choices: object whose keys are capital letters (A,B,C,...) and values are choice texts.\n"
        "- correct_answer: object like {\"value\": \"A\"}. If unknown, set value to null.\n"
        "- has_figure: boolean carried over from the extracted payload; keep true for any chart/table/image question so the UI can render the figure separately.\n"
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
    raw_text = _call_responses_api(
        payload,
        purpose="question normalization",
        attempt_hook=attempt_hook,
        job_id=job_id,
    )
    data = json.loads(raw_text)
    difficulty_assessment = data.pop("difficulty_assessment", None)

    data["section"] = _coerce_section(data.get("section"))
    data["has_figure"] = bool(question_payload.get("has_figure"))
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
    return normalized


def _sanitize_skill_tags(raw_tags: Any) -> List[str]:
    if isinstance(raw_tags, list):
        return canonicalize_tags(raw_tags, limit=2)
    return []


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
    if page_image_b64 and question_payload.get("has_figure"):
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
    [Literal["start", "retry", "success", "heartbeat"], int, int, float, Exception | None],
    None,
]


def _call_responses_api(
    payload: dict,
    *,
    purpose: str,
    attempt_hook: AttemptHook | None = None,
    job_id: int | None = None,
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



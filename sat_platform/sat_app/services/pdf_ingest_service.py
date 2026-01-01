
"""Two-stage PDF ingest (sequential): page extraction -> per-question enrichment (normalize/solve/explain)."""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Literal

import pdfplumber
import requests
from flask import current_app

from ..schemas.question_schema import QuestionCreateSchema
from ..models import Question
from .openai_log import log_event
from .skill_taxonomy import canonicalize_tags, iter_skill_tags
from .validation_service import validate_question, record_issues
from . import ai_explainer
from . import question_explanation_service

ProgressCallback = Callable[[int, int, int, Optional[str]], None]
AttemptHook = Callable[
    [Literal["start", "retry", "success", "heartbeat"], int, int, float, Optional[Exception]],
    None,
]

question_schema = QuestionCreateSchema()
SKILL_TAG_PROMPT = ", ".join(iter_skill_tags())

MATH_DOMAIN_MAP = (
    "SAT Math domains: (1) Algebra: linear eq/func, Ax+By=C, systems, inequalities. "
    "(2) Advanced Math: nonlinear functions/eqs, nonlinear systems, equivalent expressions. "
    "(3) Problem-Solving & Data Analysis: ratio/unit, percent, single/dual-variable data, probability, sampling/MOE, study design/causality. "
    "(4) Geometry & Trig: area/volume, lines/angles/triangles, right-triangle & trig, circles."
)
MATH_ROUTE_RULES = (
    "Route selection before solving: "
    "A) Graph/Desmos when intersection/roots/inequality shading/vertex/solution sets/regression appear, or algebra looks long. "
    "B) Plug-in options/special values (start with B/C; try 0,1,-1,2,10,100) when options are numeric/expressions or ask which holds. "
    "C) Formal algebra when the ask is exact value/parameter range/identity/simplified form or mentions exact/in terms of π."
)
MATH_MC_RULES = (
    "MC safety: estimate magnitude/sign to drop absurd options; usually 1–2 obvious eliminations. "
    "If stuck, plug in options or special values to verify quickly."
)
MATH_SPR_RULES = (
    "SPR (grid-in) rules: no lettered options => treat as fill. Grid allows ≤5 chars for positives (≤6 with leading minus; minus not counted). "
    "Provide every scoring-equivalent form: exact fractions, simplified radicals, π forms, and short decimals (e.g., 2/3, 0.666, .6666, .6667). "
    "If fraction too long, offer concise decimal within 4 decimals."
)
MATH_SOP = (
    "Teaching SOP (S1-S6): (1) Restate givens/goal. (2) Classify type/domain. "
    "(3) Choose strategy (graph vs plug-in vs algebra) and state why. "
    "(4) Build structure/equations before number-crunching. "
    "(5) Quick self-check: substitute back / sign & magnitude / domain constraints. "
    "(6) Takeaway rule for similar problems."
)

def _build_normalize_system_prompt(section_hint: str | None) -> str:
    is_math = str(section_hint or "").lower().startswith("math")
    if is_math:
        return (
            "You are an SAT Math normalizer. Convert extracted snippets into the platform JSON schema. "
            "Return exactly one JSON object with:\n"
            "- section: \"Math\"; sub_section optional/null.\n"
            "- passage: ONLY supporting prose; never copy figure/table text. Null if none.\n"
            "- stem_text: ONLY the interrogative part. Preserve LaTeX/advanced notation ($...$, \\(...\\), $$...$$, "
            "\\frac, \\sqrt, exponents, subscripts, inequalities, vectors, absolute value | |, summations, limits). Do not simplify.\n"
            "- choices: object with capital-letter keys. If the page shows no lettered options, set {} (treat as SPR/fill).\n"
            "- question_type: \"choice\" when valid lettered options exist, otherwise \"fill\" (SPR).\n"
            "- correct_answer: {\"value\": \"A\"} for MCQ or {\"value\": \"2/3\"} for fill.\n"
            "- answer_schema (fill only): {\"type\": \"numeric\"|\"text\", \"acceptable\": [...], \"tolerance\": number|null, "
            "\"allow_fraction\": true, \"allow_pi\": true, \"strip_spaces\": true}. List EVERY scoring-equivalent form within grid rules "
            "(≤5 chars; decimal point counts; leading minus does not). Include fraction + short decimals (e.g., 2/3, 0.666, .6666, .6667) and π/radical forms if applicable.\n"
            "- has_figure: true if passage/stem relies on a figure/table/image (not options). choice_figure_keys: letters whose option has its own figure; else [].\n"
            "- difficulty_level: 1-5 with difficulty_assessment {\"level\":3,\"expected_time_sec\":75,\"rationale\":\"...\"}.\n"
            f"- skill_tags: up to TWO from: {SKILL_TAG_PROMPT}; [] if unsure (prefer Math domains). {MATH_DOMAIN_MAP}\n"
            "- metadata: include source_question_number if available; no legacy fields.\n"
            f"{MATH_ROUTE_RULES} {MATH_MC_RULES} {MATH_SPR_RULES}\n"
            "Rules: Do NOT hallucinate. Do NOT copy figure data. Return JSON only."
        )
    return (
        "You are an SAT Reading & Writing normalizer. Convert extracted snippets into the canonical JSON schema. "
        "Return exactly one JSON object with:\n"
        "- section: \"RW\"; sub_section optional/null.\n"
        "- passage: ONLY supporting prose; do NOT copy tables/figures or the question sentence. Null if none.\n"
        "- stem_text: ONLY the interrogative part (e.g., \"Which choice ...?\").\n"
        "- choices: object with capital-letter keys. If no valid lettered options exist, set {} and question_type must be \"fill\".\n"
        "- question_type: \"choice\" for MCQ else \"fill\".\n"
        "- correct_answer: {\"value\": \"A\"} for MCQ or {\"value\": \"text\"} for fill.\n"
        "- answer_schema (fill only): {\"type\": \"text\"|\"numeric\", \"acceptable\": [...], \"tolerance\": number|null, "
        "\"allow_fraction\": true, \"allow_pi\": true, \"strip_spaces\": true}. Include all scoring-equivalent forms if known.\n"
        "- has_figure: true if passage/stem references a figure/table/image (not options). choice_figure_keys: letters whose option contains its own figure/table; else [].\n"
        "- difficulty_level 1-5 with difficulty_assessment; keep concise rationale.\n"
        f"- skill_tags: up to TWO from: {SKILL_TAG_PROMPT}; [] if unsure.\n"
        "- metadata: include source_question_number if available; no legacy fields.\n"
        "Rules: Do NOT hallucinate. Do NOT copy figure contents. Return JSON only."
    )


def _build_solver_system_prompt(section_hint: str | None) -> str:
    is_math = str(section_hint or "").lower().startswith("math")
    if is_math:
        return (
            "You are an SAT Math solving assistant. Determine the single best answer choice.\n"
            f"{MATH_ROUTE_RULES} {MATH_MC_RULES}\n"
            "Return JSON: {\"answer_value\": \"A\", \"solution\": \"step-by-step reasoning\"}. "
            "Keep exact symbolic forms when needed; answer_value must be one of the provided choice letters."
        )
    return (
        "You are an SAT Reading & Writing solving assistant. Choose the best answer based on evidence, logic, and clarity. "
        "Highlight why the selected option fits and others fail (unsupported, scope shift, grammar/clarity issues). "
        "Return JSON: {\"answer_value\": \"A\", \"solution\": \"brief reasoning\"}. answer_value must be one of the provided choice letters."
    )

# ---------------- Rate limiting (best-effort, client-side) ----------------
_rate_lock = threading.Lock()
_rate_window_minute: dict[str, deque] = defaultdict(deque)
_rate_window_second: dict[str, deque] = defaultdict(deque)


def _compute_coarse_uid(job_id: int | None, page_index: int, local_idx: int, payload: dict) -> str:
    """Deterministic coarse_uid so resumes can match the same question."""
    base = f"J{job_id or 'NA'}-P{page_index}-Q{local_idx}"
    sig_src = json.dumps(
        {
            "prompt": payload.get("prompt"),
            "stem": payload.get("stem_text"),
            "choices": payload.get("choices"),
            "section": payload.get("section"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    sig = hashlib.md5(f"{base}-{sig_src}".encode("utf-8")).hexdigest()[:12]
    return f"{base}-{sig}"


def _enforce_rate_limit(model: str) -> None:
    app = current_app
    max_rpm = int(app.config.get("AI_RESPONSES_MAX_RPM", 40))
    max_rps = int(app.config.get("AI_RESPONSES_MAX_RPS", 3))
    now = time.perf_counter()
    with _rate_lock:
        w_min = _rate_window_minute[model]
        w_sec = _rate_window_second[model]
        while w_min and now - w_min[0] > 60:
            w_min.popleft()
        while w_sec and now - w_sec[0] > 1:
            w_sec.popleft()
        sleep_for = 0.0
        if len(w_min) >= max_rpm:
            sleep_for = max(sleep_for, 60 - (now - w_min[0]) + 0.01)
        if len(w_sec) >= max_rps:
            sleep_for = max(sleep_for, 1 - (now - w_sec[0]) + 0.01)
    if sleep_for > 0:
        time.sleep(sleep_for)
    with _rate_lock:
        now2 = time.perf_counter()
        _rate_window_minute[model].append(now2)
        _rate_window_second[model].append(now2)


# ---------------- Public entry ----------------
def ingest_pdf_document(
    source_path: str | Path,
    progress_cb: Optional[ProgressCallback] = None,
    question_cb: Optional[Callable[[dict], None]] = None,
    job_id: int | None = None,
    cancel_event: Optional[threading.Event] = None,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    base_pages_completed: int = 0,
    base_questions: int = 0,
    coarse_items: Optional[List[dict]] = None,
    skip_normalized_count: int = 0,
    coarse_persist: Optional[Callable[[List[dict]], None]] = None,
    total_pages_hint: int | None = None,
) -> List[dict]:
    """
    Sequential pipeline:
      1) For each page (start_page..end_page): extract coarse questions via vision/text prompt.
      2) For each coarse question (in order): normalize -> solve (if needed) -> explain (if eligible).
    Guarantees: only one OpenAI call in flight at any time.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)
    if cancel_event and cancel_event.is_set():
        return []

    cached_items: List[dict] = list(coarse_items or [])
    max_cached_page = 0
    for it in cached_items:
        try:
            pval = it.get("page") or it.get("page_index")
            if pval is not None:
                max_cached_page = max(max_cached_page, int(pval))
        except Exception:
            continue

    pages = _extract_pages_seq(path, start_page=start_page, end_page=end_page, progress_cb=progress_cb)
    total_pages_span = max(
        base_pages_completed + len(pages),
        max_cached_page,
        base_pages_completed,
        total_pages_hint or 0,
    )
    if progress_cb:
        progress_cb(base_pages_completed, total_pages_span, base_questions, "Starting PDF ingestion")
    for p in pages:
        idx = p["page_index"]
        coarse = _extract_coarse_questions(p, job_id=job_id)
        for local_idx, it in enumerate(coarse, start=1):
            it["page_index"] = idx
            it["page"] = idx  # persist page for resume bookkeeping
            it["page_image_b64"] = p.get("page_image_b64")
            if not it.get("coarse_uid"):
                it["coarse_uid"] = _compute_coarse_uid(job_id, idx, local_idx, it)
            it["status"] = (it.get("status") or "pending").lower()
            cached_items.append(it)
        if coarse_persist:
            coarse_persist(cached_items)
        if progress_cb:
            progress_cb(
                idx,
                total_pages_span,
                base_questions,
                f"Coarse total: {len(cached_items)} after page {idx}",
            )

    # Normalize/complete items may already exist; ensure every item has coarse_uid/status.
    normalized_items: List[dict] = []
    for idx, it in enumerate(cached_items, start=1):
        if not it.get("coarse_uid"):
            it["coarse_uid"] = _compute_coarse_uid(job_id, int(it.get("page") or it.get("page_index") or 0), idx, it)
        it["status"] = (it.get("status") or "pending").lower()
        normalized_items.append(it)
    cached_items = normalized_items

    # Prefer status-based skipping: completed/explained items are skipped. Fall back to legacy skip count.
    remaining_items = [it for it in cached_items if it.get("status") not in ("explained", "completed")]
    if remaining_items:
        cached_items = remaining_items
    elif skip_normalized_count > 0 and cached_items:
        # legacy fallback if no status present
        if skip_normalized_count >= len(cached_items):
            cached_items = []
        else:
            cached_items = cached_items[skip_normalized_count:]

    enriched: List[dict] = []
    total = len(cached_items)
    start_idx = 0  # after trimming, always start from 0
    total_target = base_questions + total
    for i, item in enumerate(cached_items[start_idx:], start=start_idx + 1):
        if cancel_event and cancel_event.is_set():
            break
        eq = _enrich_item(item, job_id=job_id)
        if eq:
            item["status"] = "completed"
            enriched.append(eq)
            if question_cb:
                question_cb(eq)
            status_msg = f"Normalized {base_questions + len(enriched)}/{total_target}"
        else:
            status_msg = (
                f"Normalization failed for coarse_uid={item.get('coarse_uid')}; "
                f"saved {base_questions + len(enriched)}/{total_target} (attempt {i}/{total})"
            )
        if progress_cb:
            progress_cb(
                item.get("page_index", 0),
                total_pages_span,
                base_questions + len(enriched),
                status_msg,
            )
        # Persist updated statuses so resume can skip completed items.
        if coarse_persist:
            coarse_persist(cached_items)
    return enriched


# ---------------- Stage 1: Page extraction ----------------
def _extract_pages_seq(
    path: Path,
    *,
    start_page: int = 1,
    end_page: int | None = None,
    progress_cb: Optional[ProgressCallback] = None,
) -> List[dict]:
    app = current_app
    resolution = app.config.get("PDF_INGEST_RESOLUTION", 220)
    max_pages = app.config.get("PDF_INGEST_MAX_PAGES", 200)
    out: List[dict] = []
    with pdfplumber.open(path) as pdf:
        total = len(pdf.pages)
        if end_page is None:
            end_page = total
        for idx, page in enumerate(pdf.pages, start=1):
            if idx < start_page or idx > end_page or idx > max_pages:
                continue
            text = ""
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                app.logger.warning("extract_text failed on page %s: %s", idx, exc)
            img = _page_to_base64_safe(page, resolution)
            out.append({"page_index": idx, "text": text, "page_image_b64": img})
            if progress_cb:
                progress_cb(idx, end_page, len(out), f"Rendered page {idx}/{end_page}")
    return out


def _page_to_base64_safe(page, resolution: int) -> str | None:
    try:
        page_image = page.to_image(resolution=resolution).original.convert("RGB")
        buf = io.BytesIO()
        page_image.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception as exc:
        current_app.logger.warning("Page render failed: %s", exc)
        return None


def _extract_coarse_questions(page: dict, *, job_id: int | None) -> List[dict]:
    page_index = page.get("page_index")
    text = page.get("text") or ""
    image_b64 = page.get("page_image_b64")

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
                                "properties": {"label": {"type": "string"}, "text": {"type": "string"}},
                                "required": ["label", "text"],
                            },
                        },
                        "highlights": {
                            "type": "array",
                            "items": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
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
        "You are an SAT content extraction assistant. Emit STRICT JSON per the schema. Rules:\n"
        "- passage: supporting narrative only; do NOT copy figure/table text.\n"
        "- prompt: interrogative sentence(s).\n"
        "- choices: all options with labels. Preserve advanced math notation exactly (fractions, roots, powers, subscripts, "
        "inequalities). Prefer LaTeX inline math like $...$, \\(...\\), or $$...$$ with \\frac, \\sqrt, \\pi, exponents, "
        "absolute values |x|, vectors, summations, limits. Do NOT simplify, approximate, or strip symbols.\n"
        "- has_figure: true if chart/table/graph/image referenced; do NOT copy figure text.\n"
        f"- skill_tags: up to two from: {SKILL_TAG_PROMPT}; else [].\n"
        "- highlights: underlined snippets as {{\"text\": \"...\"}} from passage.\n"
        "If no questions: {\"questions\": []}. No commentary."
    )
    user_prompt = f"You are examining page {page_index} of an SAT prep PDF. Return JSON matching:\n{schema_hint}\nStrict JSON only."

    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if text:
        user_content.append({"type": "input_text", "text": text[:12000]})
    if image_b64:
        user_content.append({"type": "input_image", "image_url": image_b64})

    payload = {
        "model": current_app.config.get("AI_PDF_VISION_MODEL", "gpt-5.2"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    raw = _call_responses_api(
        payload,
        purpose="page_extraction",
        attempt_hook=None,
        job_id=job_id,
        ctx={"stage": "page_extraction", "page": page_index},
    )
    try:
        data = json.loads(raw)
    except Exception:
        current_app.logger.warning("Invalid JSON on page %s: %s", page_index, raw[:200])
        return []
    questions = data.get("questions") if isinstance(data, dict) else None
    out: List[dict] = []
    if isinstance(questions, list):
        for q in questions:
            if not isinstance(q, dict):
                continue
            item = dict(q)
            item["page"] = page_index
            item["source_question_number"] = _extract_question_number(q)
            item["has_figure"] = bool(q.get("has_figure"))
            item["highlights"] = _sanitize_highlights(q.get("highlights"))
            out.append(item)
    return out


# ---------------- Stage 2: per-item enrichment ----------------
def _enrich_item(item: dict, *, job_id: int | None) -> dict | None:
    ctx = {
        "job_id": job_id,
        "page": item.get("page") or item.get("page_index"),
        "qnum": _extract_question_number(item),
        "has_figure_raw": bool(item.get("has_figure")),
        "choice_figs_raw": bool(item.get("choice_figure_keys")),
    }
    coarse_uid = item.get("coarse_uid")
    item["status"] = (item.get("status") or "pending").lower()
    current_app.logger.info("Enrich start", extra=ctx)

    item["status"] = "normalizing"
    normalized = _normalize_question_item(item, job_id=job_id)
    if not normalized:
        current_app.logger.warning("Normalize returned None", extra=ctx)
        return None
    normalized["coarse_uid"] = coarse_uid
    item["status"] = "normalized"
    current_app.logger.info(
        "Normalize done",
        extra={
            **ctx,
            "question_type": normalized.get("question_type"),
            "has_figure": bool(normalized.get("has_figure")),
            "choice_figs": bool(normalized.get("choice_figure_keys")),
        },
    )

    # Always solve via API to get an explicit answer (ignore solution text for storage)
    current_app.logger.info("Solve start (always)", extra=ctx)
    solved = _solve_choice_answer(normalized, item, job_id=job_id)
    if solved and solved.get("answer_value"):
        normalized.setdefault("correct_answer", {})["value"] = solved["answer_value"]
        # Deliberately drop solver's solution text; only keep the final answer
        current_app.logger.info("Solve done", extra={**ctx, "answer": solved.get("answer_value")})
        item["status"] = "solved"
    else:
        current_app.logger.warning("Solve failed or empty", extra=ctx)

    # Explain: generate during ingest (not deferred to publish). Only honor a hard disable flag.
    has_fig = bool(normalized.get("has_figure"))
    choice_figs = normalized.get("choice_figure_keys") or []
    explain_enabled = bool(current_app.config.get("AI_EXPLAIN_ENABLE", True))
    if explain_enabled:
        # Keep explain timeout aligned with AI read timeout so we don't kill a slow-but-valid Responses call prematurely.
        ai_read_timeout = float(
            current_app.config.get(
                "AI_READ_TIMEOUT_SEC",
                current_app.config.get("AI_TIMEOUT_SECONDS", 120),
            )
        )
        explain_timeout_per_lang = float(current_app.config.get("AI_EXPLAIN_TIMEOUT_SEC", ai_read_timeout))
        # Allow time per language/version instead of a single shared budget.
        langs_cfg = current_app.config.get("AI_EXPLAIN_LANGUAGES")
        if isinstance(langs_cfg, (list, tuple)) and langs_cfg:
            lang_count = len(langs_cfg)
        else:
            lang_count = len(getattr(question_explanation_service, "DEFAULT_LANGUAGES", ["en", "zh"]))
        explain_timeout = explain_timeout_per_lang * max(1, lang_count)
        # Small overhead buffer so coordination code has time to join/log.
        explain_timeout += min(10.0, explain_timeout_per_lang * 0.25)
        app_obj = current_app._get_current_object()

        def _gen_expl(payload: dict):
            with app_obj.app_context():
                return question_explanation_service.generate_explanations_for_payload(payload)

        try:
            explain_started = time.perf_counter()
            current_app.logger.info(
                "Explain start",
                extra={**ctx, "has_figure": has_fig, "choice_figs": bool(choice_figs), "timeout": explain_timeout},
            )

            result_box: dict[str, Any] = {}
            exc_box: dict[str, Exception] = {}

            def _worker():
                try:
                    # Pass page image so explanations can use multimodal input
                    meta_for_expl = dict(normalized)
                    if item.get("page_image_b64"):
                        meta_for_expl.setdefault("metadata", {})
                        if not isinstance(meta_for_expl["metadata"], dict):
                            meta_for_expl["metadata"] = {}
                        meta_for_expl["metadata"]["page_image_b64"] = item.get("page_image_b64")
                    result_box["expl"] = _gen_expl(meta_for_expl)
                except Exception as exc:  # pragma: no cover - defensive
                    exc_box["exc"] = exc

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            elapsed = 0.0
            slice_interval = 1.0
            while worker.is_alive() and elapsed < explain_timeout:
                wait_for = min(slice_interval, explain_timeout - elapsed)
                worker.join(timeout=wait_for)
                elapsed += wait_for

            if worker.is_alive():
                current_app.logger.warning(
                    "Explanation generation timed out after %.0fs",
                    explain_timeout,
                    extra={**ctx, "elapsed_ms": int((time.perf_counter() - explain_started) * 1000)},
                )
            elif "exc" in exc_box:
                current_app.logger.warning(
                    "Explanation skipped due to error",
                    extra={
                        **ctx,
                        "error": str(exc_box["exc"]),
                        "elapsed_ms": int((time.perf_counter() - explain_started) * 1000),
                    },
                )
            else:
                expl = result_box.get("expl")
                if expl:
                    meta = normalized.get("metadata") or {}
                    if not isinstance(meta, dict):
                        meta = {}
                    meta["ai_explanations"] = expl
                    normalized["metadata"] = meta
                    item["status"] = "explained"
                    current_app.logger.info(
                        "Explain done",
                        extra={**ctx, "elapsed_ms": int((time.perf_counter() - explain_started) * 1000)},
                    )
                else:
                    current_app.logger.warning(
                        "Explanation generation returned empty result",
                        extra={**ctx, "elapsed_ms": int((time.perf_counter() - explain_started) * 1000)},
                    )
        except ai_explainer.AiExplainerError:
            current_app.logger.warning(
                "Explanation skipped due to AI error",
                extra={**ctx, "elapsed_ms": int((time.perf_counter() - explain_started) * 1000)},
            )
        except Exception:
            current_app.logger.exception("Explanation generation failed")
    else:
        current_app.logger.info(
            "Explanation skipped due to AI_EXPLAIN_ENABLE=False (has_figure=%s, choice_figs=%s)",
            has_fig,
            bool(choice_figs),
        )
        item["status"] = "explained"

    # Validate
    try:
        normalized.pop("_ai_explanations", None)
        normalized.pop("difficulty_assessment", None)
        normalized_coarse_uid = normalized.pop("coarse_uid", None)
        temp_data = question_schema.load(normalized)
        # Use a copy for validation so we don't lose passage in returned payload
        temp_for_validation = dict(temp_data)
        # Avoid assigning plain dict into SA relationship
        temp_for_validation.pop("passage", None)
        # Map metadata to column if needed
        model_columns = {col.key for col in Question.__table__.columns}
        if "metadata" in temp_for_validation and "metadata_json" in model_columns:
            temp_for_validation["metadata_json"] = temp_for_validation.pop("metadata")
        # Keep only actual model columns (drop extras like choice_figure_keys)
        temp_for_validation = {k: v for k, v in temp_for_validation.items() if k in model_columns}
        temp_question = Question(**temp_for_validation)
        valid, issues = validate_question(temp_question)
        if not valid:
            current_app.logger.warning(
                "Validation failed for job %s page %s qnum %s issues=%s",
                job_id,
                item.get("page_index"),
                _extract_question_number(item),
                issues,
            )
            return None
        # Restore coarse_uid into payload for downstream persistence
        if normalized_coarse_uid and "coarse_uid" not in temp_data:
            temp_data["coarse_uid"] = normalized_coarse_uid
    except Exception as exc:
        current_app.logger.warning("Validation/load failed: %s", exc)
        return None

    # Ensure returned payload uses `metadata` key (not metadata_json) so drafts persist explanations
    payload = dict(temp_data)
    if "metadata_json" in payload and "metadata" not in payload:
        payload["metadata"] = payload.pop("metadata_json")
    if coarse_uid:
        payload["coarse_uid"] = coarse_uid
    return payload


def _normalize_question_item(item: dict, *, job_id: int | None) -> dict | None:
    section = item.get("section") or ""
    system_prompt = _build_normalize_system_prompt(section)
    passage = item.get("passage") or ""
    # Fallback to stem_text when prompt is absent to avoid empty normalization input
    prompt_text = item.get("prompt") or item.get("stem_text") or ""
    choices = item.get("choices") or item.get("options") or item.get("answer_choices") or {}
    has_figure = bool(item.get("has_figure"))
    skill_tags = item.get("skill_tags") or []
    section = item.get("section") or ""
    source_qnum = _extract_question_number(item)

    user_lines = [
        f"Section: {section}",
        f"Passage: {passage or '(none)'}",
        f"Prompt: {prompt_text}",
        f"Choices: {json.dumps(choices, ensure_ascii=False)}",
        f"Has figure: {has_figure}",
        f"Skill tags (raw): {skill_tags}",
        f"Source question number: {source_qnum}",
    ]
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": "\n".join(user_lines)}]
    if item.get("page_image_b64") and (has_figure or item.get("choice_figure_keys")):
        user_content.append({"type": "input_image", "image_url": item.get("page_image_b64")})

    payload = {
        "model": current_app.config.get("AI_PDF_NORMALIZE_MODEL", "gpt-5.2"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    raw = _call_responses_api(
        payload,
        purpose="question_normalization",
        attempt_hook=None,
        job_id=job_id,
        ctx={
            "stage": "normalize",
            "page": item.get("page") or item.get("page_index"),
            "qnum": source_qnum,
            "has_figure": has_figure,
        },
    )
    try:
        data = json.loads(raw)
    except Exception:
        current_app.logger.warning("Normalize JSON parse failed: %s", raw[:200])
        return None

    norm_choices = _normalize_choices(data.get("choices"))
    data["choices"] = norm_choices if norm_choices else None
    data["question_type"] = data.get("question_type") or ("choice" if norm_choices else "fill")
    data["section"] = _coerce_section(data.get("section"))
    if item.get("coarse_uid"):
        data["coarse_uid"] = item.get("coarse_uid")

    # Preserve page/index so each question points to the correct PDF page
    page_val = item.get("page") or item.get("page_index")
    if page_val is not None:
        data["page"] = str(page_val)
        try:
            data["source_page"] = int(page_val)
        except (TypeError, ValueError):
            pass

    # Move difficulty_assessment into metadata/estimated_time; drop from payload for schema
    difficulty_assessment = data.pop("difficulty_assessment", None)
    if difficulty_assessment:
        meta = data.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        meta["difficulty_assessment"] = difficulty_assessment
        expected_time = difficulty_assessment.get("expected_time_sec") if isinstance(difficulty_assessment, dict) else None
        if expected_time and not data.get("estimated_time_sec"):
            try:
                data["estimated_time_sec"] = int(expected_time)
            except (TypeError, ValueError):
                pass
        data["metadata"] = meta

    if data["question_type"] == "fill":
        answer_schema = data.get("answer_schema") or {}
        if not isinstance(answer_schema, dict):
            answer_schema = {}
        correct_val = (data.get("correct_answer") or {}).get("value")
        if correct_val and not answer_schema.get("acceptable"):
            answer_schema["acceptable"] = [str(correct_val).strip()]
        answer_schema.setdefault("type", "numeric")
        answer_schema.setdefault("allow_fraction", True)
        answer_schema.setdefault("allow_pi", True)
        answer_schema.setdefault("strip_spaces", True)
        data["answer_schema"] = answer_schema

    data["passage"] = _normalize_passage(data.get("passage"))
    data["skill_tags"] = _sanitize_skill_tags(data.get("skill_tags"))
    # Fallback: ensure at least one valid skill tag to pass validation
    if not data["skill_tags"]:
        data["skill_tags"] = ["M_Algebra"] if data["section"] == "Math" else ["RW_MainIdeasEvidence"]
    data["has_figure"] = bool(data.get("has_figure") or data.get("choice_figure_keys"))

    # Normalize metadata container to a dict so later assignments (e.g., page_image_b64) are safe.
    meta = data.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    data["metadata"] = meta

    if source_qnum is not None:
        meta = data.get("metadata") or {}
        meta["source_question_number"] = source_qnum
        data["metadata"] = meta

    return data


def _solve_choice_answer(normalized: dict, raw_item: dict, *, job_id: int | None) -> dict | None:
    choices = normalized.get("choices") or {}
    if not choices:
        return None
    system_prompt = _build_solver_system_prompt(normalized.get("section") or raw_item.get("section"))
    passage = normalized.get("passage") or {}
    passage_text = passage.get("content_text") if isinstance(passage, dict) else ""
    stem_text = normalized.get("stem_text") or raw_item.get("prompt") or ""
    section = normalized.get("section") or raw_item.get("section") or ""
    user_lines = [
        f"Section: {section}",
        f"Passage: {passage_text or '(no passage)'}",
        f"Question: {stem_text}",
        f"Choices: {json.dumps(choices, ensure_ascii=False)}",
    ]
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": "\n".join(user_lines)}]
    if raw_item.get("page_image_b64") and (normalized.get("has_figure") or normalized.get("choice_figure_keys")):
        user_content.append({"type": "input_image", "image_url": raw_item.get("page_image_b64")})

    payload = {
        "model": current_app.config.get(
            "AI_PDF_SOLVER_MODEL",
            current_app.config.get("AI_PDF_NORMALIZE_MODEL", "gpt-5.2"),
        ),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    try:
        raw = _call_responses_api(
            payload,
            purpose="question_solving",
            attempt_hook=None,
            job_id=job_id,
            ctx={
                "stage": "solve",
                "page": raw_item.get("page") or raw_item.get("page_index"),
                "qnum": _extract_question_number(raw_item),
            },
        )
        data = json.loads(raw)
        ans = data.get("answer_value")
        if isinstance(ans, str):
            ans = ans.strip().upper()
        if ans not in choices:
            current_app.logger.warning("Solver answer not in choices: %s", ans)
            return None
        return {"answer_value": ans, "solution": data.get("solution")}
    except Exception as exc:
        current_app.logger.warning("Solver failed: %s", exc)
        return None


# ---------------- OpenAI call wrapper ----------------
def _call_responses_api(
    payload: dict,
    *,
    purpose: str,
    attempt_hook: Optional[AttemptHook] = None,
    job_id: Optional[int] = None,
    ctx: Optional[dict] = None,
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
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    attempt = 0
    watchdog_timeout = connect_timeout + read_timeout + 5
    heartbeat_interval = max(5.0, min(15.0, read_timeout / 4))

    base_ctx = {
        "job_id": job_id,
        "purpose": purpose,
        "model": model_name,
    }
    if ctx:
        base_ctx.update(ctx)

    while True:
        attempt += 1
        if attempt_hook:
            attempt_hook("start", attempt, max_attempts, 0.0, None)
        start_time = time.perf_counter()

        # Rate limit before sending
        if model_name:
            _enforce_rate_limit(model_name)

        try:
            future = requests.post(
                f"{base_url}/responses",
                headers=headers,
                json=payload,
                timeout=(connect_timeout, read_timeout),
            )
            response = future
            response.raise_for_status()
            data = response.json()
            log_event(
                "openai_success",
                {
                    **base_ctx,
                    "status_code": response.status_code,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "duration_ms": int((time.perf_counter() - start_time) * 1000),
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
                        **base_ctx,
                        "attempt": attempt,
                        "max_attempts": max_attempts,
                        "duration_ms": int((time.perf_counter() - start_time) * 1000),
                        "error": str(exc),
                    },
                )
                raise
            sleep_for = backoff * attempt
            try:
                retry_after = exc.response.headers.get("Retry-After") if exc.response else None
                if retry_after:
                    sleep_for = max(sleep_for, float(retry_after))
            except Exception:
                pass
            current_app.logger.warning(
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


# ---------------- Helpers ----------------
def _extract_question_number(payload: Dict[str, Any]) -> str | int | None:
    for key in ("question_number", "original_question_number", "source_question_number", "question_index"):
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _normalize_choices(raw_choices: Any) -> Dict[str, str]:
    if isinstance(raw_choices, dict):
        return {str(k).strip().upper(): v if isinstance(v, str) else str(v) for k, v in raw_choices.items() if str(k).strip()}
    if isinstance(raw_choices, list):
        out: Dict[str, str] = {}
        for idx, c in enumerate(raw_choices):
            if not isinstance(c, dict):
                continue
            label = (c.get("label") or "").strip().upper() or chr(ord("A") + idx)
            text = c.get("text") or c.get("value") or ""
            out[label] = text
        return out
    return {}


def _normalize_passage(raw_value: Any) -> dict | None:
    if isinstance(raw_value, dict):
        return raw_value if raw_value.get("content_text") else None
    if isinstance(raw_value, str):
        t = raw_value.strip()
        return {"content_text": t, "metadata": {"source": "pdf_ingest"}} if t else None
    return None


def _sanitize_skill_tags(raw_tags: Any) -> List[str]:
    if isinstance(raw_tags, list):
        return canonicalize_tags(raw_tags, limit=2)
    return []


def _sanitize_highlights(raw_highlights: Any) -> List[dict]:
    if not isinstance(raw_highlights, list):
        return []
    out: List[dict] = []
    for h in raw_highlights:
        if isinstance(h, dict) and h.get("text"):
            out.append({"text": str(h["text"])})
    return out


def _coerce_section(raw_value: Any) -> str:
    if not raw_value:
        return "RW"
    lowered = str(raw_value).strip().lower()
    if lowered in {"rw", "reading", "reading & writing", "reading/writing", "english", "verbal"}:
        return "RW"
    if "math" in lowered:
        return "Math"
    return "RW"


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
        "model": current_app.config.get("AI_PDF_VISION_MODEL", "gpt-5.2"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    raw_text = _call_responses_api(
        payload,
        purpose="page_extraction",
        attempt_hook=attempt_hook,
        job_id=job_id,
        ctx={"stage": "page_extraction", "page": page_index},
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
        Callable[[Literal["start", "retry"], int, int, float, Optional[Exception]], None]
    ] = None,
    job_id: int | None = None,
) -> dict:
    system_prompt = _build_normalize_system_prompt(question_payload.get("section"))
    schema_hint = ""
    user_prompt = json.dumps(question_payload, ensure_ascii=False, indent=2)
    payload = {
        "model": current_app.config.get("AI_PDF_NORMALIZE_MODEL", "gpt-5.2"),
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
    raw_text = _call_responses_api(
        payload,
        purpose="question_normalization",
        attempt_hook=attempt_hook,
        job_id=job_id,
        ctx={
            "stage": "normalize",
            "page": question_payload.get("page"),
            "qnum": _extract_question_number(question_payload),
        },
    )
    data = json.loads(raw_text)
    difficulty_assessment = data.pop("difficulty_assessment", None)

    # Keep only fields recognized by the schema; drop relationships/unknown keys
    allowed_fields = set(question_schema.fields.keys())
    data = {k: v for k, v in data.items() if k in allowed_fields}

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
    data_coarse_uid = data.pop("coarse_uid", None)
    normalized = question_schema.load(data)
    if data_coarse_uid is not None:
        normalized["coarse_uid"] = data_coarse_uid
    # Normalize metadata container early to avoid None-type item assignment later.
    metadata = normalized.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    normalized["metadata"] = metadata
    if difficulty_assessment:
        metadata = normalized.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        metadata["difficulty_assessment"] = difficulty_assessment
        normalized["metadata"] = metadata
        expected_time = difficulty_assessment.get("expected_time_sec")
        if expected_time and not normalized.get("estimated_time_sec"):
            normalized["estimated_time_sec"] = int(expected_time)
    decorations = _extract_decorations(question_payload)
    if decorations:
        metadata = normalized.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
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
    try:
        normalized.pop("_ai_explanations", None)
        normalized_coarse_uid = normalized.pop("coarse_uid", None)
        temp_data = question_schema.load(normalized)
        if normalized_coarse_uid is not None and "coarse_uid" not in temp_data:
            temp_data["coarse_uid"] = normalized_coarse_uid
        temp_data.pop("passage", None)
        model_columns = {col.key for col in Question.__table__.columns}
        if "metadata" in temp_data and "metadata_json" in model_columns:
            temp_data["metadata_json"] = temp_data.pop("metadata")
        temp_for_validation = {k: v for k, v in temp_data.items() if k in model_columns}
        temp_question = Question(**temp_for_validation)
        valid, issues = validate_question(temp_question)
        if not valid:
            record_issues(temp_question, issues)
            return None
    except Exception as exc:
        current_app.logger.warning("Validation/load failed: %s", exc)
        return None
    return temp_data


def _attach_precomputed_explanations(payload: dict) -> None:
    """
    Disabled pre-generation to avoid duplicate explanation calls.
    Explanation generation now only happens at publish time (per language),
    preventing the Math/RW prompt from being run twice per language.
    """
    return


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
        "AI_PDF_NORMALIZE_MODEL", "gpt-5.2"
    )
    system_prompt = _build_solver_system_prompt(normalized_question.get("section") or question_payload.get("section"))
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
            purpose="question_solving",
            job_id=job_id,
            ctx={
                "stage": "solve",
                "page": question_payload.get("page"),
                "qnum": _extract_question_number(question_payload),
            },
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


def _call_responses_api_legacy(
    payload: dict,
    *,
    purpose: str,
    attempt_hook: Optional[AttemptHook] = None,
    job_id: Optional[int] = None,
    ctx: Optional[dict] = None,
) -> str:
    return _call_responses_api(
        payload,
        purpose=purpose,
        attempt_hook=attempt_hook,
        job_id=job_id,
        ctx=ctx,
    )



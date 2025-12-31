"""AI explainer service to generate bilingual explanations."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from pathlib import Path
import base64
import time

import requests
from flask import current_app

from .ai_client import get_ai_client


ANIMATION_PROTOCOL = "tutor.anim.v1"

# Math domain and strategy prompts
MATH_DOMAIN_MAP = (
    "SAT Math domains: (1) Algebra: linear equations/functions, Ax+By=C, systems, inequalities. "
    "(2) Advanced Math: nonlinear functions/equations, nonlinear systems, equivalent expressions. "
    "(3) Problem-Solving & Data Analysis: ratio/unit, percent, single/dual-variable data, probability, sampling/MOE, study design/causality. "
    "(4) Geometry & Trig: area/volume, lines/angles/triangles, right-triangle & trig, circles."
)
MATH_ROUTE_RULES = (
    "Route selection: A) Graph/Desmos for intersections/roots/inequality shading/vertex/solution sets/regression or long algebra. "
    "B) Plug in options or special values (start B/C; try 0,1,-1,2,10,100) when options are numeric/expressions or ask which holds. "
    "C) Formal algebra when exact value/parameter range/identity/simplified form is required or \"exact/in terms of π\" is stated."
)
MATH_MC_RULES = (
    "MC safety: estimate magnitude/sign to drop absurd options; typically 1–2 obvious eliminations. "
    "If stuck, plug in options or special values to verify quickly."
)
MATH_SPR_RULES = (
    "SPR grid-in: no lettered options ⇒ treat as fill. Grid allows ≤5 chars for positives (≤6 with leading minus; minus not counted). "
    "Provide all scoring-equivalent forms: exact fractions, π forms, simplified radicals, and short decimals (e.g., 2/3, 0.666, .6666, .6667)."
)


def _resolve_language_tag(user_language: str | None) -> str:
    if not user_language:
        return "en"
    lang = user_language.lower()
    if "zh" in lang or "cn" in lang:
        return "zh"
    return "en"


def _encode_figure_image(path: Path) -> str | None:
    if not path.exists():
        return None
    mime = "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    try:
        data = path.read_bytes()
    except OSError:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _collect_question_figures(question) -> List[Dict[str, Any]]:
    """Collect figures either from ORM relationship (.figures) or pre-baked list/dicts."""
    figures: List[Dict[str, Any]] = []
    figure_query = getattr(question, "figures", None)
    if figure_query is None:
        return figures
    figure_items: List[Any] = []
    if isinstance(figure_query, list):
        figure_items = figure_query
    else:
        try:
            figure_items = figure_query.all()
        except Exception:  # pragma: no cover - defensive
            figure_items = []
    for item in figure_items:
        pre_resolved = getattr(item, "image_url", None) or (item.get("image_url") if isinstance(item, dict) else None)
        description = getattr(item, "description", None) or (item.get("description") if isinstance(item, dict) else None)
        figure_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
        if pre_resolved:
            figures.append({"id": figure_id, "description": description, "image_url": pre_resolved})
            continue
        image_path = getattr(item, "image_path", None)
        if not image_path:
            continue
        data_url = _encode_figure_image(Path(image_path))
        if not data_url:
            continue
        figures.append(
            {
                "id": figure_id,
                "description": description,
                "image_url": data_url,
            }
        )
    return figures


def _build_messages(question, user_answer, user_language: str, depth: str, figures: List[Dict[str, Any]]) -> dict:
    language_tag = _resolve_language_tag(user_language)
    language_name = "Chinese" if language_tag == "zh" else "English"
    schema_description = json.dumps(
        {
            "protocol_version": ANIMATION_PROTOCOL,
            "question_id": question.id,
            "answer_correct": True,
            "language": language_tag,
            "summary": "... short overview in target language ...",
            "steps": [
                {
                    "id": "step-1",
                    "type": "focus | annotate | strategy | definition | hint | elimination | evidence",
                    "title": "Short label for the step",
                    "narration": f"Teacher-style narration in {language_name}",
                    "duration_ms": 2600,
                    "delay_ms": 500,
                    "board_notes": ["bullet1", "bullet2"],
                    "animations": [
                        {
                            "target": "passage | stem | choices",
                            "text": "exact snippet that will be highlighted",
                            "action": "highlight | underline | circle | strike | note | color | font",
                            "cue": "Why this snippet matters",
                            "emphasis": "#FFB347",
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
    )
    math_prompt_block = (
        "- Math notation: preserve LaTeX ($...$, \\(...\\), $$...$$) with \\frac, \\sqrt, exponents, subscripts, inequalities, vectors, limits. "
        "Keep exact forms unless SAT key is decimal.\n"
        f"- Domains: {MATH_DOMAIN_MAP} State the domain/skill briefly when explaining.\n"
        f"- Route map: {MATH_ROUTE_RULES}\n"
        f"- MCQ tactics: {MATH_MC_RULES}\n"
        f"- SPR rules: {MATH_SPR_RULES}\n"
        "- Explanation SOP (S1-S6): restate goal/givens → classify type/domain → choose strategy (graph vs plug-in vs algebra) with reason → build structure then compute → quick self-check (substitute back / unit & domain / sign & magnitude) → takeaway for similar problems.\n"
        "- Animations: highlight equations, substitutions, graph features, numeric checks; when using figures, set target \"figure\" with figure_id. Include at least one check (substitute back, domain/unit, or reasonableness)."
    )
    rw_prompt_block = (
        "- Reading & Writing heuristics: use textual evidence, avoid extreme wording, correct choices restate the text, no gut guesses.\n"
        "- Reading four-step method: (1) identify keywords (names/time/logic cues) (2) understand paragraph function (3) revisit text for synonyms/logic (4) eliminate wrong answers (not stated / concept shift / over-generalization / subjective guess).\n"
        "- Writing checks: subject-verb agreement, parallel structure, logical clarity; mantra: keep it short, simple, active, precise.\n"
        "- Teaching template: what is tested? where are the keywords? where is the supporting text? why is the correct option right? why are others wrong?\n"
        "- For evidence/definition/writing items, point to the exact sentence and explain why it fits. Include at least two passage highlights for evidence-driven items.\n"
        "- For grammar/sentence items, highlight the relevant clause (subject, verb, modifier, tense marker) and show how the choice fixes or breaks it.\n"
        "- Prefer operating on the passage first (keywords, timeline, tone) before the choices so the clue source is explicit.\n"
        "- Close with: “Reading: evidence rules, synonym = correct, speculation = wrong; Writing: clarity > brevity > correctness > style.” translated into the target language."
    )
    system_prompt = (
        "You are an elite SAT tutor who provides animated explanations.\n"
        "Respond with **pure JSON** matching the schema shown below. Do not add markdown or commentary.\n"
        f"{schema_description}\n"
        "Guidelines:\n"
        "- Produce 5 to 7 steps (add more if the content is complex) so the reasoning feels granular.\n"
        "- duration_ms must be between 1500 and 4000; delay_ms between 200 and 800.\n"
        "- narration must sound like a calm teacher guiding a student.\n"
        "- Each step MUST include at least one animation referencing a short snippet from the passage, stem, or choices. Mix actions (highlight, underline, circle, strike, annotate, note, font/color) and allow multiple animations per step when helpful.\n"
        "- board_notes are concise reminders or mini formulas.\n"
        "- summary should be <= 80 words.\n"
        "- All narration, titles, and summary must be written only in the requested target language.\n"
        "- Ensure answer_correct reflects whether the submitted answer matches the official key.\n"
        "- When you populate an animation with `target: \"passage\"` or `target: \"stem\"`, copy exact contiguous characters from the provided text; no paraphrasing or invented wording.\n"
        "- For every animation that references answer choices: set target to \"choices\", always include `choice_id` (A, B, C, ...), and keep the `text` field identical to that choice’s actual wording. Provide one animation object per affected choice.\n"
        "- When highlighting text, quote enough surrounding words so the snippet is unique. Avoid vague markers such as “this sentence”.\n"
        "- If figures are provided, interpret them directly. When an animation focuses on a figure, set target to \"figure\", provide a short `text` describing the region, set `figure_id`, and explain how that visual supports or eliminates a choice."
    )
    is_math = str(getattr(question, "section", "")).lower().startswith("math")
    system_prompt += "\n" + (math_prompt_block if is_math else rw_prompt_block)
    if language_tag == "zh":
        system_prompt += (
            "- For Chinese preference: use Chinese as the main language but include essential English keywords or quoted phrases in parentheses so students connect back to the SAT passage. Keep the bilingual mix concise (Chinese sentence + key English term) rather than writing two separate explanations.\n"
        )
    figures_prompt = ""
    if figures:
        figures_prompt = f"\nFigures metadata: {json.dumps([{'id': f['id'], 'description': f.get('description')} for f in figures], ensure_ascii=False)}"
        figures_prompt += (
            "\nUse these images when reasoning about the question. Reference them in animations via "
            "`target: \"figure\"` and provide the matching `figure_id` so the UI knows which chart to highlight."
        )
    question_type = getattr(question, "question_type", "choice") or "choice"
    answer_schema = getattr(question, "answer_schema", None)
    passage_text = None
    if getattr(question, "passage", None) and getattr(question.passage, "content_text", None):
        passage_text = question.passage.content_text
    else:
        metadata = getattr(question, "metadata_json", None) or {}
        passage_text = metadata.get("passage_text") or metadata.get("passage_excerpt")
    if passage_text:
        passage_prompt = f"Passage text (copy exact wording for highlights):\n{passage_text}\n"
    else:
        passage_prompt = "Passage text: [No passage available for this item]\n"
    user_prompt = (
        f"Target language: {language_name} (language tag: {language_tag}).\n"
        f"Student answer leads to the following context:\n"
        f"{passage_prompt}"
        f"Question stem: {question.stem_text}\n"
        f"Choices: {json.dumps(question.choices, ensure_ascii=False)}\n"
        f"Correct answer: {json.dumps(question.correct_answer, ensure_ascii=False)}\n"
        f"User answer: {json.dumps(user_answer, ensure_ascii=False)}\n"
        f"Question type: {question_type}\n"
        f"Answer schema (if fill): {json.dumps(answer_schema, ensure_ascii=False)}\n"
        f"Section: {question.section}\n"
        f"Skill tags: {question.skill_tags}\n"
        f"Depth request: {depth}\n"
        f"Has figure: {question.has_figure}\n"
        f"Figure instructions: {figures_prompt}\n"
        "Explain why the correct option works AND why each incorrect option fails (tie back to the four error types: not mentioned, concept shift, over-generalization, subjective guess).\n"
        "If the skill tags indicate Writing, emphasize grammar/logic checkpoints; if Reading, spotlight keyword tracking and evidence sentences.\n"
        "Return ONLY the JSON object."
    )
    # Responses API expects "input_text" / "input_image" content blocks
    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    seen_images = set()
    for figure in figures:
        url = figure.get("image_url")
        # The Responses API expects image_url to be a string (URL or data URL).
        # Some upstream code may still pass {"url": "...", "detail": "..."} — normalize that here.
        if isinstance(url, dict):
            url = url.get("url") or url.get("data") or url.get("image_url")
        if not isinstance(url, str):
            continue
        url = url.strip()
        if not url or url in seen_images:
            continue
        seen_images.add(url)
        user_content.append(
            {
                "type": "input_image",
                "image_url": url,
            }
        )
    return {
        "system_prompt": system_prompt,
        "user_content": user_content,
    }


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = {"protocol_version", "question_id", "answer_correct", "language", "summary", "steps"}
    if not required_fields.issubset(payload):
        missing = required_fields - set(payload)
        raise ValueError(f"Missing keys in AI response: {missing}")
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    return payload


class AiExplainerError(Exception):
    """Raised when the AI explainer cannot return a valid payload."""


def generate_explanation(
    question,
    user_answer,
    user_language: str = "bilingual",
    depth: str = "standard",
    *,
    figures: List[Dict[str, Any]] | None = None,
):
    app = current_app
    if not app.config.get("AI_EXPLAINER_ENABLE", False):
        return {
            "protocol_version": ANIMATION_PROTOCOL,
            "question_id": question.id,
            "answer_correct": user_answer == question.correct_answer,
            "language": _resolve_language_tag(user_language),
            "summary": "AI explainer disabled. Please enable AI_EXPLAINER_ENABLE.",
            "steps": [],
        }

    # Gather figures: explicit list wins, then ORM figures, then page image in metadata.
    collected_figures: List[Dict[str, Any]] = []
    if figures:
        collected_figures.extend(figures)
    collected_figures.extend(_collect_question_figures(question))
    metadata = getattr(question, "metadata_json", {}) or {}
    page_img = metadata.get("page_image_b64")
    if isinstance(page_img, str) and page_img.strip():
        collected_figures.insert(
            0,
            {"id": "page", "description": "page_image", "image_url": page_img.strip()},
        )

    # Deduplicate and limit images to keep latency down and avoid over-sending.
    deduped: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for fig in collected_figures:
        url = fig.get("image_url")
        if isinstance(url, dict):
            url = url.get("url") or url.get("data") or url.get("image_url")
        if not isinstance(url, str):
            continue
        url = url.strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        fig = dict(fig)
        fig["image_url"] = url
        deduped.append(fig)

    # Always prefer the page image first; cap the total images.
    max_images = int(current_app.config.get("AI_EXPLAINER_MAX_IMAGES", 2))
    if max_images <= 0:
        max_images = len(deduped) or 1
    page_first: List[Dict[str, Any]] = []
    page_fig = next((f for f in deduped if f.get("id") == "page"), None)
    if page_fig:
        page_first.append(page_fig)
    for fig in deduped:
        if fig is page_fig:
            continue
        if len(page_first) >= max_images:
            break
        page_first.append(fig)
    collected_figures = page_first

    prompt = _build_messages(question, user_answer, user_language, depth, collected_figures)

    payload = {
        "model": app.config.get("AI_EXPLAINER_MODEL", get_ai_client().default_model),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": prompt["system_prompt"]}]},
            {"role": "user", "content": prompt["user_content"]},
        ],
        # Structured outputs per Responses API: use text.format, not response_format.
        "text": {"format": "json_object"},
        "temperature": 0.2,
    }

    api_key = app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY / AI_API_KEY is not configured")
    base_url = app.config.get("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    connect_timeout = app.config.get("AI_CONNECT_TIMEOUT_SEC", 15)
    read_timeout = app.config.get("AI_READ_TIMEOUT_SEC", 120)
    max_retries = max(1, int(app.config.get("AI_API_MAX_RETRIES", 3)))
    backoff = float(app.config.get("AI_API_RETRY_BACKOFF", 2.0))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    attempt = 0
    while True:
        attempt += 1
        try:
            response = requests.post(
                f"{base_url}/responses",
                headers=headers,
                json=payload,
                timeout=(connect_timeout, read_timeout),
            )
            if response.status_code >= 400:
                # Log response body to aid debugging of 400s
                app.logger.warning(
                    "AI explainer HTTP error %s: %s", response.status_code, response.text[:500]
                )
                response.raise_for_status()
            raw = response.json()
            output_text = None
            if isinstance(raw, dict):
                output = raw.get("output")
                if isinstance(output, list) and output:
                    content = output[0].get("content") if isinstance(output[0], dict) else None
                    if isinstance(content, list) and content:
                        text_obj = content[0]
                        if isinstance(text_obj, dict):
                            output_text = text_obj.get("text") or text_obj.get("output_text")
                # legacy chat fallback
                if not output_text and raw.get("choices"):
                    output_text = raw["choices"][0]["message"]["content"]
            if not output_text:
                raise AiExplainerError(f"Empty response content: {raw}")
            payload_json = json.loads(output_text)
            return _validate_payload(payload_json)
        except requests.RequestException as exc:
            if attempt >= max_retries:
                raise
            delay = backoff * attempt
            app.logger.warning(
                "AI explainer call failed (attempt %s/%s): %s. Retrying in %.1fs",
                attempt,
                max_retries,
                exc,
                delay,
            )
            time.sleep(delay)
        except json.JSONDecodeError as exc:
            raise AiExplainerError("Invalid JSON from explainer") from exc


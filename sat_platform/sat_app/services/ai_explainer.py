"""AI explainer service to generate bilingual explanations."""

from __future__ import annotations

import json
from typing import Any, Dict, List
from pathlib import Path
import base64

from flask import current_app

from .ai_client import get_ai_client


ANIMATION_PROTOCOL = "tutor.anim.v1"


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
    figures = []
    figure_query = getattr(question, "figures", None)
    if figure_query is None:
        return figures
    try:
        figure_items = figure_query.all()
    except Exception:  # pragma: no cover - defensive
        figure_items = []
    for item in figure_items:
        image_path = getattr(item, "image_path", None)
        if not image_path:
            continue
        data_url = _encode_figure_image(Path(image_path))
        if not data_url:
            continue
        figures.append(
            {
                "id": item.id,
                "description": item.description,
                "image_url": data_url,
            }
        )
    return figures


def _build_messages(question, user_answer, user_language: str, depth: str, figures: List[Dict[str, Any]]) -> list[dict[str, Any]]:
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
    system_prompt = (
        "You are an elite SAT tutor who provides animated explanations.\n"
        "Respond with **pure JSON** matching the schema shown below. Do not add markdown or commentary.\n"
        f"{schema_description}\n"
        "Guidelines:\n"
        "- Produce 5 to 7 steps (add more if the passage is complex) so the reasoning feels granular.\n"
        "- duration_ms must be between 1500 and 4000; delay_ms between 200 and 800.\n"
        "- narration must sound like a calm teacher guiding a student.\n"
        "- Each step MUST include at least one animation referencing a short snippet from the passage, stem, or choices. Mix actions (highlight, underline, circle, strike, annotate, note, font/color) and feel free to include multiple animations per step.\n"
        "- board_notes are concise reminders or mini formulas.\n"
        "- summary should be <= 80 words.\n"
        "- All narration, titles, and summary must be written only in the requested target language.\n"
        "- When mentioning the SAT heuristics provided below (even if they include Chinese phrases), restate them entirely in the requested language; do not mix languages.\n"
        "- Ensure answer_correct reflects whether the submitted answer matches the official key.\n"
        "- Teaching framework that MUST appear in the flow (translate to the requested language; only include bilingual text when the requested language is Chinese):\n"
        "  * Reading General Rules: answer must have textual evidence, avoid extreme wording, correct choices restate the text, no gut guesses.\n"
        "  * Reading Four-Step Method: (1) identify keywords (names/time/logic cues) (2) understand paragraph function (3) revisit the text for synonyms/logic (4) eliminate wrong answers (not stated / concept shift / over-generalization / subjective guess).\n"
        "  * Writing Three Checks: subject-verb agreement, parallel structure, logical clarity; mantra: keep it short, simple, active, and precise.\n"
        "  * Teaching template: what is tested? where are the keywords? where is the supporting text? why is the correct option right? why are others wrong?\n"
        "  * For evidence/definition/writing items, point out the exact sentence and explain why it fits.\n"
        "- Close the explanation by reinforcing “Reading: evidence rules, synonym = correct, speculation = wrong; Writing: clarity > brevity > correctness > style.” Translate this closing line into the requested language.\n"
        "- If figures are provided, interpret them directly (they are attached as images). When an animation focuses on a figure, set target to \"figure\", provide a short `text` describing the region (e.g., '1998 Beaumont bar'), set `figure_id` to the provided numeric ID, and explain how that visual supports or eliminates a choice. Mix figure-focused steps with textual steps.\n"
    )
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
    user_prompt = (
        f"Target language: {language_name} (language tag: {language_tag}).\n"
        f"Student answer leads to the following context:\n"
        f"Question stem: {question.stem_text}\n"
        f"Choices: {json.dumps(question.choices, ensure_ascii=False)}\n"
        f"Correct answer: {json.dumps(question.correct_answer, ensure_ascii=False)}\n"
        f"User answer: {json.dumps(user_answer, ensure_ascii=False)}\n"
        f"Section: {question.section}\n"
        f"Skill tags: {question.skill_tags}\n"
        f"Depth request: {depth}\n"
        f"Has figure: {question.has_figure}\n"
        f"Figure instructions: {figures_prompt}\n"
        "Explain why the correct option works AND why each incorrect option fails (tie back to the four error types: not mentioned, concept shift, over-generalization, subjective guess).\n"
        "If the skill tags indicate Writing, emphasize grammar/logic checkpoints; if Reading, spotlight keyword tracking and evidence sentences.\n"
        "Return ONLY the JSON object."
    )
    user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
    for figure in figures:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": figure["image_url"],
                    "detail": "high",
                },
            }
        )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = {"protocol_version", "question_id", "answer_correct", "language", "summary", "steps"}
    if not required_fields.issubset(payload):
        missing = required_fields - set(payload)
        raise ValueError(f"Missing keys in AI response: {missing}")
    steps = payload.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps must be a non-empty list")
    return payload


def generate_explanation(question, user_answer, user_language: str = "bilingual", depth: str = "standard"):
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

    client = get_ai_client()
    figures = _collect_question_figures(question)
    messages = _build_messages(question, user_answer, user_language, depth, figures)
    raw = client.chat(messages)
    content = raw["choices"][0]["message"]["content"]
    payload = json.loads(content)
    return _validate_payload(payload)


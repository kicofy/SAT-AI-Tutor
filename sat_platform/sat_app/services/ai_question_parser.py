"""AI powered question parser."""

from __future__ import annotations

import json
from typing import Any, Dict

from flask import current_app

from ..schemas.question_schema import QuestionCreateSchema
from .ai_client import get_ai_client

question_schema = QuestionCreateSchema()


def _fallback_payload(block: dict) -> dict:
    content = block.get("content") or ""
    lines = content.split("\n")
    stem = lines[0] if lines else "Untitled question"
    choices = {chr(65 + idx): text.strip() for idx, text in enumerate(lines[1:5]) if text.strip()}
    if not choices:
        choices = {"A": "Option A", "B": "Option B", "C": "Option C", "D": "Option D"}
    return {
        "section": "RW",
        "stem_text": stem,
        "choices": choices,
        "correct_answer": {"value": "A"},
        "difficulty_level": 3,
        "skill_tags": ["parser_fallback"],
        "metadata": block.get("metadata", {}),
    }


def _build_messages(block: dict) -> list[dict[str, str]]:
    system_prompt = (
        "You are an SAT content ingestion bot. "
        "Return ONLY JSON describing one question: "
        "{section, stem_text, choices, correct_answer, difficulty_level, skill_tags, metadata}."
    )
    user_prompt = block.get("content") or ""
    if block.get("type") == "image":
        user_prompt = json.dumps(block.get("metadata", {}), ensure_ascii=False)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def parse_raw_question_block(block: dict) -> Dict[str, Any]:
    if not current_app.config.get("AI_PARSER_ENABLE", True):
        return _fallback_payload(block)

    client = get_ai_client()
    messages = _build_messages(block)
    model = current_app.config.get("AI_PARSER_MODEL", current_app.config.get("AI_EXPLAINER_MODEL"))
    try:
        response = client.chat(messages, model=model)
        content = response["choices"][0]["message"]["content"]
        payload = json.loads(content)
        data = question_schema.load(payload)
    except Exception as exc:
        current_app.logger.warning("AI parser fallback due to error: %s", exc)
        data = _fallback_payload(block)
    return data


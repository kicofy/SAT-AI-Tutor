"""AI explainer service to generate bilingual explanations."""

from __future__ import annotations

import json
from typing import Any, Dict

from flask import current_app

from .ai_client import get_ai_client


def _build_messages(question, user_answer, user_language: str, depth: str) -> list[dict[str, str]]:
    system_prompt = (
        "You are an SAT tutor that must respond with pure JSON following this schema: "
        "{protocol_version, question_id, answer_correct, explanation_blocks:[{language,\"text_en\",\"text_zh\",related_parts}] }."
    )
    user_prompt = (
        f"Question:\n{question.stem_text}\n"
        f"Choices:\n{json.dumps(question.choices, ensure_ascii=False)}\n"
        f"Correct answer: {json.dumps(question.correct_answer, ensure_ascii=False)}\n"
        f"User answer: {json.dumps(user_answer, ensure_ascii=False)}\n"
        f"Language preference: {user_language}\n"
        f"Depth: {depth}\n"
        "Return ONLY the JSON object."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    required_fields = {"protocol_version", "question_id", "answer_correct", "explanation_blocks"}
    if not required_fields.issubset(payload):
        missing = required_fields - set(payload)
        raise ValueError(f"Missing keys in AI response: {missing}")
    return payload


def generate_explanation(question, user_answer, user_language: str = "bilingual", depth: str = "standard"):
    app = current_app
    if not app.config.get("AI_EXPLAINER_ENABLE", False):
        return {
            "protocol_version": "draft-stub",
            "question_id": question.id,
            "answer_correct": user_answer == question.correct_answer,
            "explanation_blocks": [
                {
                    "language": user_language,
                    "text_en": "AI explainer disabled. Please enable AI_EXPLAINER_ENABLE to receive full explanations.",
                    "text_zh": "AI 讲解已禁用，请开启 AI_EXPLAINER_ENABLE 以获取完整讲解。",
                    "related_parts": [],
                }
            ],
        }

    client = get_ai_client()
    messages = _build_messages(question, user_answer, user_language, depth)
    raw = client.chat(messages)
    content = raw["choices"][0]["message"]["content"]
    payload = json.loads(content)
    return _validate_payload(payload)


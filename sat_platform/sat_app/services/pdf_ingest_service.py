"""Vision-aware PDF ingestion powered by multimodal AI."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Any, Dict, List

import pdfplumber
import requests
from flask import current_app

from ..schemas.question_schema import QuestionCreateSchema

question_schema = QuestionCreateSchema()


def ingest_pdf_document(source_path: str | Path) -> List[dict]:
    """Parse a PDF file and return normalized question payloads."""
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(path)

    pages = _extract_pages(path)
    normalized: List[dict] = []
    for idx, page in enumerate(pages, start=1):
        questions = _request_page_questions(page, page_index=idx)
        if not questions:
            continue
        for raw_question in questions:
            try:
                normalized.append(_normalize_question(raw_question))
            except Exception as exc:  # pragma: no cover - guarded by unit tests
                current_app.logger.warning(
                    "PDF ingest: failed to normalize question on page %s: %s", idx, exc
                )
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


def _request_page_questions(page_data: Dict[str, Any], page_index: int) -> List[dict]:
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
                    "required": ["question_number", "prompt", "choices"],
                },
            }
        },
        "required": ["questions"],
    }

    schema_hint = json.dumps(schema, ensure_ascii=False, indent=2)
    system_prompt = (
        "You are an assistant that extracts SAT questions from PDF pages. "
        "Return STRICT JSON that matches the provided schema. If the page "
        "contains no questions, return {\"questions\": []}."
    )
    user_prompt = (
        f"You are examining page {page_index} of an SAT prep PDF. Identify every "
        "complete question (including passages) and output JSON following this schema:\n"
        f"{schema_hint}\nReturn ONLY the JSON object."
    )

    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if text:
        user_content.append({"type": "input_text", "text": text[:12000]})
    if image_b64:
        user_content.append({"type": "input_image", "image_url": image_b64})

    payload = {
        "model": current_app.config.get("AI_PDF_VISION_MODEL", "gpt-4.1"),
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
    }
    raw_text = _call_responses_api(payload)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        current_app.logger.warning("PDF ingest: invalid JSON on page %s: %s", page_index, raw_text[:200])
        return []
    questions = data.get("questions", [])
    if isinstance(questions, list):
        return questions
    return []


def _normalize_question(question_payload: dict) -> dict:
    system_prompt = (
        "You are an SAT content normalizer. Convert extracted question snippets into "
        "the canonical JSON schema used by the SAT AI Tutor platform."
    )
    schema_hint = (
        "Fields: section, sub_section, stem_text, choices (dict A/B/C/D), "
        "correct_answer (object with value), difficulty_level (1-5), skill_tags "
        "(list), optional passage, optional metadata."
    )
    user_prompt = json.dumps(question_payload, ensure_ascii=False, indent=2)
    payload = {
        "model": current_app.config.get("AI_PDF_NORMALIZE_MODEL", "gpt-4.1"),
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
    raw_text = _call_responses_api(payload)
    data = json.loads(raw_text)
    return question_schema.load(data)


def _call_responses_api(payload: dict) -> str:
    app = current_app
    api_key = app.config.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY / AI_API_KEY must be configured for PDF ingestion.")
    base_url = app.config.get("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    timeout = app.config.get("AI_TIMEOUT_SECONDS", 120)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = requests.post(
        f"{base_url}/responses",
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    texts: List[str] = []
    for chunk in data.get("output", []):
        for content in chunk.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                texts.append(content.get("text", ""))
    if not texts and data.get("output_text"):
        texts.extend(data["output_text"])
    return "".join(texts).strip()



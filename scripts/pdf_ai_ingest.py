#!/usr/bin/env python3
"""
AI-first ingestion workflow for SAT PDFs.

This script performs two passes against a general-purpose multimodal model:
1. Send the entire PDF text to the model and request a rough JSON extraction
   containing question numbers, passages, stems, and choices.
2. For each extracted question, invoke a second prompt that normalizes the
   structure into the platform's Question schema (same fields used by
   /api/admin/questions or ai_question_parser).

Usage:
------
python3 scripts/pdf_ai_ingest.py \
    --pdf "scripts/samples/2408亚太B Reading_郭乃蕊老师.pdf" \
    --model gpt-4.1 \
    --output normalized_questions.json

Optional: automatically POST normalized questions to the backend drafts API:
python3 scripts/pdf_ai_ingest.py \
    --pdf /path/to/file.pdf \
    --model gpt-4.1 \
    --post http://127.0.0.1:5080 \
    --token "<admin JWT>"

Environment:
------------
Requires OPENAI_API_KEY (or AI_API_KEY) in the environment, plus pdfplumber.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import base64
import io

import pdfplumber
import requests
from openai import OpenAI
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / "sat_platform" / ".env"
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or os.getenv("AI_API_KEY"))


def extract_pdf_pages(pdf_path: Path) -> List[Dict[str, Any]]:
    pages: List[Dict[str, Any]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pil_image = page.to_image(resolution=220).original.convert("RGB")
            buffer = io.BytesIO()
            pil_image.save(buffer, format="PNG")
            image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
            metadata = {"page": idx, "width": page.width, "height": page.height}
            pages.append(
                {
                    "text": text,
                    "image_b64": f"data:image/png;base64,{image_b64}",
                    "metadata": metadata,
                }
            )
    return pages


def request_initial_json(page_data: Dict[str, Any], model: str) -> List[dict]:
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

    text = (page_data.get("text") or "").strip()
    image_b64 = page_data.get("image_b64")
    page_no = page_data.get("metadata", {}).get("page", "unknown")

    if not text and not image_b64:
        return []

    system_prompt = (
        "You are an assistant that extracts SAT questions from PDF pages. "
        "Group content by question number, capture passages/stems/choices, "
        "and return strict JSON. If a page has no questions, return {\"questions\": []}."
    )

    schema_hint = json.dumps(schema, ensure_ascii=False, indent=2)
    user_prompt = (
        f"You are looking at page {page_no} of an SAT prep PDF. "
        "Identify complete questions (including passages if present). "
        "Return ONLY a JSON object shaped exactly like this schema:\n"
        f"{schema_hint}\n"
        "Do not add commentary. If the page has no questions, return {\"questions\": []}."
    )

    user_content: List[Dict[str, Any]] = [{"type": "input_text", "text": user_prompt}]
    if text:
        user_content.append({"type": "input_text", "text": text[:12000]})
    if image_b64:
        user_content.append({"type": "input_image", "image_url": image_b64})

    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    content = response.output[0].content[0].text
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    return data.get("questions", [])


def normalize_question(question: dict, model: str) -> dict:
    system_prompt = (
        "You are an SAT content normalizer. Transform the extracted question "
        "into the canonical schema used by the SAT AI Tutor platform. "
        "Fields: section (RW or Math), sub_section, stem_text, choices (dict), "
        "correct_answer (dict with value/justification if unknown, set value to null), "
        "difficulty_level (1-5), skill_tags (list), passage? (object), metadata (dict). "
        "If the answer isn't known, set correct_answer.value to null and include "
        "\"confidence\":\"unknown\"."
    )
    user_prompt = json.dumps(question, ensure_ascii=False, indent=2)
    prompt = (
        "Normalize this SAT question to the canonical schema and return ONLY JSON.\n"
        f"{user_prompt}"
    )
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ],
    )
    content = response.output[0].content[0].text
    return json.loads(content)


def post_to_backend(base_url: str, token: str, normalized: List[dict]) -> None:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/admin/questions/parse",
        json={"blocks": [{"type": "text", "content": json.dumps(q), "metadata": {"normalized": True}} for q in normalized]},
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    )
    resp.raise_for_status()
    print("Backend accepted payload:", json.dumps(resp.json(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert SAT PDF to normalized questions via AI.")
    parser.add_argument("--pdf", required=True, help="Path to PDF file.")
    parser.add_argument("--model", default=os.getenv("AI_PARSER_MODEL", "gpt-4.1"), help="OpenAI model name.")
    parser.add_argument("--output", help="Write normalized JSON array to file.")
    parser.add_argument("--post", help="Optional backend base URL to POST drafts.")
    parser.add_argument("--token", help="Admin JWT token used with --post.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    pages = extract_pdf_pages(pdf_path)
    total_pages = len(pages)
    print(f"Loaded {total_pages} page(s) from {pdf_path.name}", flush=True)
    normalized: List[dict] = []

    for idx, page in enumerate(pages, start=1):
        page_no = page.get("metadata", {}).get("page", idx)
        print(f"[{idx}/{total_pages}] Processing page {page_no}...", flush=True)
        questions = request_initial_json(page, args.model)
        if not questions:
            print("  -> No questions detected on this page.", flush=True)
            continue
        print(f"  -> Extracted {len(questions)} question candidate(s).", flush=True)
        for q in questions:
            normalized.append(normalize_question(q, args.model))
        print(f"  -> Normalized total so far: {len(normalized)} question(s).", flush=True)

    if not normalized:
        raise RuntimeError("Model did not return any questions from the PDF pages.")

    if args.post:
        if not args.token:
            raise SystemExit("--token is required when using --post")
        post_to_backend(args.post, args.token, normalized)
    else:
        payload = json.dumps(normalized, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
            print(f"Wrote {len(normalized)} normalized questions to {args.output}")
        else:
            print(payload)


if __name__ == "__main__":
    main()


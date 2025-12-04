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
    --model gpt-5.1 \
    --output normalized_questions.json

Optional: automatically POST normalized questions to the backend drafts API:
python3 scripts/pdf_ai_ingest.py \
    --pdf /path/to/file.pdf \
    --model gpt-5.1 \
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
import re

import pdfplumber
import requests
from openai import OpenAI
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
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
            metadata = {
                "page": idx,
                "width": page.width,
                "height": page.height,
            }
            pages.append(
                {
                    "text": text,
                    "image_b64": f"data:image/png;base64,{image_b64}",
                    "metadata": metadata,
                    "pil_image": pil_image,
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
                        "has_figure": {"type": "boolean"},
                        "figure_note": {"type": "string"},
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
        "and return strict JSON. For each question, indicate whether it depends on an image/figure by setting "
        "\"has_figure\": true or false. Do NOT guess bounding boxes at this stage—just flag whether a figure is needed "
        "and include an optional short note (figure_note) describing which graphic is referenced. "
        "If a page has no questions, return {\"questions\": []}."
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
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(
            "    !! Normalization failed for question",
            question.get("question_number"),
            "- model response was not valid JSON:",
        )
        print("       ", content[:400])
        return None


def request_figure_bboxes(
    question: dict,
    page_data: Dict[str, Any],
    model: str,
) -> List[Dict[str, Any]]:
    image_b64 = page_data.get("image_b64")
    if not image_b64:
        return []
    metadata = page_data.get("metadata", {})
    page_no = metadata.get("page", "unknown")
    schema = {
        "type": "object",
        "properties": {
            "figures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "width": {"type": "number"},
                        "height": {"type": "number"},
                        "description": {"type": "string"},
                    },
                    "required": ["x", "y", "width", "height"],
                },
            }
        },
        "required": ["figures"],
    }
    system_prompt = (
        "You are locating precise bounding boxes for figures/graphs in an SAT PDF page image. "
        "Given the page image plus the question text, return the pixel coordinates of every figure that the question needs. "
        "Coordinates should be integers relative to the provided image (origin at top-left). Return strict JSON."
    )
    user_prompt = (
        f"You are analyzing page {page_no}. The page image resolution matches the data URI provided. "
        "The question referencing the figure is as follows:\n"
        f"Question #: {question.get('question_number')}\n"
        f"Prompt: {question.get('prompt')}\n"
        f"Choices: {question.get('choices')}\n"
        "If multiple figures are required, return each bounding box separately. "
        "If no figure is actually referenced, return {\"figures\": []}."
    )
    schema_hint = json.dumps(schema, ensure_ascii=False, indent=2)
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": user_prompt + "\nSchema:\n" + schema_hint},
                    {"type": "input_image", "image_url": image_b64},
                ],
            },
        ],
    )
    content = response.output[0].content[0].text
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    return data.get("figures", [])


def _slugify(value: str) -> str:
    value = value or "question"
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "question"


def save_question_figures(
    question: dict,
    page: Dict[str, Any],
    figure_dir: Path,
) -> List[Dict[str, Any]]:
    figures = question.get("figures") or []
    if not figures:
        return []
    image = page.get("pil_image")
    metadata = page.get("metadata", {})
    page_no = metadata.get("page", "page")
    if image is None:
        return []

    output_dir = figure_dir / f"page_{page_no:03d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    saved: List[Dict[str, Any]] = []
    slug = _slugify(str(question.get("question_number", "")))
    for idx, fig in enumerate(figures, start=1):
        try:
            x = int(fig.get("x", 0))
            y = int(fig.get("y", 0))
            width = int(fig.get("width", 0))
            height = int(fig.get("height", 0))
        except (TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        crop_box = (x, y, x + width, y + height)
        cropped = image.crop(crop_box)
        filename = output_dir / f"{slug}_fig{idx}.png"
        cropped.save(filename)
        saved.append(
            {
                "path": str(filename.resolve()),
                "description": fig.get("description") or "",
                "bbox": {"x": x, "y": y, "width": width, "height": height},
            }
        )
    return saved


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
    parser.add_argument("--model", default=os.getenv("AI_PARSER_MODEL", "gpt-5.1"), help="OpenAI model name.")
    parser.add_argument("--output", help="Write normalized JSON array to file.")
    parser.add_argument(
        "--figures-dir",
        help="Directory to export cropped figures. Defaults to ./figure_crops/<pdf-name>.",
    )
    parser.add_argument("--post", help="Optional backend base URL to POST drafts.")
    parser.add_argument("--token", help="Admin JWT token used with --post.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    pages = extract_pdf_pages(pdf_path)
    total_pages = len(pages)
    print(f"Loaded {total_pages} page(s) from {pdf_path.name}", flush=True)
    normalized: List[dict] = []
    figure_base = (
        Path(args.figures_dir).expanduser()
        if args.figures_dir
        else Path(__file__).resolve().parent / "figure_crops"
    )
    figure_root = (figure_base / pdf_path.stem).resolve()
    figure_root.mkdir(parents=True, exist_ok=True)

    for idx, page in enumerate(pages, start=1):
        page_no = page.get("metadata", {}).get("page", idx)
        print(f"[{idx}/{total_pages}] Processing page {page_no}...", flush=True)
        questions = request_initial_json(page, args.model)
        if not questions:
            print("  -> No questions detected on this page.", flush=True)
            continue
        print(f"  -> Extracted {len(questions)} question candidate(s).", flush=True)
        for q in questions:
            if q.get("has_figure"):
                figures = request_figure_bboxes(q, page, args.model)
                q["figures"] = figures
                if figures:
                    print(
                        f"    -> Located {len(figures)} figure(s) for question {q.get('question_number')}",
                        flush=True,
                    )
            saved_figs = save_question_figures(q, page, figure_root)
            question_payload = dict(q)
            question_payload.pop("figures", None)
            normalized_question = normalize_question(question_payload, args.model)
            if normalized_question is None:
                print(
                    f"    -> Skipping question {q.get('question_number')} due to normalization error.",
                    flush=True,
                )
                continue
            if saved_figs:
                normalized_question["figures"] = saved_figs
                print(
                    f"    -> Saved {len(saved_figs)} figure(s) for question {q.get('question_number')}",
                    flush=True,
                )
            normalized.append(normalized_question)
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


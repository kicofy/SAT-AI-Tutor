#!/usr/bin/env python3
"""
Utility script: normalize SAT questions from a PDF into AI-parser blocks.

Usage
-----
python3 scripts/standardize_pdf_questions.py \
    --pdf "scripts/samples/2408亚太B Reading_郭乃蕊老师.pdf" \
    --output blocks.json

Optional: send blocks directly to backend (requires admin JWT token):
python3 scripts/standardize_pdf_questions.py \
    --pdf /path/to/file.pdf \
    --post http://127.0.0.1:5080 \
    --token "$(cat token.txt)"

The script extracts textual questions from each page, groups them by number,
and emits a list of block dicts compatible with `POST /api/admin/questions/parse`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable, List

import pdfplumber
import requests

QUESTION_PATTERN = re.compile(r"^\s*(\d+)[\).\s]")
CHOICE_PATTERN = re.compile(r"^\s*([A-D])[\).\s]+(.+)$")


def extract_blocks(pdf_path: Path) -> List[dict]:
    blocks: List[dict] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            blocks.extend(_extract_from_text(text, page_index, pdf_path.name))
    return blocks


def _extract_from_text(text: str, page: int, filename: str) -> List[dict]:
    lines = [line.rstrip() for line in text.splitlines()]
    current: List[str] = []
    current_number: str | None = None
    blocks: List[dict] = []

    def flush():
        nonlocal current, current_number
        if not current:
            return
        blocks.append(
            {
                "type": "text",
                "content": "\n".join(current),
                "metadata": {
                    "source": filename,
                    "page": page,
                    "question_number": current_number,
                },
            }
        )
        current = []
        current_number = None

    for line in lines:
        if not line.strip():
            continue
        match = QUESTION_PATTERN.match(line)
        if match:
            flush()
            current_number = match.group(1)
        current.append(line.strip())
    flush()
    return blocks


def post_blocks(blocks: List[dict], base_url: str, token: str) -> None:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/admin/questions/parse",
        json={"blocks": blocks},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120,
    )
    resp.raise_for_status()
    print("Server response:", json.dumps(resp.json(), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize SAT PDF into parser blocks.")
    parser.add_argument("--pdf", required=True, help="Path to the PDF file.")
    parser.add_argument("--output", help="Write blocks to JSON file (default: stdout).")
    parser.add_argument("--post", help="Optional API base URL to POST blocks.")
    parser.add_argument("--token", help="Admin JWT token used with --post.")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    blocks = extract_blocks(pdf_path)
    if not blocks:
        raise SystemExit("No question-like blocks were detected. Check the PDF formatting.")

    if args.post:
        if not args.token:
            raise SystemExit("--token is required when using --post")
        post_blocks(blocks, args.post, args.token)
    else:
        payload = json.dumps(blocks, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
            print(f"Wrote {len(blocks)} blocks to {args.output}")
        else:
            print(payload)


if __name__ == "__main__":
    main()


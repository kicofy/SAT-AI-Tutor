"""
Direct OpenAI standardization for Job #30 coarse items (first N).

Steps:
1) Load OPENAI_API_KEY (and optional AI_API_BASE, AI_PDF_NORMALIZE_MODEL, DATABASE_URL) from Others/scripts/.env.
2) Read coarse question payloads from DB table question_drafts with job_id=JOB_ID (default 30), limit N (default 10).
3) For each coarse item, call OpenAI /v1/responses using the same standardization prompt as pdf_ingest_service.
4) Save full request/response logs and normalized outputs to JSON.

Outputs (next to this script):
  job{JOB_ID}_direct_norm.log
  job{JOB_ID}_direct_norm_first{N}.json
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Paths and sys.path
THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent  # repo root
for p in (PROJECT_ROOT, PROJECT_ROOT / "sat_platform"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Load env from Others/scripts/.env
env_path = THIS_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
API_BASE = os.getenv("AI_API_BASE", "https://api.openai.com/v1").rstrip("/")
MODEL = os.getenv("AI_PDF_NORMALIZE_MODEL", "gpt-4.1")
JOB_ID = int(os.getenv("JOB_ID", "30"))
LIMIT = int(os.getenv("LIMIT", "10"))


def _resolve_db_url() -> str:
    # Prefer explicit env
    env_db = os.getenv("DATABASE_URL")
    if env_db:
        return env_db
    default_path = PROJECT_ROOT / "sat_platform" / "instance" / "sat_dev.db"
    if default_path.exists():
        return f"sqlite:///{default_path}"
    raise RuntimeError(
        f"DATABASE_URL not set and default DB not found at {default_path}. "
        "Set DATABASE_URL in Others/scripts/.env (e.g., sqlite:////absolute/path/to/sat_dev.db)."
    )


DATABASE_URL = _resolve_db_url()

LOG_PATH = THIS_DIR / f"job{JOB_ID}_direct_norm.log"
OUT_PATH = THIS_DIR / f"job{JOB_ID}_direct_norm_first{LIMIT}.json"


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("job30_direct_norm")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(LOG_PATH)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


logger = setup_logger()


def fetch_coarse_items() -> List[Dict[str, Any]]:
    engine = create_engine(DATABASE_URL)
    query = text(
        """
        SELECT payload
        FROM question_drafts
        WHERE job_id = :job_id
        ORDER BY id
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(query, {"job_id": JOB_ID, "limit": LIMIT}).fetchall()
    coarse: List[Dict[str, Any]] = []
    for row in rows:
        payload = row[0]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue
        if isinstance(payload, dict):
            coarse.append(payload)
    return coarse


def build_normalize_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    system_prompt = (
        "You are an SAT content normalizer. Convert extracted question snippets into the canonical "
        "JSON schema used by the SAT AI Tutor platform. Output MUST be a single JSON object with:\n"
        "- section: \"RW\" or \"Math\".\n"
        "- question_type: \"choice\" or \"fill\".\n"
        "- stem_text: the question stem (no answer choices).\n"
        "- passage: {\"content_text\": \"...\"} when a supporting passage exists; otherwise null/omit.\n"
        "- choices: object of labeled choices for choice questions (e.g., {\"A\":\"...\",\"B\":\"...\"}).\n"
        "- correct_answer: {\"value\": \"A\"} for choice, or {\"value\": \"3/4\"} for fill.\n"
        "- answer_schema: for fill: include acceptable answers list (<=5 chars each, SAT grid-in rules), "
        "type (\"numeric\"/\"text\"), allow_fraction, allow_pi, strip_spaces.\n"
        "- skill_tags: up to two tags from the allowed list provided; if none apply, use [].\n"
        "- has_figure: true if the question references a figure/chart/table; choice_figure_keys for per-choice figures.\n"
        "- metadata: preserve source_question_number if available.\n"
        "Rules: Do NOT hallucinate content. Do NOT copy figure data into text. Preserve original wording. "
        "Return ONLY JSON, no comments."
    )

    passage = item.get("passage") or ""
    prompt_text = item.get("prompt") or item.get("stem_text") or ""
    choices = item.get("choices") or item.get("options") or item.get("answer_choices") or {}
    has_figure = bool(item.get("has_figure"))
    skill_tags = item.get("skill_tags") or []
    section = item.get("section") or ""
    source_qnum = (
        item.get("source_question_number")
        or item.get("question_number")
        or item.get("original_question_number")
    )

    user_lines = [
        f"Section: {section}",
        f"Passage: {passage or '(none)'}",
        f"Prompt: {prompt_text}",
        f"Choices: {json.dumps(choices, ensure_ascii=False)}",
        f"Has figure: {has_figure}",
        f"Skill tags (raw): {skill_tags}",
        f"Source question number: {source_qnum}",
    ]
    user_prompt = "\n".join(user_lines)

    payload = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "temperature": 0.1,
    }
    return payload


def call_openai(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is missing (set in Others/scripts/.env)")
    url = f"{API_BASE}/responses"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    logger.info("POST %s model=%s", url, payload.get("model"))
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    logger.info("Status %s", resp.status_code)
    logger.info("Resp headers: %s", dict(resp.headers))
    resp.raise_for_status()
    data = resp.json()
    texts: List[str] = []
    for chunk in data.get("output", []):
        for content in chunk.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                texts.append(content.get("text", ""))
    if not texts and data.get("output_text"):
        texts.extend(data["output_text"])
    raw = "".join(texts).strip()
    logger.info("Raw output: %s", raw[:500])
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse JSON output, returning raw text.")
        return {"raw_output": raw}


def main() -> None:
    logger.info("Starting direct normalization: job_id=%s limit=%s model=%s", JOB_ID, LIMIT, MODEL)
    coarse_items = fetch_coarse_items()
    logger.info("Fetched %s coarse items from question_drafts", len(coarse_items))

    normalized: List[Dict[str, Any]] = []
    for idx, item in enumerate(coarse_items[:LIMIT], start=1):
        try:
            payload = build_normalize_payload(item)
            result = call_openai(payload)
            normalized.append({"coarse": item, "normalized": result})
            logger.info("Normalized %s/%s done", idx, LIMIT)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Normalization failed for item %s: %s", idx, exc)

    OUT_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %s normalized entries to %s", len(normalized), OUT_PATH)


if __name__ == "__main__":
    main()


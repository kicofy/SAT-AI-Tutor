"""
Utility script to fetch the first N drafts from an import job and persist logs + JSON.

What it does:
1) Calls GET /api/admin/questions/imports (admin JWT required).
2) Filters drafts by job_id (default 30) and takes the first N (default 10).
3) Saves the drafts payloads to JSON and writes detailed request/response logs.

Env/config (all optional):
  API_BASE: default http://127.0.0.1:5080
  ADMIN_JWT: admin bearer token (required for auth)
  JOB_ID: target job id (default 30)
  LIMIT: number of drafts to dump (default 10)

Outputs (written next to this script):
  job{JOB_ID}_drafts_first{LIMIT}.json
  job{JOB_ID}_test.log
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import requests


def setup_logger(log_path: Path) -> logging.Logger:
    logger = logging.getLogger("job_test")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def fetch_imports(api_base: str, token: str, logger: logging.Logger) -> Dict[str, Any]:
    url = f"{api_base.rstrip('/')}/api/admin/questions/imports"
    headers = {"Authorization": f"Bearer {token}"}
    logger.info("GET %s", url)
    resp = requests.get(url, headers=headers, timeout=60)
    logger.info("Status %s", resp.status_code)
    try:
        payload = resp.json()
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to decode JSON: %s", exc)
        resp.raise_for_status()
        raise
    if resp.status_code != 200:
        logger.error("Non-200 response: %s", payload)
        resp.raise_for_status()
    return payload


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    api_base = os.getenv("API_BASE", "http://127.0.0.1:5080")
    token = os.getenv("ADMIN_JWT") or ""
    job_id = int(os.getenv("JOB_ID", "30"))
    limit = int(os.getenv("LIMIT", "10"))

    log_path = script_dir / f"job{job_id}_test.log"
    logger = setup_logger(log_path)

    if not token:
        logger.error("ADMIN_JWT is required.")
        return

    logger.info("Starting job draft fetch: job_id=%s limit=%s api_base=%s", job_id, limit, api_base)
    imports = fetch_imports(api_base, token, logger)
    drafts: List[Dict[str, Any]] = imports.get("drafts") or []
    filtered = [d for d in drafts if d.get("job_id") == job_id]
    logger.info("Found %s drafts for job %s", len(filtered), job_id)

    selected = filtered[:limit]
    out_path = script_dir / f"job{job_id}_drafts_first{limit}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    logger.info("Saved %s drafts to %s", len(selected), out_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()


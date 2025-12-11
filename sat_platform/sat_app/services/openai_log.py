"""In-memory log buffer plus SSE broadcast for OpenAI API interactions."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from flask import current_app

from .job_events import job_event_broker

LOG_MAX_ENTRIES = 500
_buffer: deque[Dict[str, Any]] = deque(maxlen=LOG_MAX_ENTRIES)


def _append_to_file(entry: Dict[str, Any]) -> None:
    """Persist log to a per-job file so logs survive restarts."""
    job_id = entry.get("job_id") or "general"
    app = current_app._get_current_object() if current_app else None
    base_dir = None
    if app and app.instance_path:
        base_dir = Path(app.instance_path) / "logs" / "openai"
    else:
        base_dir = Path("instance/logs/openai")
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        path = base_dir / f"job-{job_id}.log"
        path.write_text(path.read_text() + f"{entry}\n" if path.exists() else f"{entry}\n")
    except Exception:
        # Persistence should not break pipeline; ignore file errors.
        pass


def log_event(kind: str, payload: Dict[str, Any]) -> None:
    """Store a log entry in memory and append to per-job file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **payload,
    }
    _buffer.appendleft(entry)
    _append_to_file(entry)
    # Broadcast via the shared job-event SSE channel so the frontend can react immediately.
    try:
        job_event_broker.publish({"type": "openai_log", "payload": entry})
    except Exception:
        # Logging must never break the ingestion pipeline.
        pass


def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Return a copy of the most recent log entries (in-memory)."""
    limit = max(1, min(limit, LOG_MAX_ENTRIES))
    return list(_buffer)[:limit]


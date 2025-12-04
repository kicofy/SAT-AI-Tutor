"""In-memory log buffer plus SSE broadcast for OpenAI API interactions."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List

from .job_events import job_event_broker

LOG_MAX_ENTRIES = 500
_buffer: deque[Dict[str, Any]] = deque(maxlen=LOG_MAX_ENTRIES)


def log_event(kind: str, payload: Dict[str, Any]) -> None:
    """Store a log entry, keeping only the latest LOG_MAX_ENTRIES."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **payload,
    }
    _buffer.appendleft(entry)
    # Broadcast via the shared job-event SSE channel so the frontend can react immediately.
    try:
        job_event_broker.publish({"type": "openai_log", "payload": entry})
    except Exception:
        # Logging must never break the ingestion pipeline.
        pass


def get_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Return a copy of the most recent log entries."""
    limit = max(1, min(limit, LOG_MAX_ENTRIES))
    return list(_buffer)[:limit]


"""Application logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any
from uuid import uuid4

from flask import g, has_request_context, request


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.request_id = getattr(g, "request_id", "n/a")
            record.path = request.path
            record.method = request.method
        else:
            record.request_id = "-"
            record.path = "-"
            record.method = "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base: dict[str, Any] = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "request_id": getattr(record, "request_id", "-"),
            "path": getattr(record, "path", "-"),
            "method": getattr(record, "method", "-"),
        }
        if record.exc_info:
            base["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)


def configure_logging(app) -> None:
    level = app.config.get("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def assign_request_id() -> str:
    req_id = request.headers.get("X-Request-ID") if has_request_context() else None
    if not req_id:
        req_id = uuid4().hex
    g.request_id = req_id
    return req_id


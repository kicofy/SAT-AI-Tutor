"""Metrics endpoint for Prometheus scraping."""

from __future__ import annotations

from flask import Blueprint, Response

from ..metrics import latest_metrics

metrics_bp = Blueprint("metrics_bp", __name__)


@metrics_bp.get("/metrics")
def metrics():
    payload, content_type = latest_metrics()
    return Response(payload, mimetype=content_type)


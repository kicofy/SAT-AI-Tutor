"""Prometheus metrics helpers."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

REQUEST_COUNT = Counter(
    "sat_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "sat_request_latency_seconds",
    "Latency of HTTP requests in seconds",
    ["endpoint"],
)


def record_request(method: str, endpoint: str, status: int, latency: float) -> None:
    REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=status).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(latency)


def latest_metrics() -> tuple[bytes, str]:
    data = generate_latest()
    return data, CONTENT_TYPE_LATEST


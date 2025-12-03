"""Tests for logging/metrics hardening."""

from __future__ import annotations


def test_metrics_endpoint(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"sat_requests_total" in resp.data


def test_request_id_header(client):
    resp = client.get("/api/auth/ping")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


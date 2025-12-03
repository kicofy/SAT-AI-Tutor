"""Smoke tests for the Flask application factory."""

from __future__ import annotations

import pytest

from sat_app import create_app


@pytest.fixture(scope="module")
def app():
    app = create_app("test")
    yield app


def test_app_creation(app):
    assert app is not None
    assert app.config["TESTING"] is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/auth/ping",
        "/api/admin/ping",
        "/api/student/ping",
        "/api/question/ping",
        "/api/learning/ping",
        "/api/ai/ping",
        "/api/analytics/ping",
    ],
)
def test_ping_endpoints(app, endpoint):
    client = app.test_client()
    response = client.get(endpoint)
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"


"""Pytest configuration for ensuring project modules resolve correctly."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from sat_app import create_app
from sat_app.extensions import db
from sat_app.models import User, EmailVerificationTicket
from sat_app.utils.security import hash_password


@pytest.fixture()
def app_with_db():
    app = create_app("test")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_with_db):
    return app_with_db.test_client()


@pytest.fixture()
def student_token(app_with_db, client):
    email = "student@example.com"
    resp = client.post(
        "/api/auth/register/request-code",
        json={"email": email, "language_preference": "en"},
    )
    assert resp.status_code == 200
    with app_with_db.app_context():
        ticket = EmailVerificationTicket.query.filter_by(email=email).first()
        code = ticket.code
    register = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123!", "code": code},
    )
    return register.get_json()["access_token"]


@pytest.fixture()
def admin_token(app_with_db, client):
    with app_with_db.app_context():
        admin = User(
            email="admin@example.com",
            username="admin1",
            password_hash=hash_password("AdminPass123!"),
            role="admin",
            is_email_verified=True,
        )
        db.session.add(admin)
        db.session.commit()
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "admin@example.com", "password": "AdminPass123!"},
    )
    return resp.get_json()["access_token"]

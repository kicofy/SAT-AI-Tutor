"""Tests for the auth blueprint."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sat_app.models import User, EmailVerificationTicket
from sat_app.extensions import db
from sat_app.utils.security import hash_password

def test_register_creates_user_and_profile(client):
    payload = {
        "email": "Student@example.com",
        "password": "StrongPass123!",
        "username": "student_one",
        "profile": {
            "daily_available_minutes": 90,
            "language_preference": "en",
        },
    }
    payload["code"] = _request_registration_code(client, payload["email"])
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["user"]["email"] == "student@example.com"
    assert data["user"]["profile"]["daily_available_minutes"] == 90
    assert data["user"]["profile"]["language_preference"] == "en"


def test_register_duplicate_email_returns_conflict(client):
    payload = {"email": "dup@example.com", "password": "StrongPass123!"}
    payload["code"] = _request_registration_code(client, payload["email"])
    client.post("/api/auth/register", json=payload)
    payload2 = payload.copy()
    resp = client.post("/api/auth/register", json=payload2)
    assert resp.status_code == 409
    assert resp.get_json()["message"] == "Email already registered"


def test_login_returns_token(client):
    payload = {"email": "login@example.com", "password": "StrongPass123!"}
    payload["code"] = _request_registration_code(client, payload["email"])
    client.post("/api/auth/register", json=payload)
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "login@example.com", "password": payload["password"]},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert data["user"]["email"] == "login@example.com"


def test_login_invalid_credentials(client):
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "missing@example.com", "password": "nope"},
    )
    assert resp.status_code == 401
    assert resp.get_json()["message"] == "Invalid email or password"


def test_login_fails_when_email_not_verified(client):
    with client.application.app_context():
        user = User(
            email="pending@example.com",
            username="pending",
            password_hash=hash_password("StrongPass123!"),
            role="student",
            is_email_verified=False,
        )
        db.session.add(user)
        db.session.commit()
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "pending@example.com", "password": "StrongPass123!"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "email_not_verified"


def test_me_requires_jwt_and_returns_user(client):
    payload = {"email": "me@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "me@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]
    resp = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["user"]["email"] == "me@example.com"


def test_register_forces_student_role(client):
    payload = {
        "email": "wannabe_admin@example.com",
        "password": "StrongPass123!",
    }
    payload["code"] = _request_registration_code(client, payload["email"])
    resp = client.post("/api/auth/register", json=payload | {"role": "admin"})
    assert resp.status_code == 201
    assert resp.get_json()["user"]["role"] == "student"


def test_root_admin_can_create_admin(client):
    token = _login_root_admin(client)
    resp = client.post(
        "/api/auth/admin/create",
        json={
            "email": "newadmin@example.com",
            "username": "newadmin",
            "password": "StrongPass123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.get_json()["user"]["role"] == "admin"
    assert resp.get_json()["user"]["is_root"] is False


def test_non_root_admin_cannot_create_admin(client):
    token = _login_root_admin(client)
    client.post(
        "/api/auth/admin/create",
        json={
            "email": "admin2@example.com",
            "username": "admin2",
            "password": "StrongPass123!",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    admin_token = client.post(
        "/api/auth/login",
        json={"identifier": "admin2", "password": "StrongPass123!"},
    ).get_json()["access_token"]

    resp = client.post(
        "/api/auth/admin/create",
        json={
            "email": "admin3@example.com",
            "username": "admin3",
            "password": "StrongPass123!",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 403


def test_update_profile_changes_email_and_language(client):
    payload = {"email": "update@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "update@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]
    resp = client.patch(
        "/api/auth/profile",
        json={"email": "updated@example.com", "language_preference": "zh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()["user"]
    assert payload["email"] == "updated@example.com"
    assert payload["profile"]["language_preference"] == "zh"


def test_change_password_requires_current_password(client):
    payload = {"email": "changepw@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "changepw@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]
    bad = client.post(
        "/api/auth/password",
        json={"current_password": "WrongPass123!", "new_password": "NewStrongPass123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert bad.status_code == 400

    good = client.post(
        "/api/auth/password",
        json={"current_password": "StrongPass123!", "new_password": "NewStrongPass123!"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert good.status_code == 200
    # ensure login works with new password
    login_resp = client.post(
        "/api/auth/login",
        json={"identifier": "changepw@example.com", "password": "NewStrongPass123!"},
    )
    assert login_resp.status_code == 200


def test_request_code_enforces_cooldown(client):
    email = "resend@example.com"
    resp = client.post(
        "/api/auth/register/request-code",
        json={"email": email, "language_preference": "en"},
    )
    assert resp.status_code == 200
    cooldown = client.post(
        "/api/auth/register/request-code",
        json={"email": email, "language_preference": "en"},
    )
    assert cooldown.status_code == 400
    assert cooldown.get_json()["message"] == "verification_code_recent"


def _login_root_admin(client):
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "ha22y", "password": "Kicofy5438"},
    )
    assert resp.status_code == 200
    return resp.get_json()["access_token"]


def _request_registration_code(client, email: str) -> str:
    resp = client.post(
        "/api/auth/register/request-code",
        json={"email": email, "language_preference": "en"},
    )
    assert resp.status_code == 200
    with client.application.app_context():
        ticket = (
            EmailVerificationTicket.query.filter_by(email=email.lower())
            .order_by(EmailVerificationTicket.created_at.desc())
            .first()
        )
        assert ticket is not None
        return ticket.code


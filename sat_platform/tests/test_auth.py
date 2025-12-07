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


def test_update_profile_changes_language(client):
    payload = {"email": "update@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "update@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]
    resp = client.patch(
        "/api/auth/profile",
        json={"language_preference": "zh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.get_json()["user"]
    assert data["email"] == "update@example.com"
    assert data["profile"]["language_preference"] == "zh"


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


def test_email_change_flow_updates_user_email(client):
    payload = {"email": "change@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "change@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]

    new_email = "updated@example.com"
    code = _request_email_change_code(client, token, new_email)
    resp = client.post(
        "/api/auth/email/change/confirm",
        json={"new_email": new_email, "code": code},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    user_payload = resp.get_json()["user"]
    assert user_payload["email"] == new_email

    # old email should no longer allow login
    old_login = client.post(
        "/api/auth/login",
        json={"identifier": "change@example.com", "password": "StrongPass123!"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/api/auth/login",
        json={"identifier": new_email, "password": "StrongPass123!"},
    )
    assert new_login.status_code == 200


def test_email_change_request_rejects_existing_email(client):
    first = {"email": "taken@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "taken@example.com")}
    client.post("/api/auth/register", json=first)
    second = {"email": "second@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "second@example.com")}
    register = client.post("/api/auth/register", json=second)
    token = register.get_json()["access_token"]
    resp = client.post(
        "/api/auth/email/change/request",
        json={"new_email": "taken@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["message"] == "email_exists"


def test_email_change_confirm_rejects_wrong_code(client):
    payload = {"email": "wrongcode@example.com", "password": "StrongPass123!", "code": _request_registration_code(client, "wrongcode@example.com")}
    register = client.post("/api/auth/register", json=payload)
    token = register.get_json()["access_token"]
    new_email = "another@example.com"
    _request_email_change_code(client, token, new_email)
    resp = client.post(
        "/api/auth/email/change/confirm",
        json={"new_email": new_email, "code": "999999"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["message"] == "verification_code_invalid"
    # ensure email did not change
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.get_json()["user"]["email"] == "wrongcode@example.com"


def test_password_reset_request_and_confirm(client):
    email = "resetuser@example.com"
    payload = {"email": email, "password": "StrongPass123!", "code": _request_registration_code(client, email)}
    client.post("/api/auth/register", json=payload)

    resp = client.post("/api/auth/password/reset/request", json={"identifier": email})
    assert resp.status_code == 200

    with client.application.app_context():
        user = User.query.filter_by(email=email).first()
        token = user.password_reset_token
        assert token

    confirm = client.post(
        "/api/auth/password/reset/confirm",
        json={"token": token, "new_password": "NewPass123!"},
    )
    assert confirm.status_code == 200

    login = client.post(
        "/api/auth/login",
        json={"identifier": email, "password": "NewPass123!"},
    )
    assert login.status_code == 200


def test_password_reset_request_enforces_cooldown(client):
    email = "cooldown@example.com"
    payload = {"email": email, "password": "StrongPass123!", "code": _request_registration_code(client, email)}
    client.post("/api/auth/register", json=payload)

    first = client.post("/api/auth/password/reset/request", json={"identifier": email})
    assert first.status_code == 200

    second = client.post("/api/auth/password/reset/request", json={"identifier": email})
    assert second.status_code == 400
    assert second.get_json()["message"] == "reset_recent"


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
        ticket = EmailVerificationTicket.query.filter_by(email=email.lower(), purpose="signup").first()
        assert ticket is not None
        return ticket.code


def _request_email_change_code(client, token: str, email: str) -> str:
    resp = client.post(
        "/api/auth/email/change/request",
        json={"new_email": email},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    with client.application.app_context():
        ticket = EmailVerificationTicket.query.filter_by(email=email.lower(), purpose="email_change").first()
        assert ticket is not None
        return ticket.code


"""Tests for the auth blueprint."""

from __future__ import annotations

import pytest

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
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 201
    data = resp.get_json()
    assert "access_token" in data
    assert data["user"]["email"] == "student@example.com"
    assert data["user"]["profile"]["daily_available_minutes"] == 90
    assert data["user"]["profile"]["language_preference"] == "en"


def test_register_duplicate_email_returns_conflict(client):
    payload = {"email": "dup@example.com", "password": "StrongPass123!"}
    client.post("/api/auth/register", json=payload)
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.get_json()["message"] == "Email already registered"


def test_login_returns_token(client):
    payload = {"email": "login@example.com", "password": "StrongPass123!"}
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


def test_me_requires_jwt_and_returns_user(client):
    register = client.post(
        "/api/auth/register", json={"email": "me@example.com", "password": "StrongPass123!"}
    )
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


def _login_root_admin(client):
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "ha22y", "password": "Kicofy5438"},
    )
    assert resp.status_code == 200
    return resp.get_json()["access_token"]


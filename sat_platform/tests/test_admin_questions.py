"""Tests for admin question CRUD endpoints."""

from __future__ import annotations

import copy

import pytest


QUESTION_PAYLOAD = {
    "section": "RW",
    "sub_section": "Grammar",
    "stem_text": "Which choice corrects the sentence?",
    "choices": {"A": "choice A", "B": "choice B", "C": "choice C", "D": "choice D"},
    "correct_answer": {"value": "A"},
    "difficulty_level": 3,
    "skill_tags": ["grammar", "structure"],
    "estimated_time_sec": 75,
    "metadata": {"source": "unit test"},
}


def test_admin_can_crud_questions(client):
    token = _login_root_admin(client)

    create_resp = client.post(
        "/api/admin/questions",
        json=QUESTION_PAYLOAD,
        headers=_auth_headers(token),
    )
    assert create_resp.status_code == 201
    question = create_resp.get_json()["question"]
    question_id = question["id"]

    list_resp = client.get(
        "/api/admin/questions",
        headers=_auth_headers(token),
    )
    assert list_resp.status_code == 200
    assert list_resp.get_json()["total"] == 1

    get_resp = client.get(
        f"/api/admin/questions/{question_id}",
        headers=_auth_headers(token),
    )
    assert get_resp.status_code == 200

    update_payload = copy.deepcopy(QUESTION_PAYLOAD)
    update_payload["difficulty_level"] = 4
    update_resp = client.put(
        f"/api/admin/questions/{question_id}",
        json=update_payload,
        headers=_auth_headers(token),
    )
    assert update_resp.status_code == 200
    assert update_resp.get_json()["question"]["difficulty_level"] == 4

    delete_resp = client.delete(
        f"/api/admin/questions/{question_id}",
        headers=_auth_headers(token),
    )
    assert delete_resp.status_code == 204

    final_list = client.get(
        "/api/admin/questions",
        headers=_auth_headers(token),
    )
    assert final_list.get_json()["total"] == 0


def test_student_cannot_access_admin_questions(client):
    client.post(
        "/api/auth/register",
        json={"email": "student@example.com", "password": "StrongPass123!"},
    )
    token = client.post(
        "/api/auth/login",
        json={"identifier": "student@example.com", "password": "StrongPass123!"},
    ).get_json()["access_token"]

    resp = client.get(
        "/api/admin/questions",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 403


def _login_root_admin(client):
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "ha22y", "password": "Kicofy5438"},
    )
    assert resp.status_code == 200
    return resp.get_json()["access_token"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


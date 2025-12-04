#!/usr/bin/env python3
import json
import sys
import time
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:5080"
ADMIN_EMAIL = "ha22y@example.com"
ADMIN_PASSWORD = "Kicofy5438"

def pretty(title, resp):
    print(f"\n=== {title} ===")
    print(f"Status: {resp.status_code}")
    try:
        print(json.dumps(resp.json(), ensure_ascii=False, indent=2))
    except Exception:
        print(resp.text)

def admin_login():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    print("Admin login OK")
    return {"Authorization": f"Bearer {token}"}

def create_question(admin_headers):
    payload = {
        "section": "RW",
        "sub_section": "Grammar",
        "stem_text": "Which choice is grammatically correct?",
        "choices": {"A": "Choice A", "B": "Choice B", "C": "Choice C", "D": "Choice D"},
        "correct_answer": {"value": "A"},
        "difficulty_level": 2,
        "skill_tags": ["RW_Grammar"],
    }
    resp = requests.post(
        f"{BASE_URL}/api/admin/questions",
        json=payload,
        headers=admin_headers,
    )
    pretty("Admin Create Question", resp)
    resp.raise_for_status()
    return resp.json()["question"]["id"]

def register_student():
    resp = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": "tester1@example.com",
            "password": "StrongPass123!",
            "username": "tester2",
            "profile": {"daily_available_minutes": 60, "language_preference": "bilingual"},
        },
    )
    pretty("Student Register", resp)
    resp.raise_for_status()
    return resp.json()["access_token"]

def student_login():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"identifier": "tester@example.com", "password": "StrongPass123!"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def start_session(headers):
    resp = requests.post(
        f"{BASE_URL}/api/learning/session/start",
        json={"num_questions": 1},
        headers=headers,
    )
    pretty("Start Session", resp)
    resp.raise_for_status()
    return resp.json()["session"]

def answer_question(headers, session, answer_value="A"):
    q = session["questions_assigned"][0]
    resp = requests.post(
        f"{BASE_URL}/api/learning/session/answer",
        json={
            "session_id": session["id"],
            "question_id": q["question_id"],
            "user_answer": {"value": answer_value},
            "time_spent_sec": 30,
        },
        headers=headers,
    )
    pretty("Answer Question", resp)

def end_session(headers, session):
    resp = requests.post(
        f"{BASE_URL}/api/learning/session/end",
        json={"session_id": session["id"]},
        headers=headers,
    )
    pretty("End Session", resp)

def call_learning_plan(headers):
    resp = requests.get(f"{BASE_URL}/api/learning/plan/today", headers=headers)
    pretty("Learning Plan", resp)

def call_mastery(headers):
    resp = requests.get(f"{BASE_URL}/api/learning/mastery", headers=headers)
    pretty("Mastery Snapshot", resp)

def call_progress(headers):
    resp = requests.get(f"{BASE_URL}/api/analytics/progress", headers=headers)
    pretty("Analytics Progress", resp)

def call_diagnose(headers):
    resp = requests.post(f"{BASE_URL}/api/ai/diagnose", headers=headers)
    pretty("AI Diagnose", resp)

def call_explain(headers, question_id):
    resp = requests.post(
        f"{BASE_URL}/api/ai/explain",
        json={"question_id": question_id, "user_answer": {"value": "A"}},
        headers=headers,
    )
    pretty("AI Explain", resp)

def manual_parse(admin_headers):
    resp = requests.post(
        f"{BASE_URL}/api/admin/questions/parse",
        json={"blocks": [{"type": "text", "content": "Stem\nA\nB"}]},
        headers=admin_headers,
    )
    pretty("Manual Parse", resp)

def list_imports(admin_headers):
    resp = requests.get(f"{BASE_URL}/api/admin/questions/imports", headers=admin_headers)
    pretty("List Imports", resp)

def metrics():
    resp = requests.get(f"{BASE_URL}/metrics")
    print("\n=== /metrics (first 200 chars) ===")
    print(resp.text[:200])

def main():
    admin_headers = admin_login()
    question_id = create_question(admin_headers)

    # Student flow
    register_student()
    student_token = student_login()
    student_headers = {"Authorization": f"Bearer {student_token}"}

    session = start_session(student_headers)
    answer_question(student_headers, session)
    end_session(student_headers, session)

    call_mastery(student_headers)
    call_learning_plan(student_headers)
    call_progress(student_headers)
    call_diagnose(student_headers)
    call_explain(student_headers, question_id)

    manual_parse(admin_headers)
    list_imports(admin_headers)

    metrics()

if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print("HTTP Error:", exc.response.status_code, exc.response.text)
        sys.exit(1)
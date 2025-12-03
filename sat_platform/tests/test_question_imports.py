"""Tests for AI question parser pipeline."""

from __future__ import annotations

import io

import pytest

from sat_app.extensions import db
from sat_app.models import QuestionDraft


@pytest.fixture()
def mock_parser(monkeypatch):
    def _fake_parser(block):
        return {
            "section": "RW",
            "stem_text": block.get("content", "Default stem"),
            "choices": {"A": "Option A", "B": "Option B"},
            "correct_answer": {"value": "A"},
            "difficulty_level": 2,
            "skill_tags": ["grammar"],
            "metadata": block.get("metadata", {}),
        }

    monkeypatch.setattr("sat_app.services.ai_question_parser.parse_raw_question_block", _fake_parser)


@pytest.fixture()
def mock_pdf_ingest(monkeypatch):
    def _fake_ingest(_path):
        return [
            {
                "section": "RW",
                "sub_section": "Grammar",
                "stem_text": "Vision stem",
                "choices": {"A": "Alpha", "B": "Beta"},
                "correct_answer": {"value": "A"},
                "difficulty_level": 2,
                "skill_tags": ["vision"],
                "metadata": {"source": "pdf-test"},
            }
        ]

    monkeypatch.setattr("sat_app.services.pdf_ingest_service.ingest_pdf_document", _fake_ingest)


def test_manual_parse_creates_drafts(client, admin_token, mock_parser):
    resp = client.post(
        "/api/admin/questions/parse",
        json={"blocks": [{"type": "text", "content": "Stem\nA\nB"}]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 202
    data = resp.get_json()["job"]
    assert data["status"] == "completed"
    with client.application.app_context():
        assert QuestionDraft.query.count() == 1


def test_upload_flow(client, admin_token, mock_parser):
    payload = io.BytesIO(b"Question stem\nA\nB\n\nNext question?\nA\nB")
    resp = client.post(
        "/api/admin/questions/upload",
        data={"file": (payload, "questions.txt")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202
    jobs = client.get(
        "/api/admin/questions/imports",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).get_json()
    assert jobs["jobs"]
    assert jobs["drafts"]


def test_pdf_ingest_flow(client, admin_token, mock_pdf_ingest):
    payload = io.BytesIO(b"%PDF-1.4 vision-mock")
    resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (payload, "vision.pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202
    data = resp.get_json()["job"]
    assert data["ingest_strategy"] == "vision_pdf"
    assert data["parsed_questions"] == 1
    with client.application.app_context():
        drafts = QuestionDraft.query.all()
        assert len(drafts) == 1
        assert drafts[0].payload["skill_tags"] == ["vision"]


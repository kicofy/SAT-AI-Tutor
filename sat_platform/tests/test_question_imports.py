"""Tests for AI question parser pipeline."""

from __future__ import annotations

import io

import pytest

from sat_app.extensions import db
from sat_app.models import QuestionDraft, Question, QuestionFigure, QuestionImportJob, QuestionSource, User
from sat_app.services import question_service


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
    def _fake_ingest(_path, progress_cb=None, question_cb=None, job_id=None):
        if progress_cb:
            progress_cb(1, 2, 1, "halfway")
            progress_cb(2, 2, 1, "done")
        payloads = [
            {
                "section": "RW",
                "sub_section": "Grammar",
                "stem_text": "Vision stem",
                "choices": {"A": "Alpha", "B": "Beta"},
                "correct_answer": {"value": "A"},
                "difficulty_level": 2,
                "skill_tags": ["RW_DataInterpretation"],
                "metadata": {"source": "pdf-test"},
            }
        ]
        if question_cb:
            for payload in payloads:
                question_cb(payload)
        return payloads

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
    assert data["processed_pages"] == 2
    assert data["total_pages"] == 2
    assert data["source_id"] is not None
    assert data["source"]["filename"] == "vision.pdf"
    with client.application.app_context():
        drafts = QuestionDraft.query.all()
        assert len(drafts) == 1
        assert drafts[0].payload["skill_tags"] == ["RW_DataInterpretation"]
        assert drafts[0].source_id == data["source_id"]
        assert QuestionSource.query.count() == 1


def test_pdf_ingest_duplicate_requires_confirmation(client, admin_token, mock_pdf_ingest):
    first_payload = io.BytesIO(b"%PDF-1.4 original")
    resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (first_payload, "vision.pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202

    second_payload = io.BytesIO(b"%PDF-1.4 new-content")
    duplicate_resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (second_payload, "vision.pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert duplicate_resp.status_code == 409
    payload = duplicate_resp.get_json()
    assert payload["error"] == "duplicate_source"
    assert payload["source"]["filename"] == "vision.pdf"

    forced_payload = io.BytesIO(b"%PDF-1.4 forced")
    forced_resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (forced_payload, "vision.pdf"), "force": "true"},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert forced_resp.status_code == 202
    with client.application.app_context():
        assert QuestionSource.query.count() == 2


def _create_manual_draft(client, admin_token):
    resp = client.post(
        "/api/admin/questions/parse",
        json={"blocks": [{"type": "text", "content": "Stem\nA\nB"}]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 202
    with client.application.app_context():
        draft = QuestionDraft.query.first()
        assert draft is not None
        return draft.id


def test_delete_draft(client, admin_token, mock_parser):
    draft_id = _create_manual_draft(client, admin_token)
    resp = client.delete(
        f"/api/admin/questions/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204
    with client.application.app_context():
        assert QuestionDraft.query.count() == 0


def test_delete_draft_removes_source_when_empty(client, admin_token, mock_pdf_ingest):
    payload = io.BytesIO(b"%PDF-1.4 cleanup-source")
    resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (payload, "cleanup.pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202
    job = resp.get_json()["job"]
    source_id = job["source_id"]
    with client.application.app_context():
        draft = QuestionDraft.query.filter_by(source_id=source_id).first()
        assert draft is not None
        draft_id = draft.id
    delete_resp = client.delete(
        f"/api/admin/questions/drafts/{draft_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 204
    with client.application.app_context():
        assert db.session.get(QuestionSource, source_id) is None
        job_ref = db.session.get(QuestionImportJob, job["id"])
        assert job_ref is not None
        assert job_ref.source_id is None


def test_publish_draft(client, admin_token, mock_parser):
    draft_id = _create_manual_draft(client, admin_token)
    resp = client.post(
        f"/api/admin/questions/drafts/{draft_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    data = resp.get_json()["question"]
    assert data["section"] == "RW"
    with client.application.app_context():
        assert QuestionDraft.query.count() == 0
        assert Question.query.count() == 1


def test_publish_pdf_draft_links_source(client, admin_token, mock_pdf_ingest):
    payload = io.BytesIO(b"%PDF-1.4 vision-mock")
    resp = client.post(
        "/api/admin/questions/ingest-pdf",
        data={"file": (payload, "vision.pdf")},
        headers={"Authorization": f"Bearer {admin_token}"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 202
    job_data = resp.get_json()["job"]
    source_id = job_data["source_id"]
    with client.application.app_context():
        draft = QuestionDraft.query.first()
        draft_id = draft.id
    publish_resp = client.post(
        f"/api/admin/questions/drafts/{draft_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert publish_resp.status_code == 201
    question = publish_resp.get_json()["question"]
    assert question["source_id"] == source_id
    list_resp = client.get(
        f"/api/admin/questions?source_id={source_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_resp.status_code == 200
    assert list_resp.get_json()["total"] >= 1
    assert any(item["source_id"] == source_id for item in list_resp.get_json()["items"])


def test_publish_legacy_draft(client, admin_token):
    with client.application.app_context():
        admin = User.query.filter_by(role="admin").first()
        assert admin is not None
        job = QuestionImportJob(user_id=admin.id, ingest_strategy="classic")
        db.session.add(job)
        db.session.flush()
        draft = QuestionDraft(
            job_id=job.id,
            payload={
                "section": "reading",
                "prompt": "Legacy stem",
                "choices": [
                    {"label": "A", "text": "Alpha"},
                    {"label": "B", "text": "Beta"},
                ],
                "correct_answer": "A",
            },
        )
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    resp = client.post(
        f"/api/admin/questions/drafts/{draft_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    data = resp.get_json()["question"]
    assert data["choices"]["A"] == "Alpha"
    with client.application.app_context():
        assert db.session.get(QuestionDraft, draft_id) is None
        assert Question.query.filter_by(stem_text="Legacy stem").first() is not None


def test_publish_requires_figure_when_flagged(client, admin_token):
    with client.application.app_context():
        admin = User.query.filter_by(role="admin").first()
        assert admin is not None
        job = QuestionImportJob(user_id=admin.id, ingest_strategy="vision_pdf")
        db.session.add(job)
        db.session.flush()
        draft = QuestionDraft(
            job_id=job.id,
            payload={
                "section": "RW",
                "stem_text": "Needs figure",
                "choices": {"A": "Alpha", "B": "Beta"},
                "correct_answer": {"value": "A"},
                "skill_tags": [],
                "has_figure": True,
            },
        )
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    resp = client.post(
        f"/api/admin/questions/drafts/{draft_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400
    assert b"Figure required" in resp.data


def test_publish_moves_uploaded_figure(client, admin_token, tmp_path):
    with client.application.app_context():
        admin = User.query.filter_by(role="admin").first()
        job = QuestionImportJob(user_id=admin.id, ingest_strategy="vision_pdf")
        db.session.add(job)
        db.session.flush()
        draft = QuestionDraft(
            job_id=job.id,
            payload={
                "section": "RW",
                "stem_text": "Has figure",
                "choices": {"A": "Alpha", "B": "Beta"},
                "correct_answer": {"value": "A"},
                "skill_tags": [],
                "has_figure": True,
            },
        )
        db.session.add(draft)
        db.session.flush()
        figure_path = tmp_path / "figure.png"
        figure_path.write_bytes(b"fake-image")
        figure = QuestionFigure(draft_id=draft.id, image_path=str(figure_path))
        db.session.add(figure)
        db.session.commit()
        draft_id = draft.id

    resp = client.post(
        f"/api/admin/questions/drafts/{draft_id}/publish",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 201
    question_id = resp.get_json()["question"]["id"]

    with client.application.app_context():
        figure = QuestionFigure.query.filter_by(question_id=question_id).first()
        assert figure is not None
        assert figure.draft_id is None
        assert figure.question_id == question_id


def test_bulk_delete_questions_endpoint(client, admin_token, app_with_db):
    with app_with_db.app_context():
        question = Question(
            section="RW",
            stem_text="Delete me",
            choices={"A": "Alpha"},
            correct_answer={"value": "A"},
        )
        db.session.add(question)
        db.session.commit()
        question_id = question.id

    resp = client.post(
        "/api/admin/questions/bulk-delete",
        json={"ids": [question_id]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["count"] == 1
    assert question_id in payload["deleted"]
    with app_with_db.app_context():
        assert db.session.get(Question, question_id) is None


def test_delete_source_endpoint(client, admin_token, app_with_db):
    with app_with_db.app_context():
        source = QuestionSource(
            filename="empty.pdf",
            original_name="empty.pdf",
            stored_path="/tmp/empty.pdf",
            uploaded_by=1,
        )
        db.session.add(source)
        db.session.commit()
        source_id = source.id

    resp = client.delete(
        f"/api/admin/sources/{source_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 204
    with app_with_db.app_context():
        assert db.session.get(QuestionSource, source_id) is None


def test_source_deleted_when_questions_removed(client, admin_token):
    with client.application.app_context():
        admin = User.query.filter_by(role="admin").first()
        assert admin is not None
    source = QuestionSource(
        filename="auto-prune.pdf",
        original_name="auto-prune.pdf",
        stored_path="/tmp/auto-prune.pdf",
        uploaded_by=admin.id,
    )
    db.session.add(source)
    db.session.flush()
    job = QuestionImportJob(user_id=admin.id, source_id=source.id, ingest_strategy="vision_pdf")
    db.session.add(job)
    db.session.flush()
    draft = QuestionDraft(
        job_id=job.id,
        source_id=source.id,
        payload={
            "section": "RW",
            "stem_text": "Placeholder stem",
            "choices": {"A": "Alpha"},
            "correct_answer": {"value": "A"},
        },
    )
    db.session.add(draft)
    question = Question(
        source_id=source.id,
        section="RW",
        stem_text="Keep or delete?",
        choices={"A": "Alpha"},
        correct_answer={"value": "A"},
    )
    db.session.add(question)
    db.session.commit()

    target_question = db.session.get(Question, question.id)
    question_service.delete_question(target_question)

    assert db.session.get(QuestionSource, source.id) is not None
    assert QuestionDraft.query.filter_by(source_id=source.id).count() == 1
    job_ref = db.session.get(QuestionImportJob, job.id)
    assert job_ref is not None
    assert job_ref.source_id == source.id

    QuestionDraft.query.filter_by(source_id=source.id).delete()
    db.session.commit()

    question_service.cleanup_source_if_unused(source.id)
    db.session.commit()

    assert db.session.get(QuestionSource, source.id) is None
    job_ref = db.session.get(QuestionImportJob, job.id)
    assert job_ref is not None
    assert job_ref.source_id is None



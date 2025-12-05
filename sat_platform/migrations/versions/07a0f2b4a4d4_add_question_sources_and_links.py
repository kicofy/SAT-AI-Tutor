"""add question sources and link questions to pdf files

Revision ID: 07a0f2b4a4d4
Revises: 5bb2b4f6b8d3
Create Date: 2025-12-04 16:15:00.000000

"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "07a0f2b4a4d4"
down_revision = "5bb2b4f6b8d3"
branch_labels = None
depends_on = None


def _utcnow():
    return datetime.now(timezone.utc)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    table_names = inspector.get_table_names()
    if "question_sources" not in table_names:
        op.create_table(
            "question_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("original_name", sa.String(length=255), nullable=True),
            sa.Column("stored_path", sa.String(length=512), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("total_pages", sa.Integer(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
        )
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("question_sources")} if "question_sources" in table_names else set()
    uploaded_idx = op.f("ix_question_sources_uploaded_by")
    if uploaded_idx not in existing_indexes and "question_sources" in table_names:
        op.create_index(uploaded_idx, "question_sources", ["uploaded_by"])

    job_columns = [col["name"] for col in inspector.get_columns("question_import_jobs")]
    if "source_id" not in job_columns:
        op.add_column("question_import_jobs", sa.Column("source_id", sa.Integer(), nullable=True))
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("question_import_jobs")}
    job_index = op.f("ix_question_import_jobs_source_id")
    if job_index not in existing_indexes:
        op.create_index(job_index, "question_import_jobs", ["source_id"])
    job_fks = {fk["name"] for fk in inspector.get_foreign_keys("question_import_jobs")}
    job_fk_name = op.f("fk_question_import_jobs_source_id_question_sources")
    if job_fk_name not in job_fks and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            job_fk_name,
            "question_import_jobs",
            "question_sources",
            ["source_id"],
            ["id"],
        )

    draft_columns = [col["name"] for col in inspector.get_columns("question_drafts")]
    if "source_id" not in draft_columns:
        op.add_column("question_drafts", sa.Column("source_id", sa.Integer(), nullable=True))
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("question_drafts")}
    draft_index = op.f("ix_question_drafts_source_id")
    if draft_index not in existing_indexes:
        op.create_index(draft_index, "question_drafts", ["source_id"])
    draft_fks = {fk["name"] for fk in inspector.get_foreign_keys("question_drafts")}
    draft_fk_name = op.f("fk_question_drafts_source_id_question_sources")
    if draft_fk_name not in draft_fks and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            draft_fk_name,
            "question_drafts",
            "question_sources",
            ["source_id"],
            ["id"],
        )

    question_columns = [col["name"] for col in inspector.get_columns("questions")]
    if "source_id" not in question_columns:
        op.add_column("questions", sa.Column("source_id", sa.Integer(), nullable=True))
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("questions")}
    question_index = op.f("ix_questions_source_id")
    if question_index not in existing_indexes:
        op.create_index(question_index, "questions", ["source_id"])
    question_fks = {fk["name"] for fk in inspector.get_foreign_keys("questions")}
    question_fk_name = op.f("fk_questions_source_id_question_sources")
    if question_fk_name not in question_fks and bind.dialect.name != "sqlite":
        op.create_foreign_key(
            question_fk_name,
            "questions",
            "question_sources",
            ["source_id"],
            ["id"],
        )

    connection = op.get_bind()
    job_table = sa.table(
        "question_import_jobs",
        sa.column("id", sa.Integer()),
        sa.column("filename", sa.String(length=255)),
        sa.column("source_path", sa.String(length=512)),
        sa.column("user_id", sa.Integer()),
        sa.column("source_id", sa.Integer()),
    )
    source_table = sa.table(
        "question_sources",
        sa.column("id", sa.Integer()),
        sa.column("filename", sa.String(length=255)),
        sa.column("original_name", sa.String(length=255)),
        sa.column("stored_path", sa.String(length=512)),
        sa.column("uploaded_by", sa.Integer()),
        sa.column("total_pages", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    jobs = connection.execute(
        sa.select(
            job_table.c.id,
            job_table.c.filename,
            job_table.c.source_path,
            job_table.c.user_id,
            job_table.c.source_id,
        )
    ).fetchall()
    for job in jobs:
        if job.source_id or not job.source_path:
            continue
        display_name = job.filename or os.path.basename(job.source_path)
        insert = source_table.insert().values(
            filename=display_name,
            original_name=job.filename,
            stored_path=job.source_path,
            uploaded_by=job.user_id or 1,
            total_pages=None,
            created_at=_utcnow(),
        )
        result = connection.execute(insert)
        source_id = None
        pk = getattr(result, "inserted_primary_key", None)
        if pk:
            source_id = pk[0]
        if source_id is None:
            source_id = connection.execute(
                sa.select(sa.func.max(source_table.c.id))
            ).scalar()
        if source_id is None:
            continue
        connection.execute(
            job_table.update().where(job_table.c.id == job.id).values(source_id=source_id)
        )

    draft_table = sa.table(
        "question_drafts",
        sa.column("id", sa.Integer()),
        sa.column("job_id", sa.Integer()),
        sa.column("source_id", sa.Integer()),
    )
    draft_columns = [col["name"] for col in inspector.get_columns("question_drafts")]
    if "source_id" in draft_columns:
        connection.execute(
            draft_table.update().values(
                source_id=sa.select(job_table.c.source_id)
                .where(job_table.c.id == draft_table.c.job_id)
                .scalar_subquery()
            )
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    question_fks = {fk["name"] for fk in inspector.get_foreign_keys("questions")}
    question_index_names = {idx["name"] for idx in inspector.get_indexes("questions")}
    question_columns = [col["name"] for col in inspector.get_columns("questions")]
    if bind.dialect.name != "sqlite" and op.f("fk_questions_source_id_question_sources") in question_fks:
        op.drop_constraint(op.f("fk_questions_source_id_question_sources"), "questions", type_="foreignkey")
    if op.f("ix_questions_source_id") in question_index_names:
        op.drop_index(op.f("ix_questions_source_id"), table_name="questions")
    if "source_id" in question_columns:
        op.drop_column("questions", "source_id")

    draft_fks = {fk["name"] for fk in inspector.get_foreign_keys("question_drafts")}
    draft_index_names = {idx["name"] for idx in inspector.get_indexes("question_drafts")}
    draft_columns = [col["name"] for col in inspector.get_columns("question_drafts")]
    if bind.dialect.name != "sqlite" and op.f("fk_question_drafts_source_id_question_sources") in draft_fks:
        op.drop_constraint(op.f("fk_question_drafts_source_id_question_sources"), "question_drafts", type_="foreignkey")
    if op.f("ix_question_drafts_source_id") in draft_index_names:
        op.drop_index(op.f("ix_question_drafts_source_id"), table_name="question_drafts")
    if "source_id" in draft_columns:
        op.drop_column("question_drafts", "source_id")

    job_fks = {fk["name"] for fk in inspector.get_foreign_keys("question_import_jobs")}
    job_index_names = {idx["name"] for idx in inspector.get_indexes("question_import_jobs")}
    job_columns = [col["name"] for col in inspector.get_columns("question_import_jobs")]
    if bind.dialect.name != "sqlite" and op.f("fk_question_import_jobs_source_id_question_sources") in job_fks:
        op.drop_constraint(op.f("fk_question_import_jobs_source_id_question_sources"), "question_import_jobs", type_="foreignkey")
    if op.f("ix_question_import_jobs_source_id") in job_index_names:
        op.drop_index(op.f("ix_question_import_jobs_source_id"), table_name="question_import_jobs")
    if "source_id" in job_columns:
        op.drop_column("question_import_jobs", "source_id")

    table_names = inspector.get_table_names()
    if op.f("ix_question_sources_uploaded_by") in (
        {idx["name"] for idx in inspector.get_indexes("question_sources")} if "question_sources" in table_names else set()
    ):
        op.drop_index(op.f("ix_question_sources_uploaded_by"), table_name="question_sources")
    if "question_sources" in table_names:
        op.drop_table("question_sources")


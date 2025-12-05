"""add stable question uid column

Revision ID: f0b6b0c0a1c7
Revises: e5c95a00f3a6
Create Date: 2025-12-04 13:30:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f0b6b0c0a1c7"
down_revision = "e5c95a00f3a6"
branch_labels = None
depends_on = None


def _ensure_column():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns("questions")]
    if "question_uid" in columns:
        return
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("question_uid", sa.String(length=32), nullable=True))


def _populate_existing_rows():
    bind = op.get_bind()
    questions = sa.table(
        "questions",
        sa.column("id", sa.Integer),
        sa.column("question_uid", sa.String(length=32)),
    )
    rows = bind.execute(sa.select(questions.c.id, questions.c.question_uid)).fetchall()
    existing = {row.question_uid for row in rows if row.question_uid}
    for row in rows:
        if row.question_uid:
            continue
        base_uid = f"Q{row.id:06d}"
        candidate = base_uid
        suffix = 1
        while candidate in existing:
            candidate = f"{base_uid}-{suffix}"
            suffix += 1
        bind.execute(
            sa.text("UPDATE questions SET question_uid = :uid WHERE id = :id"),
            {"uid": candidate, "id": row.id},
        )
        existing.add(candidate)


def upgrade():
    _ensure_column()
    _populate_existing_rows()
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    with op.batch_alter_table("questions") as batch_op:
        batch_op.alter_column("question_uid", existing_type=sa.String(length=32), nullable=False)
        existing_uniques = {uc["name"] for uc in inspector.get_unique_constraints("questions")}
        if "uq_questions_question_uid" not in existing_uniques:
            batch_op.create_unique_constraint("uq_questions_question_uid", ["question_uid"])

    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("questions")}
    if "ix_questions_question_uid" not in existing_indexes:
        op.create_index("ix_questions_question_uid", "questions", ["question_uid"], unique=False)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("questions")}
    if "ix_questions_question_uid" in existing_indexes:
        op.drop_index("ix_questions_question_uid", table_name="questions")

    inspector = sa.inspect(bind)
    unique_constraints = {uc["name"] for uc in inspector.get_unique_constraints("questions")}
    with op.batch_alter_table("questions") as batch_op:
        if "uq_questions_question_uid" in unique_constraints:
            batch_op.drop_constraint("uq_questions_question_uid", type_="unique")
        columns = [col["name"] for col in inspector.get_columns("questions")]
        if "question_uid" in columns:
            batch_op.drop_column("question_uid")



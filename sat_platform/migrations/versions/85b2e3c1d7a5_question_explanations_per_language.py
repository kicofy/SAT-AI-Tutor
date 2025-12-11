"""Normalize question explanations per language

Revision ID: 85b2e3c1d7a5
Revises: 7f8a4d4f9f2d
Create Date: 2025-12-07 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "85b2e3c1d7a5"
down_revision = "7f8a4d4f9f2d"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            DELETE FROM question_explanations a
            USING question_explanations b
            WHERE a.id < b.id
              AND a.question_id = b.question_id
              AND a.language = b.language
            """
        )
    )
    op.drop_constraint(
        "uq_question_explanations_question_language_answer",
        "question_explanations",
        type_="unique",
    )
    with op.batch_alter_table("question_explanations") as batch_op:
        batch_op.drop_column("answer_value")
        batch_op.add_column(sa.Column("source", sa.String(length=32), nullable=True))
        batch_op.create_unique_constraint(
            "uq_question_explanations_question_language", ["question_id", "language"]
        )
    conn.execute(
        sa.text(
            "UPDATE question_explanations SET source = COALESCE(source, 'legacy')"
        )
    )


def downgrade():
    op.drop_constraint(
        "uq_question_explanations_question_language",
        "question_explanations",
        type_="unique",
    )
    with op.batch_alter_table("question_explanations") as batch_op:
        batch_op.drop_column("source")
        batch_op.add_column(sa.Column("answer_value", sa.String(length=32), nullable=True))
        batch_op.create_unique_constraint(
            "uq_question_explanations_question_language_answer",
            ["question_id", "language", "answer_value"],
        )


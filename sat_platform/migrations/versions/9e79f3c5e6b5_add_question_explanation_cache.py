"""add question explanation cache table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9e79f3c5e6b5"
down_revision = "5f1f2c6fd5f3"
branch_labels = None
depends_on = None


def upgrade():
    question_explanations = op.create_table(
        "question_explanations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("answer_value", sa.String(length=32), nullable=True),
        sa.Column("explanation", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("(datetime('now'))")),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_id",
            "language",
            "answer_value",
            name="uq_question_explanations_question_language_answer",
        ),
    )
    op.create_index(op.f("ix_question_explanations_question_id"), "question_explanations", ["question_id"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_question_explanations_question_id"), table_name="question_explanations")
    op.drop_table("question_explanations")


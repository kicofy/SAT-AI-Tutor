"""add question figures table and has_figure flag"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "2b6b8f4f3c4a"
down_revision = "9e79f3c5e6b5"
branch_labels = None
depends_on = None


def _ensure_column(table_name: str, column: sa.Column) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column.name not in existing:
        op.add_column(table_name, column)


def upgrade():
    _ensure_column(
        "question_drafts",
        sa.Column("has_figure", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )
    _ensure_column(
        "questions",
        sa.Column("has_figure", sa.Boolean(), server_default=sa.text("0"), nullable=False),
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "question_figures" in inspector.get_table_names():
        op.drop_table("question_figures")

    op.create_table(
        "question_figures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("questions.id"), nullable=True),
        sa.Column("draft_id", sa.Integer(), sa.ForeignKey("question_drafts.id"), nullable=True),
        sa.Column("image_path", sa.String(length=512), nullable=False),
        sa.Column("description", sa.String(length=255)),
        sa.Column("bbox", sa.JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_table("question_figures")
    op.drop_column("questions", "has_figure")
    op.drop_column("question_drafts", "has_figure")


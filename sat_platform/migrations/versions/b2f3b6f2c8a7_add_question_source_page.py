"""add question.source_page

Revision ID: b2f3b6f2c8a7
Revises: ab12d5c1f0b4
Create Date: 2025-12-06 15:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b2f3b6f2c8a7"
down_revision = "ab12d5c1f0b4"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "source_page" not in {col["name"] for col in inspector.get_columns("questions")}:
        op.add_column("questions", sa.Column("source_page", sa.Integer(), nullable=True))
        # best-effort backfill from legacy "page" column when it's a simple integer
        dialect = bind.dialect.name
        if dialect == "sqlite":
            bind.execute(
                sa.text(
                    "UPDATE questions SET source_page = CAST(page AS INTEGER) "
                    "WHERE page IS NOT NULL AND TRIM(page) != '' "
                    "AND page GLOB '[0-9]*'"
                )
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE questions SET source_page = CAST(page AS INTEGER) "
                    "WHERE page IS NOT NULL AND page ~ '^[0-9]+$'"
                )
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "source_page" in {col["name"] for col in inspector.get_columns("questions")}:
        op.drop_column("questions", "source_page")


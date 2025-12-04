"""add status message and heartbeat fields to question import jobs"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a4cbdc0c9fd7"
down_revision = "2b6b8f4f3c4a"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("question_import_jobs")}

    if "current_page" not in existing:
        op.add_column(
            "question_import_jobs",
            sa.Column("current_page", sa.Integer(), server_default="0", nullable=False),
        )
    if "status_message" not in existing:
        op.add_column(
            "question_import_jobs",
            sa.Column("status_message", sa.Text(), nullable=True),
        )
    if "last_progress_at" not in existing:
        op.add_column(
            "question_import_jobs",
            sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
        )
        bind.execute(sa.text("UPDATE question_import_jobs SET last_progress_at = CURRENT_TIMESTAMP"))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {col["name"] for col in inspector.get_columns("question_import_jobs")}

    if "last_progress_at" in existing:
        op.drop_column("question_import_jobs", "last_progress_at")
    if "status_message" in existing:
        op.drop_column("question_import_jobs", "status_message")
    if "current_page" in existing:
        op.drop_column("question_import_jobs", "current_page")


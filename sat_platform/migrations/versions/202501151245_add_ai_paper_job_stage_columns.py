"""add stage fields to ai paper jobs

Revision ID: 7a3e9b2d1c45
Revises: 3f8f6a1b9f23
Create Date: 2025-01-15 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7a3e9b2d1c45"
down_revision = "3f8f6a1b9f23"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_paper_jobs", sa.Column("stage", sa.String(length=64), nullable=False, server_default="pending"))
    op.add_column("ai_paper_jobs", sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ai_paper_jobs", sa.Column("status_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_paper_jobs", "status_message")
    op.drop_column("ai_paper_jobs", "stage_index")
    op.drop_column("ai_paper_jobs", "stage")


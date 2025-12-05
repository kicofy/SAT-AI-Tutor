"""add coach notes table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "1f2a9b7d6d3d"
down_revision = "5bb2b4f6b8d3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coach_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "plan_date", name="uq_coach_note_user_date"),
    )
    op.create_index(op.f("ix_coach_notes_plan_date"), "coach_notes", ["plan_date"])
    op.create_index(op.f("ix_coach_notes_user_id"), "coach_notes", ["user_id"])


def downgrade():
    op.drop_index(op.f("ix_coach_notes_user_id"), table_name="coach_notes")
    op.drop_index(op.f("ix_coach_notes_plan_date"), table_name="coach_notes")
    op.drop_table("coach_notes")


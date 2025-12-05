"""add study plan tasks and plan block linkage

Revision ID: e5c95a00f3a6
Revises: 5f1f2c6fd5f3
Create Date: 2025-12-04 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5c95a00f3a6'
down_revision = '5f1f2c6fd5f3'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    session_columns = [col["name"] for col in inspector.get_columns("study_sessions")]
    if "plan_block_id" not in session_columns:
        op.add_column(
            "study_sessions",
            sa.Column("plan_block_id", sa.String(length=128), nullable=True),
        )
        op.create_index(
            op.f("ix_study_sessions_plan_block_id"),
            "study_sessions",
            ["plan_block_id"],
            unique=False,
        )

    if "study_plan_tasks" not in inspector.get_table_names():
        op.create_table(
            "study_plan_tasks",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("plan_date", sa.Date(), nullable=False),
            sa.Column("block_id", sa.String(length=128), nullable=False),
            sa.Column("section", sa.String(length=32), nullable=False),
            sa.Column("focus_skill", sa.String(length=128)),
            sa.Column("questions_target", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("session_id", sa.Integer(), sa.ForeignKey("study_sessions.id")),
            sa.Column("started_at", sa.DateTime(timezone=True)),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
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
            sa.UniqueConstraint("user_id", "plan_date", "block_id", name="uq_plan_task_block"),
        )
        op.create_index(
            "ix_study_plan_tasks_user_date",
            "study_plan_tasks",
            ["user_id", "plan_date"],
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "study_plan_tasks" in inspector.get_table_names():
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("study_plan_tasks")}
        if "ix_study_plan_tasks_user_date" in existing_indexes:
            op.drop_index("ix_study_plan_tasks_user_date", table_name="study_plan_tasks")
        op.drop_table("study_plan_tasks")

    session_columns = [col["name"] for col in inspector.get_columns("study_sessions")]
    if "plan_block_id" in session_columns:
        existing_session_indexes = {
            idx["name"] for idx in inspector.get_indexes("study_sessions")
        }
        if op.f("ix_study_sessions_plan_block_id") in existing_session_indexes:
            op.drop_index(op.f("ix_study_sessions_plan_block_id"), table_name="study_sessions")
        op.drop_column("study_sessions", "plan_block_id")


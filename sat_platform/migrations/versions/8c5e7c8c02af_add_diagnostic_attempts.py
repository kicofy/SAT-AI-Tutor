"""add diagnostic attempts and session metadata

Revision ID: 8c5e7c8c02af
Revises: 07a0f2b4a4d4
Create Date: 2025-12-05 11:15:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8c5e7c8c02af"
down_revision = "07a0f2b4a4d4"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in [col["name"] for col in inspector.get_columns(table_name)]


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    dialect = bind.dialect.name

    if not _has_table(inspector, "diagnostic_attempts"):
        op.create_table(
            "diagnostic_attempts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "started_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True)),
            sa.Column("result_summary", sa.JSON(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
        )
        op.create_index(
            "ix_diagnostic_attempts_user_status",
            "diagnostic_attempts",
            ["user_id", "status"],
            unique=False,
        )

    if _has_table(inspector, "study_sessions"):
        if not _has_column(inspector, "study_sessions", "session_type"):
            op.add_column(
                "study_sessions",
                sa.Column(
                    "session_type",
                    sa.String(length=32),
                    nullable=False,
                    server_default="practice",
                ),
            )
        if not _has_column(inspector, "study_sessions", "diagnostic_attempt_id"):
            column = sa.Column(
                "diagnostic_attempt_id",
                sa.Integer(),
                nullable=True,
            )
            if dialect != "sqlite":
                column = sa.Column(
                    "diagnostic_attempt_id",
                    sa.Integer(),
                    sa.ForeignKey("diagnostic_attempts.id"),
                    nullable=True,
                )
            op.add_column("study_sessions", column)
        if not _has_index(
            inspector, "study_sessions", "ix_study_sessions_diagnostic_attempt_id"
        ):
            op.create_index(
                "ix_study_sessions_diagnostic_attempt_id",
                "study_sessions",
                ["diagnostic_attempt_id"],
                unique=False,
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_index(inspector, "study_sessions", "ix_study_sessions_diagnostic_attempt_id"):
        op.drop_index("ix_study_sessions_diagnostic_attempt_id", table_name="study_sessions")
    if _has_column(inspector, "study_sessions", "diagnostic_attempt_id"):
        op.drop_column("study_sessions", "diagnostic_attempt_id")
    if _has_column(inspector, "study_sessions", "session_type"):
        op.drop_column("study_sessions", "session_type")

    if _has_table(inspector, "diagnostic_attempts"):
        if _has_index(inspector, "diagnostic_attempts", "ix_diagnostic_attempts_user_status"):
            op.drop_index(
                "ix_diagnostic_attempts_user_status", table_name="diagnostic_attempts"
            )
        op.drop_table("diagnostic_attempts")


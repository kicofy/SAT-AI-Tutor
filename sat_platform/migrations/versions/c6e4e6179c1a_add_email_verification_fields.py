"""add email verification fields to users

Revision ID: c6e4e6179c1a
Revises: 8c5e7c8c02af
Create Date: 2025-12-06 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "c6e4e6179c1a"
down_revision = "8c5e7c8c02af"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in [col["name"] for col in inspector.get_columns(table_name)]


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "users"):
        return

    def add_column(name: str, column: sa.Column):
        if not _has_column(inspector, "users", name):
            op.add_column("users", column)

    add_column(
        "is_email_verified",
        sa.Column("is_email_verified", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    add_column(
        "email_verification_code",
        sa.Column("email_verification_code", sa.String(length=12)),
    )
    add_column(
        "email_verification_expires_at",
        sa.Column("email_verification_expires_at", sa.DateTime(timezone=True)),
    )
    add_column(
        "email_verification_attempts",
        sa.Column(
            "email_verification_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    add_column(
        "email_verification_sent_at",
        sa.Column("email_verification_sent_at", sa.DateTime(timezone=True)),
    )
    add_column(
        "email_verification_sent_count",
        sa.Column(
            "email_verification_sent_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    add_column(
        "email_verification_sent_window_start",
        sa.Column("email_verification_sent_window_start", sa.DateTime(timezone=True)),
    )

    # remove server defaults now that existing rows are initialized (skip on SQLite)
    if bind.dialect.name != "sqlite":
        op.alter_column("users", "is_email_verified", server_default=None)
        op.alter_column("users", "email_verification_attempts", server_default=None)
        op.alter_column("users", "email_verification_sent_count", server_default=None)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "users"):
        return

    for column in [
        "email_verification_sent_window_start",
        "email_verification_sent_count",
        "email_verification_sent_at",
        "email_verification_attempts",
        "email_verification_expires_at",
        "email_verification_code",
        "is_email_verified",
    ]:
        if _has_column(inspector, "users", column):
            op.drop_column("users", column)


"""add user status fields

Revision ID: ab12d5c1f0b4
Revises: d3f1a6b2c851
Create Date: 2025-12-06 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "ab12d5c1f0b4"
down_revision = "d3f1a6b2c851"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_column(inspector, "users", "is_active"):
        op.add_column(
            "users",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        )
        op.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        op.alter_column("users", "is_active", server_default=None)

    if not _has_column(inspector, "users", "locked_reason"):
        op.add_column("users", sa.Column("locked_reason", sa.String(length=255), nullable=True))

    if not _has_column(inspector, "users", "locked_at"):
        op.add_column(
            "users",
            sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_column(inspector, "users", "locked_at"):
        op.drop_column("users", "locked_at")

    if _has_column(inspector, "users", "locked_reason"):
        op.drop_column("users", "locked_reason")

    if _has_column(inspector, "users", "is_active"):
        op.drop_column("users", "is_active")


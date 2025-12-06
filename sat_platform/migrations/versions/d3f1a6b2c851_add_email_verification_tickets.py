"""add email verification tickets

Revision ID: d3f1a6b2c851
Revises: c6e4e6179c1a
Create Date: 2025-12-06 13:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "d3f1a6b2c851"
down_revision = "c6e4e6179c1a"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_verification_tickets" in inspector.get_table_names():
        return
    op.create_table(
        "email_verification_tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=12), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
        sa.Column("resend_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_email_verification_tickets_email",
        "email_verification_tickets",
        ["email"],
        unique=True,
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_verification_tickets" in inspector.get_table_names():
        op.drop_index(
            "ix_email_verification_tickets_email",
            table_name="email_verification_tickets",
        )
        op.drop_table("email_verification_tickets")


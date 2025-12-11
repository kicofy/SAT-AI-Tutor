"""add membership orders table

Revision ID: 7f8a4d4f9f2d
Revises: 4de1a3f2e58c
Create Date: 2025-12-07 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7f8a4d4f9f2d"
down_revision = "4de1a3f2e58c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "membership_orders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("user_note", sa.String(length=255)),
        sa.Column("admin_note", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.Integer()),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_membership_orders_user_id"), "membership_orders", ["user_id"])


def downgrade():
    op.drop_index(op.f("ix_membership_orders_user_id"), table_name="membership_orders")
    op.drop_table("membership_orders")


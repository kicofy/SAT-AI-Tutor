"""add membership tracking fields

Revision ID: 4de1a3f2e58c
Revises: bb93ef90bf8f
Create Date: 2025-12-07 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4de1a3f2e58c"
down_revision = "bb93ef90bf8f"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("membership_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("ai_explain_quota_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("ai_explain_quota_used", sa.Integer(), nullable=False, server_default="0")
        )

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("ai_explain_quota_used", server_default=None)

    op.create_table(
        "user_subscription_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("delta_days", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        op.f("ix_user_subscription_logs_user_id"),
        "user_subscription_logs",
        ["user_id"],
        unique=False,
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE users SET membership_expires_at = '2099-12-31T00:00:00Z' "
            "WHERE role = 'admin' AND membership_expires_at IS NULL"
        )
    )


def downgrade():
    op.drop_index(op.f("ix_user_subscription_logs_user_id"), table_name="user_subscription_logs")
    op.drop_table("user_subscription_logs")
    with op.batch_alter_table("users") as batch_op:
        for column in ("membership_expires_at", "ai_explain_quota_date", "ai_explain_quota_used"):
            batch_op.drop_column(column)


"""add general settings table"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "5d3b89f0a2de"
down_revision = "121dc0b3b0d8"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "general_settings" in inspector.get_table_names():
        return
    op.create_table(
        "general_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "general_settings" in inspector.get_table_names():
        op.drop_table("general_settings")


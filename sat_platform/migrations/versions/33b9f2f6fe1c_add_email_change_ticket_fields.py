"""add email change ticket fields

Revision ID: 33b9f2f6fe1c
Revises: 121dc0b3b0d8
Create Date: 2025-12-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "33b9f2f6fe1c"
down_revision = "121dc0b3b0d8"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table = "email_verification_tickets"
    if table not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns(table)}
    if "purpose" not in columns:
        op.add_column(
            table,
            sa.Column("purpose", sa.String(length=32), nullable=False, server_default="signup"),
        )
        if bind.dialect.name != "sqlite":
            op.alter_column(table, "purpose", server_default=None)

    if "user_id" not in columns:
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        if bind.dialect.name != "sqlite":
            fk_name = "fk_email_verification_tickets_user_id"
            existing_fks = [fk["name"] for fk in inspector.get_foreign_keys(table)]
            if fk_name not in existing_fks:
                op.create_foreign_key(
                    fk_name,
                    table,
                    "users",
                    ["user_id"],
                    ["id"],
                    ondelete="CASCADE",
                )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table = "email_verification_tickets"
    if table not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns(table)}
    if "user_id" in columns:
        if bind.dialect.name != "sqlite":
            fk_name = "fk_email_verification_tickets_user_id"
            constraints = [fk["name"] for fk in inspector.get_foreign_keys(table)]
            if fk_name in constraints:
                op.drop_constraint(fk_name, table, type_="foreignkey")
        op.drop_column(table, "user_id")

    if "purpose" in columns:
        op.drop_column(table, "purpose")


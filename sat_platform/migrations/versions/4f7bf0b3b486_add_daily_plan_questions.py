"""add daily plan question preference

Revision ID: 4f7bf0b3b486
Revises: 121dc0b3b0d8
Create Date: 2025-12-07 06:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "4f7bf0b3b486"
down_revision = "121dc0b3b0d8"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.add_column(sa.Column("daily_plan_questions", sa.Integer(), nullable=True))

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE user_profiles SET daily_plan_questions = 12 WHERE daily_plan_questions IS NULL"
        )
    )

    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.alter_column(
            "daily_plan_questions",
            existing_type=sa.Integer(),
            nullable=False,
            server_default="12",
        )


def downgrade():
    with op.batch_alter_table("user_profiles") as batch_op:
        batch_op.drop_column("daily_plan_questions")


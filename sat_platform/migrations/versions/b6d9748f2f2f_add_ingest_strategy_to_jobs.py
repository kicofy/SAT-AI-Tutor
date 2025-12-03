"""add ingest strategy column to question import jobs

Revision ID: b6d9748f2f2f
Revises: d9bfbb294685
Create Date: 2025-12-03 13:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6d9748f2f2f'
down_revision = 'd9bfbb294685'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ingest_strategy', sa.String(length=32), nullable=False, server_default='classic'))

    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.alter_column('ingest_strategy', server_default=None)


def downgrade():
    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.drop_column('ingest_strategy')



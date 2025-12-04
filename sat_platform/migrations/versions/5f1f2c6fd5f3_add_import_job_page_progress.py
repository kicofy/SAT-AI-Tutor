"""add page progress tracking to question import jobs

Revision ID: 5f1f2c6fd5f3
Revises: b6d9748f2f2f
Create Date: 2025-12-03 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5f1f2c6fd5f3'
down_revision = 'b6d9748f2f2f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('processed_pages', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('total_pages', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.alter_column('processed_pages', server_default=None)
        batch_op.alter_column('total_pages', server_default=None)


def downgrade():
    with op.batch_alter_table('question_import_jobs', schema=None) as batch_op:
        batch_op.drop_column('total_pages')
        batch_op.drop_column('processed_pages')



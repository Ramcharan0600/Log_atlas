"""uploaded_files.column_map (user-defined CSV column -> log field mapping)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('uploaded_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('column_map', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('uploaded_files', schema=None) as batch_op:
        batch_op.drop_column('column_map')

"""add approval_stage_histories table and composite indices

Revision ID: 001
Revises: None
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # 1. 创建审批阶段历史表
    op.create_table(
        'approval_stage_histories',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('record_id', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['record_id'], ['approval_records.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_stage_history_record', 'approval_stage_histories',
                    ['record_id'])

    # 2. 为 approval_records 添加复合索引
    op.create_index('idx_record_user_type_status', 'approval_records',
                    ['user_id', 'document_type', 'status'])
    op.create_index('idx_record_status_stage', 'approval_records',
                    ['status', 'current_stage'])


def downgrade():
    op.drop_index('idx_record_status_stage', table_name='approval_records')
    op.drop_index('idx_record_user_type_status', table_name='approval_records')
    op.drop_index('idx_stage_history_record', table_name='approval_stage_histories')
    op.drop_table('approval_stage_histories')

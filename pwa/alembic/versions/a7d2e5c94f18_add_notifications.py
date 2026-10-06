"""in-portal notifications (the bell)

Revision ID: a7d2e5c94f18
Revises: f1c4d8e27b93
Create Date: 2026-10-06

One row per message per customer. (user_id, dedupe_key) is unique so the
hourly reminders cannot repeat; Postgres treats NULL keys as distinct, so
messages without a key are unaffected.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d2e5c94f18'
down_revision: Union[str, Sequence[str], None] = 'f1c4d8e27b93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body', sa.String(length=1000), nullable=False, server_default=''),
        sa.Column('link', sa.String(length=32), nullable=True),
        sa.Column('dedupe_key', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('user_id', 'dedupe_key', name='uq_notifications_user_dedupe'),
    )
    op.create_index('ix_notifications_user_id', 'notifications', ['user_id'])
    op.create_index('ix_notifications_created_at', 'notifications', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_notifications_created_at', table_name='notifications')
    op.drop_index('ix_notifications_user_id', table_name='notifications')
    op.drop_table('notifications')

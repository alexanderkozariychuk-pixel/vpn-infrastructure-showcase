"""Telegram bot: a customer's chat on the account, and support threads

Revision ID: c8e4d1a92b37
Revises: f3a9c2e71d58
Create Date: 2026-10-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c8e4d1a92b37'
down_revision: Union[str, Sequence[str], None] = 'f3a9c2e71d58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.add_column('users', sa.Column('telegram_link_hash', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('telegram_link_expires', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint('uq_users_telegram_id', 'users', ['telegram_id'])
    op.create_table(
        'telegram_support',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('admin_message_id', sa.BigInteger(), nullable=False),
        sa.Column('user_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('admin_message_id', name='uq_telegram_support_admin_message'),
    )


def downgrade() -> None:
    op.drop_table('telegram_support')
    op.drop_constraint('uq_users_telegram_id', 'users', type_='unique')
    op.drop_column('users', 'telegram_link_expires')
    op.drop_column('users', 'telegram_link_hash')
    op.drop_column('users', 'telegram_id')

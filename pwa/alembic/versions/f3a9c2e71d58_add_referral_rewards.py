"""referral rewards in days: a paying friend adds a month to the referrer

Revision ID: f3a9c2e71d58
Revises: a7d3e9f15c42
Create Date: 2026-10-26

The referral reward was 175 points, and only for a purchase longer than a
month — so the usual first purchase, one month to try, earned nothing. Since
2026-10-26 every paid purchase through a referral code adds 30 days to the
referrer's subscription once it vests. Points already earned stay in
credit_entries and keep working; nothing is migrated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3a9c2e71d58'
down_revision: Union[str, Sequence[str], None] = 'a7d3e9f15c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'referral_rewards',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('referrer_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source_payment_id', sa.String(), sa.ForeignKey('payments.id'), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('vests_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_payment_id', name='uq_referral_reward_source'),
    )
    op.create_index('ix_referral_rewards_referrer_user_id', 'referral_rewards', ['referrer_user_id'])


def downgrade() -> None:
    op.drop_index('ix_referral_rewards_referrer_user_id', table_name='referral_rewards')
    op.drop_table('referral_rewards')

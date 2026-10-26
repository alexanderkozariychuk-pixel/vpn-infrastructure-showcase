"""accounts from Telegram: email optional, one trial per Telegram account

Revision ID: d2f7a6b04c19
Revises: c8e4d1a92b37
Create Date: 2026-10-26

A customer can now start from the bot: an account created inside Telegram
has no mailbox, and the Telegram account (which needs a phone number) is
what a trial is counted against, as the confirmed mailbox is for the rest.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2f7a6b04c19'
down_revision: Union[str, Sequence[str], None] = 'c8e4d1a92b37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=True)
    op.alter_column('trial_grants', 'email_norm', existing_type=sa.String(length=255), nullable=True)
    op.add_column('trial_grants', sa.Column('telegram_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_trial_grants_telegram_id', 'trial_grants', ['telegram_id'])


def downgrade() -> None:
    op.drop_constraint('uq_trial_grants_telegram_id', 'trial_grants', type_='unique')
    op.drop_column('trial_grants', 'telegram_id')
    # Fails while Telegram-only accounts or grants exist — on purpose.
    op.alter_column('trial_grants', 'email_norm', existing_type=sa.String(length=255), nullable=False)
    op.alter_column('users', 'email', existing_type=sa.String(length=255), nullable=False)

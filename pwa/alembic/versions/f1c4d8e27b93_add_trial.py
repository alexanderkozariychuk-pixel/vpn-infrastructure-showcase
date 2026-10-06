"""free trial: end date per user, device kind, one grant per mailbox

Revision ID: f1c4d8e27b93
Revises: e6b3f0a1c752
Create Date: 2026-10-06

The network side is already on the entry node: trial peers get addresses in
10.88.89.0/24, under a shared bandwidth ceiling and a kill switch
(infrastructure/trial). This is the portal's half.

- users.trial_until — set once when a trial is granted; a past date means
  the trial was used.
- configs.kind — "paid" or "trial". Existing rows are paid.
- trial_grants — one row per normalised mailbox, unique, kept after the
  trial ends and after the account is deleted, so the same inbox does not
  get a second trial.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1c4d8e27b93'
down_revision: Union[str, Sequence[str], None] = 'e6b3f0a1c752'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('trial_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('configs', sa.Column('kind', sa.String(length=8), nullable=False, server_default='paid'))
    op.create_table(
        'trial_grants',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('email_norm', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_ip', sa.String(length=64), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('email_norm', name='uq_trial_grants_email_norm'),
        sa.UniqueConstraint('user_id', name='uq_trial_grants_user_id'),
    )


def downgrade() -> None:
    op.drop_table('trial_grants')
    op.drop_column('configs', 'kind')
    op.drop_column('users', 'trial_until')

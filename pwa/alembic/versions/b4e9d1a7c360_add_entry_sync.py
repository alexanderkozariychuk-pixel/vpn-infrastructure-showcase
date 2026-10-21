"""entry sync: changes owed to the standby entry

Revision ID: b4e9d1a7c360
Revises: e2a7c5d91f04
Create Date: 2026-10-21

Stage 4 of the standby cluster: every portal peer added to or removed from
entry A is also owed to entry B. Those changes wait here until
pwa/entry_sync.py (cron) has made them on B. With ENTRY_B_IP unset no row is
ever written, and the portal behaves as before.

The way back: downgrade drops the table. Nothing else reads it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4e9d1a7c360'
down_revision: Union[str, Sequence[str], None] = 'e2a7c5d91f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'entry_sync',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('entry', sa.String(length=8), nullable=False),
        sa.Column('action', sa.String(length=8), nullable=False),
        sa.Column('config_id', sa.String(), sa.ForeignKey('configs.id'), nullable=False),
        sa.Column('public_key', sa.String(length=64), nullable=False),
        sa.Column('peer_ip', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('done_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_entry_sync_config_id', 'entry_sync', ['config_id'])
    op.create_index('ix_entry_sync_done_at', 'entry_sync', ['done_at'])


def downgrade() -> None:
    op.drop_index('ix_entry_sync_done_at', table_name='entry_sync')
    op.drop_index('ix_entry_sync_config_id', table_name='entry_sync')
    op.drop_table('entry_sync')

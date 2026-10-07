"""the monitor's latest report and its history of problems

Revision ID: d8a4c2f6b913
Revises: c6f1a9d3e204
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd8a4c2f6b913'
down_revision: Union[str, Sequence[str], None] = 'c6f1a9d3e204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'monitor_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
    )
    op.create_table(
        'monitor_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(length=120), nullable=False),
        sa.Column('level', sa.String(length=8), nullable=False),
        sa.Column('text', sa.String(length=300), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_monitor_events_key', 'monitor_events', ['key'])
    op.create_index('ix_monitor_events_started_at', 'monitor_events', ['started_at'])


def downgrade() -> None:
    op.drop_table('monitor_events')
    op.drop_table('monitor_reports')

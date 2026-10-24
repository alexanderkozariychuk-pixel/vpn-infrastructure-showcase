"""app sessions: the Android client's long-lived sign-in

Revision ID: e2a7c5d91f04
Revises: d8a4c2f6b913
Create Date: 2026-10-19

The app trades a refresh token for a new day-long access token instead of
asking the customer to sign in every day. Only the token's SHA-256 is kept.
Rows go with the account (CASCADE), on a password reset, and on sign-out
from the app.

The way back: downgrade drops the table; every app then signs in once more
when its access token runs out.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e2a7c5d91f04'
down_revision: Union[str, Sequence[str], None] = 'd8a4c2f6b913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_sessions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('token_hash', name='uq_app_sessions_token_hash'),
    )
    op.create_index('ix_app_sessions_user_id', 'app_sessions', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_app_sessions_user_id', table_name='app_sessions')
    op.drop_table('app_sessions')

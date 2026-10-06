"""operator's names for peers the portal did not issue

Revision ID: b3e8c1d07a52
Revises: a7d2e5c94f18
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3e8c1d07a52'
down_revision: Union[str, Sequence[str], None] = 'a7d2e5c94f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'peer_labels',
        sa.Column('public_key', sa.String(length=64), primary_key=True),
        sa.Column('label', sa.String(length=60), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('peer_labels')

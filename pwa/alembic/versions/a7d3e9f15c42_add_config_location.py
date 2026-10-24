"""device location: which entry a device's peer lives on

Revision ID: a7d3e9f15c42
Revises: e2a7c5d91f04
Create Date: 2026-10-24

Two independent chains since 2026-10-24 (services/locations.py): "de" is
entry A, the only one there was, so every existing row is "de"; "nl" is
entry B with its own exit. A device keeps its location for life.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7d3e9f15c42'
down_revision: Union[str, Sequence[str], None] = 'e2a7c5d91f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('configs', sa.Column('location', sa.String(length=8), nullable=False, server_default='de'))


def downgrade() -> None:
    op.drop_column('configs', 'location')

"""the referral code an account was registered through

Revision ID: c6f1a9d3e204
Revises: b3e8c1d07a52
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6f1a9d3e204'
down_revision: Union[str, Sequence[str], None] = 'b3e8c1d07a52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('referred_code', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'referred_code')

"""drop the promo code uses counter, add a campaign note

Revision ID: c3e8a1f70b42
Revises: b7c1d9e42a10
Create Date: 2026-09-22

`promo_codes.uses` was a counter incremented inside the referral reward, which
returns early for a code with no owner. A campaign code's counter therefore
never moved and its `max_uses` limit could never take effect — the one thing
the column existed for. Uses are now counted from paid payments carrying the
code, which cannot fall out of step and cannot be double-counted by a retried
webhook.

`note` is for the operator: which blogger, which mailing, which month. A code
with no record of why it exists is one nobody dares switch off.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3e8a1f70b42'
down_revision: Union[str, Sequence[str], None] = 'b7c1d9e42a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('promo_codes', sa.Column('note', sa.String(length=255), nullable=True))
    op.drop_column('promo_codes', 'uses')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'promo_codes',
        sa.Column('uses', sa.Integer(), nullable=False, server_default='0'),
    )
    op.drop_column('promo_codes', 'note')

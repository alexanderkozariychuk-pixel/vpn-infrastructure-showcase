"""record which gateway each payment belongs to

Revision ID: d4f2a9c81e30
Revises: c3e8a1f70b42
Create Date: 2026-09-28

A payment row carried only `heleket_invoice_id` — a column named for one
gateway. With FreeKassa alongside it and Platega replacing FreeKassa, a
callback that arrives with a transaction id has to be matched to the payment
that created it, and two gateways can hand out ids that collide. `provider`
says whose payment it is; `provider_ref` holds that gateway's own transaction
id, gateway-agnostic.

`heleket_invoice_id` is left in place: code still reads it, and a column is
dropped in its own migration once nothing does, so a rollback of the code
does not lose the data. Existing rows are backfilled from it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4f2a9c81e30'
down_revision: Union[str, Sequence[str], None] = 'c3e8a1f70b42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('provider', sa.String(length=16), nullable=True))
    op.add_column('payments', sa.Column('provider_ref', sa.String(length=255), nullable=True))
    # Every existing paid or pending row was Heleket: it is the only gateway
    # that ever wrote heleket_invoice_id. Backfill so old rows are not
    # provider-less once the code starts reading the column.
    op.execute(
        "UPDATE payments SET provider = 'heleket', provider_ref = heleket_invoice_id "
        "WHERE heleket_invoice_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column('payments', 'provider_ref')
    op.drop_column('payments', 'provider')

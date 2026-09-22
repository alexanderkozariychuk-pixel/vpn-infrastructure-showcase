"""add promo codes and the credit ledger

Revision ID: b7c1d9e42a10
Revises: a1b2c3d4e5f6
Create Date: 2026-09-22

Account credit is money the service owes, so it lives in an append-only
ledger rather than a balance column. The unique constraint on
(reason, source_payment_id) is what makes a referral reward idempotent:
gateway webhooks retry, and this is where "credited exactly once" is
guaranteed rather than in code that has to remember to check.

Payments gain the code used and the credit the order intends to consume.
The credit is recorded as an intention rather than deducted at checkout —
an order that is never paid must not spend anything.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c1d9e42a10'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'promo_codes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('owner_user_id', sa.String(), nullable=True),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('max_uses', sa.Integer(), nullable=True),
        sa.Column('uses', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_promo_codes_code'), 'promo_codes', ['code'], unique=True)

    op.create_table(
        'credit_entries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('delta', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=32), nullable=False),
        sa.Column('payment_id', sa.String(), nullable=True),
        sa.Column('source_payment_id', sa.String(), nullable=True),
        sa.Column('vests_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('note', sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id'], ),
        sa.ForeignKeyConstraint(['source_payment_id'], ['payments.id'], ),
        sa.PrimaryKeyConstraint('id'),
        # One reward per referred purchase, enforced by the database.
        sa.UniqueConstraint('reason', 'source_payment_id', name='uq_credit_reason_source'),
    )
    op.create_index(op.f('ix_credit_entries_user_id'), 'credit_entries', ['user_id'], unique=False)

    op.add_column('payments', sa.Column('promo_code', sa.String(length=32), nullable=True))
    op.add_column('payments', sa.Column('credit_spent', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('payments', 'credit_spent')
    op.drop_column('payments', 'promo_code')
    op.drop_index(op.f('ix_credit_entries_user_id'), table_name='credit_entries')
    op.drop_table('credit_entries')
    op.drop_index(op.f('ix_promo_codes_code'), table_name='promo_codes')
    op.drop_table('promo_codes')

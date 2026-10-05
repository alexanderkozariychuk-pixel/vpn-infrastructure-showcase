"""email confirmation, and the language letters are written in

Revision ID: e6b3f0a1c752
Revises: d4f2a9c81e30
Create Date: 2026-10-06

Purchases now need a confirmed mailbox: the receipt, the reset link and any
notice about the service go to `users.email`, and an address nobody reads
(or someone else's) leaves the customer unreachable.

`email_verify_token` holds the SHA-256 of the token, as `reset_token` does
since the previous change: the database never holds a usable link.

`lang` is what the account was created in. A payment receipt is sent from a
gateway callback, where there is no browser to ask.

Existing rows are left unconfirmed. Before this the base held only test
accounts; nothing is backfilled as confirmed on the strength of a guess.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e6b3f0a1c752'
down_revision: Union[str, Sequence[str], None] = 'd4f2a9c81e30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('email_verify_token', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('email_verify_expires', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('lang', sa.String(length=2), nullable=False, server_default='ru'))


def downgrade() -> None:
    op.drop_column('users', 'lang')
    op.drop_column('users', 'email_verify_expires')
    op.drop_column('users', 'email_verify_token')
    op.drop_column('users', 'email_verified_at')

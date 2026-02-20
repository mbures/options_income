"""Add watchlist and opportunities tables

Revision ID: a1b2c3d4e5f6
Revises: 83821511f593
Create Date: 2026-02-17 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '83821511f593'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create watchlist and opportunities tables."""
    op.create_table(
        'watchlist',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_watchlist_symbol', 'watchlist', ['symbol'], unique=True)

    op.create_table(
        'opportunities',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('symbol', sa.String(), nullable=False),
        sa.Column('direction', sa.String(), nullable=False),
        sa.Column('profile', sa.String(), nullable=False),
        sa.Column('strike', sa.Float(), nullable=False),
        sa.Column('expiration_date', sa.String(), nullable=False),
        sa.Column('premium_per_share', sa.Float(), nullable=False),
        sa.Column('total_premium', sa.Float(), nullable=False),
        sa.Column('p_itm', sa.Float(), nullable=False),
        sa.Column('sigma_distance', sa.Float(), nullable=False),
        sa.Column('annualized_yield_pct', sa.Float(), nullable=False),
        sa.Column('bias_score', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('dte', sa.Integer(), nullable=False),
        sa.Column('current_price', sa.Float(), nullable=False),
        sa.Column('bid', sa.Float(), nullable=False),
        sa.Column('ask', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('scanned_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_opportunities_symbol', 'opportunities', ['symbol'])
    op.create_index('ix_opportunities_is_read', 'opportunities', ['is_read'])
    op.create_index('ix_opportunities_scanned_at', 'opportunities', ['scanned_at'])


def downgrade() -> None:
    """Remove watchlist and opportunities tables."""
    op.drop_table('opportunities')
    op.drop_table('watchlist')

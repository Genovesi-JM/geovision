"""add price_usd and price_eur to shop_products

Revision ID: a1b2c3d4e5f6
Revises: c8858ccfbb42
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'c8858ccfbb42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('shop_products', sa.Column('price_usd', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('shop_products', sa.Column('price_eur', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('shop_products', 'price_eur')
    op.drop_column('shop_products', 'price_usd')

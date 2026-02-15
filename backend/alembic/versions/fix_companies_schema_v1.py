"""Fix companies table schema — add missing columns

Revision ID: fix_companies_schema_v1
Revises: 9d1e115c0350
Create Date: 2026-02-15

The enterprise_complete_v1 migration created the companies table with
address_line1/address_line2 columns but the current model expects a single
'address' column. The 9d1e115c0350 migration skipped re-creating the table
because it already existed. This migration adds the missing column.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


revision = 'fix_companies_schema_v1'
down_revision = '9d1e115c0350'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c['name'] for c in inspector.get_columns(table)]
    return column in columns


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists('companies'):
        if not _column_exists('companies', 'address'):
            op.add_column('companies', sa.Column('address', sa.Text(), nullable=True))


def downgrade() -> None:
    if _table_exists('companies') and _column_exists('companies', 'address'):
        op.drop_column('companies', 'address')

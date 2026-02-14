"""add_platform_tables_full_migration

Revision ID: 9d1e115c0350
Revises: prod_hardening_v1
Create Date: 2026-02-14 22:17:24.850505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect


# revision identifiers, used by Alembic.
revision: str = '9d1e115c0350'
down_revision: Union[str, None] = 'prod_hardening_v1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    """Check if table already exists in the database."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return name in inspector.get_table_names()


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    if table not in inspector.get_table_names():
        return False
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def _index_exists(name: str) -> bool:
    """Check if an index already exists."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    for table in inspector.get_table_names():
        for idx in inspector.get_indexes(table):
            if idx["name"] == name:
                return True
    return False


def upgrade() -> None:
    # Made idempotent: skip tables/columns/indexes that already exist
    if not _table_exists('carts'):
        op.create_table('carts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=True),
        sa.Column('company_id', sa.String(length=36), nullable=True),
        sa.Column('session_id', sa.String(length=36), nullable=True),
        sa.Column('site_id', sa.String(length=36), nullable=True),
        sa.Column('coupon_code', sa.String(length=50), nullable=True),
        sa.Column('discount_amount', sa.Integer(), nullable=False),
        sa.Column('discount_type', sa.String(length=20), nullable=True),
        sa.Column('delivery_method', sa.String(length=30), nullable=True),
        sa.Column('delivery_cost', sa.Integer(), nullable=False),
        sa.Column('delivery_address_json', sa.Text(), nullable=True),
        sa.Column('subtotal', sa.Integer(), nullable=False),
        sa.Column('tax_amount', sa.Integer(), nullable=False),
        sa.Column('total', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=5), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_carts_session_id'), 'carts', ['session_id'], unique=False)
        op.create_index(op.f('ix_carts_user_id'), 'carts', ['user_id'], unique=False)

    if not _table_exists('companies'):
        op.create_table('companies',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('tax_id', sa.String(length=50), nullable=True),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('sectors', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('subscription_plan', sa.String(length=20), nullable=False),
        sa.Column('max_users', sa.Integer(), nullable=False),
        sa.Column('max_sites', sa.Integer(), nullable=False),
        sa.Column('max_storage_gb', sa.Integer(), nullable=False),
        sa.Column('current_users', sa.Integer(), nullable=False),
        sa.Column('current_sites', sa.Integer(), nullable=False),
        sa.Column('storage_used_gb', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )

    if not _table_exists('coupons'):
        op.create_table('coupons',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=False),
        sa.Column('discount_type', sa.String(length=20), nullable=False),
        sa.Column('discount_value', sa.Integer(), nullable=False),
        sa.Column('minimum_order', sa.Integer(), nullable=False),
        sa.Column('maximum_discount', sa.Integer(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=False),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('first_order_only', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_coupons_code'), 'coupons', ['code'], unique=True)

    if not _table_exists('datasets'):
        op.create_table('datasets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('site_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_tool', sa.String(length=50), nullable=True),
        sa.Column('data_type', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('sector', sa.String(length=50), nullable=True),
        sa.Column('capture_date', sa.DateTime(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=True),
        sa.Column('file_count', sa.Integer(), nullable=False),
        sa.Column('total_size_bytes', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_datasets_company_id'), 'datasets', ['company_id'], unique=False)
        op.create_index(op.f('ix_datasets_site_id'), 'datasets', ['site_id'], unique=False)

    if not _table_exists('payments'):
        op.create_table('payments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=5), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('provider_reference', sa.String(length=200), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('idempotency_key')
        )
        op.create_index(op.f('ix_payments_company_id'), 'payments', ['company_id'], unique=False)
        op.create_index(op.f('ix_payments_order_id'), 'payments', ['order_id'], unique=False)

    if not _table_exists('risk_assessments'):
        op.create_table('risk_assessments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('site_id', sa.String(length=36), nullable=False),
        sa.Column('sector', sa.String(length=50), nullable=False),
        sa.Column('risk_score', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('risk_level', sa.String(length=20), nullable=False),
        sa.Column('triggered_count', sa.Integer(), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('assessed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_risk_assessments_site_id'), 'risk_assessments', ['site_id'], unique=False)

    if not _table_exists('shop_products'):
        op.create_table('shop_products',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('slug', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('short_description', sa.String(length=500), nullable=True),
        sa.Column('product_type', sa.String(length=30), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('execution_type', sa.String(length=30), nullable=True),
        sa.Column('price', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=5), nullable=False),
        sa.Column('tax_rate', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('duration_hours', sa.Integer(), nullable=True),
        sa.Column('requires_site', sa.Boolean(), nullable=False),
        sa.Column('min_area_ha', sa.Integer(), nullable=True),
        sa.Column('sectors_json', sa.Text(), nullable=True),
        sa.Column('deliverables_json', sa.Text(), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_featured', sa.Boolean(), nullable=False),
        sa.Column('track_inventory', sa.Boolean(), nullable=False),
        sa.Column('stock_quantity', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug')
        )

    if not _table_exists('cart_items'):
        op.create_table('cart_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('cart_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('variant_id', sa.String(length=36), nullable=True),
        sa.Column('product_name', sa.String(), nullable=False),
        sa.Column('product_type', sa.String(length=30), nullable=False),
        sa.Column('product_image', sa.Text(), nullable=True),
        sa.Column('sku', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Integer(), nullable=False),
        sa.Column('total_price', sa.Integer(), nullable=False),
        sa.Column('tax_rate', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('tax_amount', sa.Integer(), nullable=False),
        sa.Column('scheduled_date', sa.DateTime(), nullable=True),
        sa.Column('custom_options_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cart_id'], ['carts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_cart_items_cart_id'), 'cart_items', ['cart_id'], unique=False)

    if not _table_exists('company_users'):
        op.create_table('company_users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('role', sa.String(length=30), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_company_users_company_id'), 'company_users', ['company_id'], unique=False)

    if not _table_exists('connectors'):
        op.create_table('connectors',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('connector_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('api_secret', sa.Text(), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('webhook_secret', sa.Text(), nullable=True),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('last_sync', sa.DateTime(), nullable=True),
        sa.Column('sync_status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_connectors_company_id'), 'connectors', ['company_id'], unique=False)

    if not _table_exists('dataset_files'):
        op.create_table('dataset_files',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('dataset_id', sa.String(length=36), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_dataset_files_dataset_id'), 'dataset_files', ['dataset_id'], unique=False)

    if not _table_exists('documents'):
        op.create_table('documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('site_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('document_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_confidential', sa.Boolean(), nullable=False),
        sa.Column('is_official', sa.Boolean(), nullable=False),
        sa.Column('uploaded_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_documents_company_id'), 'documents', ['company_id'], unique=False)
        op.create_index(op.f('ix_documents_site_id'), 'documents', ['site_id'], unique=False)

    if not _table_exists('integrations'):
        op.create_table('integrations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('connector_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('api_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('webhook_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False),
        sa.Column('sync_interval_hours', sa.Integer(), nullable=False),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('sync_status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_integrations_company_id'), 'integrations', ['company_id'], unique=False)

    if not _table_exists('sites'):
        op.create_table('sites',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('company_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=False),
        sa.Column('province', sa.String(length=100), nullable=True),
        sa.Column('municipality', sa.String(length=100), nullable=True),
        sa.Column('latitude', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('longitude', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('area_hectares', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('sector', sa.String(length=50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_sites_company_id'), 'sites', ['company_id'], unique=False)

    if not _table_exists('deliverables'):
        op.create_table('deliverables',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('order_item_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('deliverable_type', sa.String(length=50), nullable=False),
        sa.Column('storage_key', sa.Text(), nullable=True),
        sa.Column('download_url', sa.Text(), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('download_count', sa.Integer(), nullable=False),
        sa.Column('is_ready', sa.Boolean(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_deliverables_order_id'), 'deliverables', ['order_id'], unique=False)

    if not _table_exists('order_events'):
        op.create_table('order_events',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('actor_name', sa.String(length=100), nullable=True),
        sa.Column('is_customer_visible', sa.Boolean(), nullable=False),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_order_events_order_id'), 'order_events', ['order_id'], unique=False)

    # Add columns to orders table (skip if already present)
    _order_columns = [
        ('order_number', sa.String(length=30), True),
        ('payment_method', sa.String(length=30), True),
        ('payment_intent_id', sa.String(length=36), True),
        ('payment_reference', sa.String(length=100), True),
        ('payment_confirmed_at', sa.DateTime(), True),
        ('coupon_code', sa.String(length=50), True),
        ('tax_amount', sa.Numeric(precision=12, scale=2), False),
        ('delivery_method', sa.String(length=30), True),
        ('delivery_notes', sa.Text(), True),
        ('estimated_delivery', sa.DateTime(), True),
        ('actual_delivery', sa.DateTime(), True),
        ('assigned_team', sa.String(length=100), True),
        ('scheduled_start', sa.DateTime(), True),
        ('scheduled_end', sa.DateTime(), True),
        ('actual_start', sa.DateTime(), True),
        ('actual_end', sa.DateTime(), True),
        ('customer_notes', sa.Text(), True),
        ('internal_notes', sa.Text(), True),
        ('billing_info_json', sa.Text(), True),
        ('completed_at', sa.DateTime(), True),
        ('cancelled_at', sa.DateTime(), True),
        ('metadata_json', sa.Text(), True),
    ]
    for col_name, col_type, nullable in _order_columns:
        if not _column_exists('orders', col_name):
            op.add_column('orders', sa.Column(col_name, col_type, nullable=nullable))

    if not _column_exists('orders', 'order_number') or True:
        try:
            op.create_index(op.f('ix_orders_order_number'), 'orders', ['order_number'], unique=True)
        except Exception:
            pass  # Index may already exist
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_orders_order_number'), table_name='orders')
    op.drop_column('orders', 'metadata_json')
    op.drop_column('orders', 'cancelled_at')
    op.drop_column('orders', 'completed_at')
    op.drop_column('orders', 'billing_info_json')
    op.drop_column('orders', 'internal_notes')
    op.drop_column('orders', 'customer_notes')
    op.drop_column('orders', 'actual_end')
    op.drop_column('orders', 'actual_start')
    op.drop_column('orders', 'scheduled_end')
    op.drop_column('orders', 'scheduled_start')
    op.drop_column('orders', 'assigned_team')
    op.drop_column('orders', 'actual_delivery')
    op.drop_column('orders', 'estimated_delivery')
    op.drop_column('orders', 'delivery_notes')
    op.drop_column('orders', 'delivery_method')
    op.drop_column('orders', 'tax_amount')
    op.drop_column('orders', 'coupon_code')
    op.drop_column('orders', 'payment_confirmed_at')
    op.drop_column('orders', 'payment_reference')
    op.drop_column('orders', 'payment_intent_id')
    op.drop_column('orders', 'payment_method')
    op.drop_column('orders', 'order_number')
    op.drop_index(op.f('ix_order_events_order_id'), table_name='order_events')
    op.drop_table('order_events')
    op.drop_index(op.f('ix_deliverables_order_id'), table_name='deliverables')
    op.drop_table('deliverables')
    op.drop_index(op.f('ix_sites_company_id'), table_name='sites')
    op.drop_table('sites')
    op.drop_index(op.f('ix_integrations_company_id'), table_name='integrations')
    op.drop_table('integrations')
    op.drop_index(op.f('ix_documents_site_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_company_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_dataset_files_dataset_id'), table_name='dataset_files')
    op.drop_table('dataset_files')
    op.drop_index(op.f('ix_connectors_company_id'), table_name='connectors')
    op.drop_table('connectors')
    op.drop_index(op.f('ix_company_users_company_id'), table_name='company_users')
    op.drop_table('company_users')
    op.drop_index(op.f('ix_cart_items_cart_id'), table_name='cart_items')
    op.drop_table('cart_items')
    op.drop_table('shop_products')
    op.drop_index(op.f('ix_risk_assessments_site_id'), table_name='risk_assessments')
    op.drop_table('risk_assessments')
    op.drop_index(op.f('ix_payments_order_id'), table_name='payments')
    op.drop_index(op.f('ix_payments_company_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_datasets_site_id'), table_name='datasets')
    op.drop_index(op.f('ix_datasets_company_id'), table_name='datasets')
    op.drop_table('datasets')
    op.drop_index(op.f('ix_coupons_code'), table_name='coupons')
    op.drop_table('coupons')
    op.drop_table('companies')
    op.drop_index(op.f('ix_carts_user_id'), table_name='carts')
    op.drop_index(op.f('ix_carts_session_id'), table_name='carts')
    op.drop_table('carts')
    # ### end Alembic commands ###

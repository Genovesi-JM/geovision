"""Add complete enterprise schema - payments, risk, analytics

Revision ID: enterprise_complete_v1
Revises: 3e76cc464332
Create Date: 2026-02-13

This migration adds:
- Payment system tables (providers, intents, transactions, webhooks, refunds)
- Risk assessment tables (scores, alerts, events, notifications)
- Analytics tables (site metrics, alert rules, sector thresholds)
- Enterprise tables (companies, sites, datasets, documents, connectors)
- Shop tables (products, carts, orders, coupons, deliveries)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'enterprise_complete_v1'
down_revision = '3e76cc464332'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============ COMPANIES ============
    op.create_table('companies',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('legal_name', sa.String(300), nullable=True),
        sa.Column('tax_id', sa.String(50), nullable=True),
        sa.Column('email', sa.String(), nullable=False, index=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('whatsapp', sa.String(50), nullable=True),
        sa.Column('address_line1', sa.String(300), nullable=True),
        sa.Column('address_line2', sa.String(300), nullable=True),
        sa.Column('city', sa.String(100), nullable=True),
        sa.Column('province', sa.String(100), nullable=True),
        sa.Column('country', sa.String(100), nullable=False, default='Angola'),
        sa.Column('sectors', sa.Text(), nullable=False, default='["agro"]'),
        sa.Column('status', sa.String(20), nullable=False, default='trial'),
        sa.Column('subscription_plan', sa.String(30), nullable=False, default='trial'),
        sa.Column('subscription_expires_at', sa.DateTime(), nullable=True),
        sa.Column('max_users', sa.Integer(), nullable=False, default=5),
        sa.Column('max_sites', sa.Integer(), nullable=False, default=10),
        sa.Column('max_storage_gb', sa.Integer(), nullable=False, default=50),
        sa.Column('current_users', sa.Integer(), nullable=False, default=0),
        sa.Column('current_sites', sa.Integer(), nullable=False, default=0),
        sa.Column('storage_used_gb', sa.Numeric(10, 2), nullable=False, default=0),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('primary_color', sa.String(10), nullable=True),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_companies_status', 'companies', ['status'])
    
    # ============ COMPANY MEMBERS ============
    op.create_table('company_members',
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role', sa.String(30), nullable=False, default='client_viewer'),
        sa.Column('permissions', sa.Text(), nullable=True),
        sa.Column('is_primary_contact', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_company_members_user', 'company_members', ['user_id'])
    
    # ============ SITES ============
    op.create_table('sites',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('code', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('address', sa.String(500), nullable=True),
        sa.Column('province', sa.String(100), nullable=True),
        sa.Column('municipality', sa.String(100), nullable=True),
        sa.Column('latitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('longitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('area_hectares', sa.Numeric(12, 2), nullable=True),
        sa.Column('sector', sa.String(50), nullable=False, default='agro'),
        sa.Column('site_type', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_sites_sector', 'sites', ['sector'])
    
    # ============ SOFTWARE CONNECTORS ============
    op.create_table('software_connectors',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('connector_type', sa.String(30), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('api_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('refresh_token_encrypted', sa.Text(), nullable=True),
        sa.Column('base_url', sa.String(500), nullable=True),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('webhook_secret', sa.String(100), nullable=True),
        sa.Column('watch_folder_path', sa.Text(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=True),
        sa.Column('sync_status', sa.String(20), nullable=False, default='never'),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, default=False),
        sa.Column('sync_interval_minutes', sa.Integer(), nullable=False, default=60),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_connectors_type', 'software_connectors', ['connector_type'])
    
    # ============ DATASETS ============
    op.create_table('datasets',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('data_type', sa.String(50), nullable=False, default='drone_imagery'),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('connector_id', sa.String(36), sa.ForeignKey('software_connectors.id', ondelete='SET NULL'), nullable=True),
        sa.Column('collection_date', sa.DateTime(), nullable=True),
        sa.Column('processing_date', sa.DateTime(), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=True),
        sa.Column('storage_size_mb', sa.Numeric(12, 2), nullable=True),
        sa.Column('file_count', sa.Integer(), nullable=False, default=0),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_datasets_status', 'datasets', ['status'])
    
    # ============ DOCUMENTS ============
    op.create_table('documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('name', sa.String(300), nullable=False),
        sa.Column('original_filename', sa.String(500), nullable=False),
        sa.Column('file_extension', sa.String(20), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), nullable=False, default=0),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('storage_provider', sa.String(30), nullable=False, default='local'),
        sa.Column('document_type', sa.String(30), nullable=False, default='other'),
        sa.Column('status', sa.String(30), nullable=False, default='draft'),
        sa.Column('is_confidential', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_official', sa.Boolean(), nullable=False, default=False),
        sa.Column('download_blocked', sa.Boolean(), nullable=False, default=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False, default=1),
        sa.Column('previous_version_id', sa.String(36), nullable=True),
        sa.Column('uploaded_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_documents_type', 'documents', ['document_type'])
    op.create_index('idx_documents_status', 'documents', ['status'])
    
    # ============ ALERTS (Enterprise) ============
    op.create_table('alerts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, default='info'),
        sa.Column('category', sa.String(50), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, default=False),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, default=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_id', sa.String(36), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_alerts_severity', 'alerts', ['severity'])
    op.create_index('idx_alerts_resolved', 'alerts', ['is_resolved'])
    
    # ============ INVOICES (Enterprise) ============
    op.create_table('invoices',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), sa.ForeignKey('companies.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('invoice_number', sa.String(50), unique=True, nullable=False),
        sa.Column('subtotal', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('tax_amount', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('total', sa.Numeric(12, 2), nullable=False, default=0),
        sa.Column('currency', sa.String(10), nullable=False, default='AOA'),
        sa.Column('status', sa.String(20), nullable=False, default='draft'),
        sa.Column('issue_date', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('due_date', sa.DateTime(), nullable=True),
        sa.Column('paid_at', sa.DateTime(), nullable=True),
        sa.Column('payment_method', sa.String(30), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=True),
        sa.Column('items', sa.Text(), nullable=True),
        sa.Column('pdf_url', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_invoices_status', 'invoices', ['status'])
    
    # ============ AUDIT LOGS ============
    op.create_table('audit_logs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('user_email', sa.String(), nullable=True),
        sa.Column('user_role', sa.String(30), nullable=True),
        sa.Column('company_id', sa.String(36), nullable=True, index=True),
        sa.Column('resource_type', sa.String(50), nullable=False),
        sa.Column('resource_id', sa.String(36), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('changes', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )
    op.create_index('idx_audit_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_resource', 'audit_logs', ['resource_type', 'resource_id'])
    
    # ============ ADMIN CONTACTS ============
    op.create_table('admin_contacts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('role', sa.String(100), nullable=True),
        sa.Column('department', sa.String(100), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('phone', sa.String(50), nullable=True),
        sa.Column('whatsapp', sa.String(50), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_internal', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    # ============ TWO FACTOR AUTH ============
    op.create_table('two_factor_auth',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('secret_encrypted', sa.Text(), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, default=False),
        sa.Column('backup_codes_encrypted', sa.Text(), nullable=True),
        sa.Column('verified_at', sa.DateTime(), nullable=True),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    
    # ============ PAYMENT PROVIDERS ============
    op.create_table('payment_providers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('api_secret_encrypted', sa.Text(), nullable=True),
        sa.Column('merchant_id', sa.String(100), nullable=True),
        sa.Column('terminal_id', sa.String(100), nullable=True),
        sa.Column('api_base_url', sa.String(500), nullable=True),
        sa.Column('webhook_url', sa.String(500), nullable=True),
        sa.Column('webhook_secret', sa.String(200), nullable=True),
        sa.Column('bank_name', sa.String(200), nullable=True),
        sa.Column('iban', sa.String(50), nullable=True),
        sa.Column('swift_bic', sa.String(20), nullable=True),
        sa.Column('account_holder', sa.String(200), nullable=True),
        sa.Column('fee_percentage', sa.Numeric(5, 4), nullable=False, default=0),
        sa.Column('fee_fixed', sa.Integer(), nullable=False, default=0),
        sa.Column('supported_currencies', sa.Text(), nullable=True),
        sa.Column('default_currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('min_amount', sa.Integer(), nullable=False, default=100),
        sa.Column('max_amount', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_test_mode', sa.Boolean(), nullable=False, default=True),
        sa.Column('settings', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_payment_providers_type', 'payment_providers', ['provider_type'])
    op.create_index('idx_payment_providers_active', 'payment_providers', ['is_active'])
    
    # ============ PAYMENT INTENTS ============
    op.create_table('payment_intents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('idempotency_key', sa.String(100), unique=True, nullable=False, index=True),
        sa.Column('order_id', sa.String(36), nullable=False, index=True),
        sa.Column('company_id', sa.String(36), nullable=True, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('provider_id', sa.String(36), sa.ForeignKey('payment_providers.id'), nullable=False),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('provider_fee', sa.Integer(), nullable=False, default=0),
        sa.Column('platform_fee', sa.Integer(), nullable=False, default=0),
        sa.Column('net_amount', sa.Integer(), nullable=False, default=0),
        sa.Column('status', sa.String(30), nullable=False, default='created'),
        sa.Column('provider_intent_id', sa.String(200), nullable=True),
        sa.Column('provider_reference', sa.String(200), nullable=True),
        sa.Column('bank_reference', sa.String(100), nullable=True, index=True),
        sa.Column('entity_number', sa.String(20), nullable=True),
        sa.Column('payment_reference', sa.String(50), nullable=True),
        sa.Column('last_four', sa.String(4), nullable=True),
        sa.Column('card_brand', sa.String(20), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('failure_code', sa.String(50), nullable=True),
        sa.Column('failure_message', sa.Text(), nullable=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('refunded_amount', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_payment_intents_status', 'payment_intents', ['status'])
    op.create_index('idx_payment_intents_provider', 'payment_intents', ['provider_id'])
    op.create_index('idx_payment_intents_created', 'payment_intents', ['created_at'])
    
    # ============ PAYMENT TRANSACTIONS ============
    op.create_table('payment_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payment_intent_id', sa.String(36), sa.ForeignKey('payment_intents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('transaction_type', sa.String(30), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('provider_transaction_id', sa.String(200), nullable=True),
        sa.Column('provider_response', sa.Text(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, default=False),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('request_payload', sa.Text(), nullable=True),
        sa.Column('response_payload', sa.Text(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_payment_transactions_type', 'payment_transactions', ['transaction_type'])
    op.create_index('idx_payment_transactions_status', 'payment_transactions', ['status'])
    
    # ============ PAYMENT WEBHOOK EVENTS ============
    op.create_table('payment_webhook_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('provider_type', sa.String(50), nullable=False),
        sa.Column('provider_event_id', sa.String(200), nullable=False, index=True),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('processed', sa.Boolean(), nullable=False, default=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('process_attempts', sa.Integer(), nullable=False, default=0),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('payment_intent_id', sa.String(36), nullable=True, index=True),
        sa.Column('order_id', sa.String(36), nullable=True, index=True),
        sa.Column('ip_address', sa.String(50), nullable=True),
        sa.Column('signature_valid', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now(), index=True),
    )
    op.create_index('idx_webhook_events_provider', 'payment_webhook_events', ['provider_type'])
    op.create_index('idx_webhook_events_processed', 'payment_webhook_events', ['processed'])
    op.create_index('idx_webhook_events_type', 'payment_webhook_events', ['event_type'])
    
    # ============ BANK TRANSFER RECONCILIATION ============
    op.create_table('bank_transfer_reconciliations',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payment_intent_id', sa.String(36), sa.ForeignKey('payment_intents.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('bank_name', sa.String(200), nullable=False),
        sa.Column('statement_date', sa.DateTime(), nullable=False),
        sa.Column('statement_reference', sa.String(100), nullable=True),
        sa.Column('sender_name', sa.String(200), nullable=True),
        sa.Column('sender_iban', sa.String(50), nullable=True),
        sa.Column('payment_reference', sa.String(100), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('matched', sa.Boolean(), nullable=False, default=False),
        sa.Column('matched_at', sa.DateTime(), nullable=True),
        sa.Column('matched_by_id', sa.String(36), nullable=True),
        sa.Column('match_confidence', sa.Numeric(3, 2), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_reconciliation_matched', 'bank_transfer_reconciliations', ['matched'])
    op.create_index('idx_reconciliation_status', 'bank_transfer_reconciliations', ['status'])
    
    # ============ PAYMENT REFUNDS ============
    op.create_table('payment_refunds',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('payment_intent_id', sa.String(36), sa.ForeignKey('payment_intents.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('idempotency_key', sa.String(100), unique=True, nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('reason', sa.String(50), nullable=False, default='customer_request'),
        sa.Column('reason_details', sa.Text(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('provider_refund_id', sa.String(200), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('requested_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_refunds_status', 'payment_refunds', ['status'])
    
    # ============ PAYOUTS ============
    op.create_table('payouts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), nullable=False, index=True),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, default='AOA'),
        sa.Column('bank_name', sa.String(200), nullable=False),
        sa.Column('iban', sa.String(50), nullable=False),
        sa.Column('swift_bic', sa.String(20), nullable=True),
        sa.Column('account_holder', sa.String(200), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('payout_reference', sa.String(100), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by_id', sa.String(36), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_payouts_status', 'payouts', ['status'])
    
    # ============ RISK SCORES ============
    op.create_table('risk_scores',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), nullable=False, index=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('dataset_id', sa.String(36), sa.ForeignKey('datasets.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('sector', sa.String(50), nullable=False),
        sa.Column('risk_category', sa.String(50), nullable=False),
        sa.Column('risk_level', sa.String(20), nullable=False, default='low'),
        sa.Column('overall_score', sa.Numeric(5, 2), nullable=False),
        sa.Column('component_scores', sa.Text(), nullable=True),
        sa.Column('metrics_json', sa.Text(), nullable=True),
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('calculation_method', sa.String(100), nullable=True),
        sa.Column('confidence_score', sa.Numeric(3, 2), nullable=True),
        sa.Column('assessment_date', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('period_start', sa.DateTime(), nullable=True),
        sa.Column('period_end', sa.DateTime(), nullable=True),
        sa.Column('is_latest', sa.Boolean(), nullable=False, default=True),
        sa.Column('superseded_by_id', sa.String(36), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_risk_scores_category', 'risk_scores', ['risk_category'])
    op.create_index('idx_risk_scores_level', 'risk_scores', ['risk_level'])
    op.create_index('idx_risk_scores_date', 'risk_scores', ['assessment_date'])
    op.create_index('idx_risk_scores_latest', 'risk_scores', ['is_latest'])
    
    # ============ RISK ALERTS ============
    op.create_table('risk_alerts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), nullable=False, index=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('risk_score_id', sa.String(36), sa.ForeignKey('risk_scores.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('alert_code', sa.String(50), nullable=False, index=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('sector', sa.String(50), nullable=False),
        sa.Column('risk_category', sa.String(50), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, default='medium'),
        sa.Column('risk_level', sa.String(20), nullable=False, default='medium'),
        sa.Column('status', sa.String(30), nullable=False, default='active'),
        sa.Column('triggered_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledged_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_by_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('escalated', sa.Boolean(), nullable=False, default=False),
        sa.Column('escalated_at', sa.DateTime(), nullable=True),
        sa.Column('escalation_level', sa.Integer(), nullable=False, default=0),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('latitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('longitude', sa.Numeric(10, 7), nullable=True),
        sa.Column('affected_area_geojson', sa.Text(), nullable=True),
        sa.Column('recommendations', sa.Text(), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_risk_alerts_status', 'risk_alerts', ['status'])
    op.create_index('idx_risk_alerts_severity', 'risk_alerts', ['severity'])
    op.create_index('idx_risk_alerts_triggered', 'risk_alerts', ['triggered_at'])
    op.create_index('idx_risk_alerts_sector', 'risk_alerts', ['sector'])
    
    # ============ ALERT EVENTS ============
    op.create_table('alert_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('alert_id', sa.String(36), sa.ForeignKey('risk_alerts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('previous_status', sa.String(30), nullable=True),
        sa.Column('new_status', sa.String(30), nullable=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('actor_name', sa.String(200), nullable=True),
        sa.Column('extra_data', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_alert_events_type', 'alert_events', ['event_type'])
    
    # ============ ALERT NOTIFICATIONS ============
    op.create_table('alert_notifications',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('alert_id', sa.String(36), sa.ForeignKey('risk_alerts.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('recipient_email', sa.String(), nullable=True),
        sa.Column('recipient_phone', sa.String(50), nullable=True),
        sa.Column('notification_type', sa.String(20), nullable=False),
        sa.Column('subject', sa.String(300), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('status', sa.String(30), nullable=False, default='pending'),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('delivered_at', sa.DateTime(), nullable=True),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, default=0),
        sa.Column('provider', sa.String(50), nullable=True),
        sa.Column('provider_message_id', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_alert_notifications_status', 'alert_notifications', ['status'])
    op.create_index('idx_alert_notifications_type', 'alert_notifications', ['notification_type'])
    
    # ============ SITE METRICS ============
    op.create_table('site_metrics',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), nullable=False, index=True),
        sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_category', sa.String(50), nullable=False),
        sa.Column('value_numeric', sa.Numeric(20, 6), nullable=True),
        sa.Column('value_text', sa.String(500), nullable=True),
        sa.Column('value_json', sa.Text(), nullable=True),
        sa.Column('unit', sa.String(50), nullable=True),
        sa.Column('recorded_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('period', sa.String(20), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('dataset_id', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_site_metrics_name', 'site_metrics', ['metric_name'])
    op.create_index('idx_site_metrics_recorded', 'site_metrics', ['recorded_at'])
    op.create_index('idx_site_metrics_category', 'site_metrics', ['metric_category'])
    
    # ============ ALERT RULES ============
    op.create_table('alert_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('company_id', sa.String(36), nullable=True, index=True),
        sa.Column('site_id', sa.String(36), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('sector', sa.String(50), nullable=True),
        sa.Column('risk_category', sa.String(50), nullable=False),
        sa.Column('conditions', sa.Text(), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, default='medium'),
        sa.Column('alert_title_template', sa.String(200), nullable=False),
        sa.Column('alert_description_template', sa.Text(), nullable=False),
        sa.Column('threshold_low', sa.Numeric(10, 2), nullable=True),
        sa.Column('threshold_medium', sa.Numeric(10, 2), nullable=True),
        sa.Column('threshold_high', sa.Numeric(10, 2), nullable=True),
        sa.Column('threshold_critical', sa.Numeric(10, 2), nullable=True),
        sa.Column('cooldown_minutes', sa.Integer(), nullable=False, default=60),
        sa.Column('last_triggered_at', sa.DateTime(), nullable=True),
        sa.Column('notification_channels', sa.Text(), nullable=True),
        sa.Column('auto_escalate_after_minutes', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_alert_rules_active', 'alert_rules', ['is_active'])
    op.create_index('idx_alert_rules_category', 'alert_rules', ['risk_category'])
    
    # ============ SECTOR THRESHOLDS ============
    op.create_table('sector_thresholds',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('sector', sa.String(50), nullable=False),
        sa.Column('risk_category', sa.String(50), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('threshold_low', sa.Numeric(10, 2), nullable=False),
        sa.Column('threshold_medium', sa.Numeric(10, 2), nullable=False),
        sa.Column('threshold_high', sa.Numeric(10, 2), nullable=False),
        sa.Column('threshold_critical', sa.Numeric(10, 2), nullable=False),
        sa.Column('unit', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_sector_thresholds_sector', 'sector_thresholds', ['sector'])
    op.create_index('idx_sector_thresholds_category', 'sector_thresholds', ['risk_category'])


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table('sector_thresholds')
    op.drop_table('alert_rules')
    op.drop_table('site_metrics')
    op.drop_table('alert_notifications')
    op.drop_table('alert_events')
    op.drop_table('risk_alerts')
    op.drop_table('risk_scores')
    op.drop_table('payouts')
    op.drop_table('payment_refunds')
    op.drop_table('bank_transfer_reconciliations')
    op.drop_table('payment_webhook_events')
    op.drop_table('payment_transactions')
    op.drop_table('payment_intents')
    op.drop_table('payment_providers')
    op.drop_table('two_factor_auth')
    op.drop_table('admin_contacts')
    op.drop_table('audit_logs')
    op.drop_table('invoices')
    op.drop_table('alerts')
    op.drop_table('documents')
    op.drop_table('datasets')
    op.drop_table('software_connectors')
    op.drop_table('sites')
    op.drop_table('company_members')
    op.drop_table('companies')

# GeoVision Database Schema

Complete PostgreSQL database schema with multi-tenancy, e-commerce, payments, and risk assessment.

## Quick Start

```bash
# Run migration
cd backend
alembic upgrade head

# Reset database (DANGER - drops all data)
alembic downgrade base
alembic upgrade head
```

## Table Overview

| Category | Tables |
|----------|--------|
| **Identity** | `users`, `user_profiles`, `accounts`, `account_members` |
| **Enterprise** | `companies`, `company_members`, `sites`, `software_connectors` |
| **Data** | `datasets`, `documents` |
| **E-commerce** | `shop_products`, `product_variants`, `carts`, `cart_items`, `shop_orders`, `order_events`, `deliverables`, `coupons` |
| **Payments** | `payment_providers`, `payment_intents`, `payment_transactions`, `payment_webhook_events`, `bank_transfer_reconciliations`, `payment_refunds`, `payouts` |
| **Risk** | `risk_scores`, `risk_alerts`, `alert_events`, `alert_notifications`, `site_metrics`, `alert_rules`, `sector_thresholds` |
| **Security** | `audit_logs`, `two_factor_auth`, `oauth_states`, `password_reset_tokens` |

---

## Example Queries

### 1. List Sites for a Company (with sector filter)

```sql
-- All active sites for a company
SELECT s.id, s.name, s.sector, s.province, s.latitude, s.longitude
FROM sites s
WHERE s.company_id = :company_id
  AND s.is_active = true
ORDER BY s.sector, s.name;

-- Filter by sector
SELECT s.id, s.name, s.sector
FROM sites s
WHERE s.company_id = :company_id
  AND s.sector = 'mining'
  AND s.is_active = true;
```

**SQLAlchemy:**
```python
from app.models_enterprise import Site, SiteType

# All sites
sites = db.query(Site).filter(
    Site.company_id == company_id,
    Site.is_active == True
).order_by(Site.sector, Site.name).all()

# By sector
mining_sites = db.query(Site).filter(
    Site.company_id == company_id,
    Site.sector == "mining",
    Site.is_active == True
).all()
```

---

### 2. Create Order with Payment

```sql
-- 1. Create shop order
INSERT INTO shop_orders (
    id, invoice_number, user_id, company_id, 
    subtotal, tax_amount, total, currency, status
) VALUES (
    'ord-uuid', 'GV-2024-0001', 'user-uuid', 'company-uuid',
    5000000, 700000, 5700000, 'AOA', 'pending_payment'
);

-- 2. Create payment intent
INSERT INTO payment_intents (
    id, idempotency_key, order_id, company_id, user_id,
    provider_id, provider_type, amount, currency, status
) VALUES (
    'pi-uuid', 'order_ord-uuid_attempt_1', 'ord-uuid', 'company-uuid', 'user-uuid',
    'provider-uuid', 'multicaixa_express', 5700000, 'AOA', 'created'
);

-- 3. On payment confirmed (webhook)
UPDATE payment_intents 
SET status = 'confirmed', confirmed_at = NOW()
WHERE id = 'pi-uuid';

UPDATE shop_orders
SET status = 'paid', payment_confirmed_at = NOW()
WHERE id = 'ord-uuid';
```

**SQLAlchemy:**
```python
from app.models_shop import ShopOrder, OrderStatus
from app.models_payments import PaymentIntent, PaymentIntentStatus
import uuid

# Create order
order = ShopOrder(
    id=str(uuid.uuid4()),
    invoice_number="GV-2024-0001",
    user_id=user_id,
    company_id=company_id,
    subtotal=5_000_000,  # 50,000 AOA in centavos
    tax_amount=700_000,
    total=5_700_000,
    currency="AOA",
    status=OrderStatus.pending_payment
)
db.add(order)

# Create payment intent
payment = PaymentIntent(
    id=str(uuid.uuid4()),
    idempotency_key=f"order_{order.id}_attempt_1",
    order_id=order.id,
    user_id=user_id,
    provider_id=provider_id,
    provider_type="multicaixa_express",
    amount=order.total,
    currency="AOA",
    status=PaymentIntentStatus.created
)
db.add(payment)
db.commit()
```

---

### 3. Create Dataset + Risk Score + Alert

```sql
-- 1. Upload dataset
INSERT INTO datasets (
    id, site_id, name, data_type, source, status
) VALUES (
    'ds-uuid', 'site-uuid', 'Satellite Imagery Dec 2024',
    'satellite_imagery', 'Sentinel-2', 'processed'
);

-- 2. Register risk score
INSERT INTO risk_scores (
    id, company_id, site_id, dataset_id, sector, 
    risk_category, risk_level, overall_score, assessment_date
) VALUES (
    'rs-uuid', 'company-uuid', 'site-uuid', 'ds-uuid', 'mining',
    'environmental', 'critical', 87.5, NOW()
);

-- 3. Create alert if critical
INSERT INTO risk_alerts (
    id, company_id, site_id, risk_score_id, alert_code,
    title, description, sector, risk_category, severity, status
) VALUES (
    'alert-uuid', 'company-uuid', 'site-uuid', 'rs-uuid', 'ENV_001',
    'Critical Environmental Risk Detected',
    'Analysis identified potential soil contamination in mining area.',
    'mining', 'environmental', 'critical', 'active'
);
```

**SQLAlchemy:**
```python
from app.models_enterprise import Dataset, DatasetStatus, DataType
from app.models_risk import RiskScore, RiskAlert, RiskLevel, RiskCategory, AlertStatus
import uuid

# Create dataset
dataset = Dataset(
    id=str(uuid.uuid4()),
    site_id=site_id,
    name="Satellite Imagery Dec 2024",
    data_type=DataType.satellite_imagery,
    source="Sentinel-2",
    status=DatasetStatus.processed
)
db.add(dataset)
db.flush()

# Create risk score
score = RiskScore(
    id=str(uuid.uuid4()),
    company_id=company_id,
    site_id=site_id,
    dataset_id=dataset.id,
    sector="mining",
    risk_category=RiskCategory.environmental,
    risk_level=RiskLevel.critical,
    overall_score=87.5,
)
db.add(score)
db.flush()

# Create alert for critical risk
if score.risk_level == RiskLevel.critical:
    alert = RiskAlert(
        id=str(uuid.uuid4()),
        company_id=company_id,
        site_id=site_id,
        risk_score_id=score.id,
        alert_code="ENV_001",
        title="Critical Environmental Risk Detected",
        description="Analysis identified potential soil contamination in mining area.",
        sector="mining",
        risk_category=RiskCategory.environmental,
        severity="critical",
        status=AlertStatus.active
    )
    db.add(alert)

db.commit()
```

---

### 4. Dashboard: Active Alerts by Severity

```sql
SELECT 
    severity,
    status,
    COUNT(*) as count
FROM risk_alerts
WHERE company_id = :company_id
  AND status IN ('active', 'acknowledged')
GROUP BY severity, status
ORDER BY 
    CASE severity 
        WHEN 'critical' THEN 1 
        WHEN 'high' THEN 2 
        WHEN 'medium' THEN 3 
        ELSE 4 
    END;
```

**SQLAlchemy:**
```python
from sqlalchemy import func
from app.models_risk import RiskAlert, AlertStatus

results = db.query(
    RiskAlert.severity,
    RiskAlert.status,
    func.count(RiskAlert.id).label('count')
).filter(
    RiskAlert.company_id == company_id,
    RiskAlert.status.in_([AlertStatus.active, AlertStatus.acknowledged])
).group_by(
    RiskAlert.severity,
    RiskAlert.status
).all()
```

---

### 5. Payment Reconciliation Report

```sql
SELECT 
    p.name as provider_name,
    pi.status,
    COUNT(*) as transaction_count,
    SUM(pi.amount) / 100.0 as total_amount_aoa,
    SUM(pi.provider_fee) / 100.0 as total_fees
FROM payment_intents pi
JOIN payment_providers p ON pi.provider_id = p.id
WHERE pi.company_id = :company_id
  AND pi.created_at >= :start_date
  AND pi.created_at < :end_date
GROUP BY p.name, pi.status
ORDER BY p.name, pi.status;
```

---

### 6. Multi-Tenant Access Control

```sql
-- Get user's accessible companies
SELECT c.*
FROM companies c
JOIN company_members cm ON c.id = cm.company_id
WHERE cm.user_id = :user_id;

-- Check if user has access to specific company
SELECT EXISTS (
    SELECT 1 FROM company_members 
    WHERE user_id = :user_id AND company_id = :company_id
) as has_access;

-- Get user's role in company
SELECT role, permissions
FROM company_members
WHERE user_id = :user_id AND company_id = :company_id;
```

**SQLAlchemy (dependency injection):**
```python
from app.models_enterprise import CompanyMember, UserRole

def get_current_company(user_id: str, company_id: str, db: Session):
    """Verify user has access to company and return role."""
    member = db.query(CompanyMember).filter(
        CompanyMember.user_id == user_id,
        CompanyMember.company_id == company_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=403, detail="Access denied")
    
    return member
```

---

### 7. Site Metrics Aggregation (Time Series)

```sql
-- Daily NDVI average for agriculture site
SELECT 
    DATE(recorded_at) as date,
    metric_name,
    AVG(value_numeric) as avg_value,
    MIN(value_numeric) as min_value,
    MAX(value_numeric) as max_value
FROM site_metrics
WHERE site_id = :site_id
  AND metric_category = 'vegetation'
  AND metric_name = 'ndvi'
  AND recorded_at >= :start_date
GROUP BY DATE(recorded_at), metric_name
ORDER BY date;
```

---

### 8. Audit Trail Export

```sql
SELECT 
    al.created_at,
    al.user_email,
    al.action,
    al.resource_type,
    al.resource_id,
    al.details,
    al.ip_address
FROM audit_logs al
WHERE al.company_id = :company_id
  AND al.created_at >= :start_date
  AND al.created_at < :end_date
ORDER BY al.created_at DESC
LIMIT 1000;
```

**SQLAlchemy:**
```python
from app.models_enterprise import AuditLog

def log_action(
    db: Session, 
    user_id: str, 
    action: str, 
    resource_type: str,
    resource_id: str = None,
    details: dict = None,
    request: Request = None
):
    log = AuditLog(
        id=str(uuid.uuid4()),
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=json.dumps(details) if details else None,
        ip_address=request.client.host if request else None,
        user_agent=request.headers.get("user-agent") if request else None
    )
    db.add(log)
    db.commit()
```

---

## Entity Relationships

```
┌───────────────────────────────────────────────────────────────────┐
│                         MULTI-TENANCY                              │
└───────────────────────────────────────────────────────────────────┘
                              │
    ┌─────────────────────────┼─────────────────────────┐
    │                         │                         │
    v                         v                         v
┌─────────┐            ┌───────────┐             ┌──────────┐
│ Company │────────────│   Site    │─────────────│ Dataset  │
└─────────┘            └───────────┘             └──────────┘
     │                      │                         │
     │                      │                         │
     v                      v                         v
┌─────────────┐      ┌───────────────┐        ┌───────────┐
│ ShopOrder   │      │  RiskScore    │        │ Document  │
└─────────────┘      └───────────────┘        └───────────┘
     │                      │
     │                      │
     v                      v
┌─────────────────┐   ┌───────────┐
│ PaymentIntent   │   │ RiskAlert │
└─────────────────┘   └───────────┘
     │                      │
     v                      v
┌─────────────────┐   ┌─────────────────┐
│ PaymentTransaction│ │ AlertNotification│
└─────────────────┘   └─────────────────┘
```

---

## Sectors

- `agro` - Agriculture
- `mining` - Mining
- `livestock` - Livestock
- `construction` - Construction
- `infrastructure` - Infrastructure
- `demining` - Demining/UXO

---

## Currency Note

All monetary values are stored in **centavos (cents)** as integers:
- `5700000` = 57,000.00 AOA
- Divide by 100 for display

---

## Next Steps

1. Run migration: `alembic upgrade head`
2. Create API routers for each domain
3. Add Pydantic schemas for request/response
4. Implement webhook handlers for payment providers
5. Set up background jobs for alert notifications

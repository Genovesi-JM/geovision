# ERP and real-time customer account

## Decision

ERPNext is the initial ERP for GeoVision. It matches the existing open-source,
API-first FastAPI platform and covers sales, purchasing, inventory, warehouse,
invoicing, payments and multi-currency. The integration remains provider-neutral
so a future ERP can be introduced without changing the Flutter application.

PostgreSQL/PostGIS remains GeoVision's operational database. ERPNext is the
commercial/accounting system after documents synchronize. The mobile app never
connects directly to either database or ERPNext.

```text
Flutter app
    │ authenticated snapshot + SSE/polling
    ▼
FastAPI /mobile/account/*
    │                 └── customer-visible account_events
    ├── PostgreSQL/PostGIS (sites, IoT, work, commerce)
    └── transactional integration_outbox
                            │ restricted token API
                            ▼
                         ERPNext
```

## Customer-visible scope

- organisation plan and status;
- outstanding and completed payment totals;
- order and delivery state;
- service requests;
- sites and future device/alert summaries;
- timestamps showing freshness.

Only the authenticated organisation is queried. Supplier costs, margins,
general-ledger entries, other customers and ERP administration are never exposed.
The backend provides authenticated Server-Sent Events with heartbeat; Flutter
also refreshes every ten seconds and supports pull-to-refresh.

## Production checklist

1. Provision separate PostgreSQL/PostGIS dev, staging and production databases.
2. Provision ERPNext staging under GeoVision ownership.
3. Configure company, accounts, warehouses, AOA/USD/EUR price lists and taxes.
4. Add the GeoVision idempotency custom field to synchronized document types.
5. Create a least-privilege API user and store secrets outside Git.
6. Validate Angolan fiscal requirements with a qualified accountant.
7. Run a full sandbox order and reconciliation.
8. Enable a scheduled worker and alerts for failed outbox records.

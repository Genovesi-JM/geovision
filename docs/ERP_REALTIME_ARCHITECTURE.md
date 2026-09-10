# ERP integration and real-time customer account

## Decision

Odoo 19 is the Phase 21 internal CRM/ERP target for commercial contacts,
suppliers, purchasing, inventory, invoicing and accounting. The existing
ERPNext adapter remains a provider-pinned compatibility path; changing the
configured provider never rewrites or silently reroutes its queued work.

PostgreSQL/PostGIS remains GeoVision's authoritative operational database.
Odoo and ERPNext are internal commercial/accounting projections, not identity,
asset or intelligence stores. The mobile/web applications never connect directly
to either database or ERP provider. See the complete
[Odoo 19 integration and operations contract](ODOO_19_INTEGRATION.md).

```text
Flutter app
    │ authenticated snapshot + SSE/polling
    ▼
FastAPI /mobile/account/*
    │                 └── customer-visible account_events
    ├── PostgreSQL/PostGIS (sites, IoT, work, commerce)
    ├── canonical event outbox ── event worker receipts/audit
    └── provider-pinned integration_outbox ── independent ERP worker
                                   │ provider-neutral ERP port
                                   ▼
                       Odoo 19 JSON-2 or ERPNext
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

## Synchronization rules

- A GeoVision domain transaction records the authoritative change, a
  provider-pinned `integration_outbox` command and its durable sync-request event.
- The independent ERP worker performs provider I/O after commit and outside its
  short claim transactions, using a stable idempotency key and opaque
  external-reference mapping. The event worker handles canonical receipts/facts.
- Odoo receives only the allowlisted commercial projection needed by its custom
  bridge. Assets, missions, datasets, KPIs, observations, actions, reports and
  monitoring remain exclusively authoritative in GeoVision.
- Order creation is the current automatic producer. Other allowlisted resource
  commands require an explicit owning-service producer and reviewed bridge map;
  adapter support alone is not a claim of automatic master-data synchronization.
- Signed callbacks may update only mapped invoice, stock and purchase status
  projections. They cannot create an organization binding or replace an internal
  UUID.
- Provider unavailability is represented as pending/retrying/dead-lettered work;
  it does not roll back checkout or customer intelligence.

## Production checklist

1. Provision and restore-test separate PostgreSQL/PostGIS and ERP staging data.
2. Complete [Human Gate 17](../HUMAN_GATES.md#17-odoo-19-live-erpcrm-activation),
   including the Odoo 19 Custom plan, reviewed bridge addon, dedicated bot/API
   key, signed callback and Angolan fiscal approval.
3. Configure company, accounts, warehouses, AOA/USD/EUR price lists and taxes.
4. Prove bridge-side idempotency with a repeated order and an uncertain-outcome
   reconciliation test.
5. Run order → invoice → stock/purchase callback flows and tenant/mapping negative
   tests in staging.
6. Deploy `python -m app.workers.erp_worker` and
   `python -m app.workers.event_worker` independently and alert on oldest due
   work, retries, dead letters, claim age, callback rejects and mapping drift.
7. Before changing providers, drain or reconcile work with the adapter recorded
   on each row; never relabel old rows during cutover.

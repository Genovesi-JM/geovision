# Odoo 19 integration and operations

## Status and authority boundary

Phase 21 adds Odoo 19 as an internal CRM/ERP projection behind GeoVision's
provider-neutral ERP port. It is implemented but **not live-approved**. Production
activation requires [Human Gate 17](../HUMAN_GATES.md#17-odoo-19-live-erpcrm-activation).

GeoVision remains the system of record and the only customer-facing application.
Odoo never authenticates a GeoVision customer and no web or Flutter client calls
Odoo directly.

| Information | Authority | Odoo use |
|---|---|---|
| Identity, organization membership and permissions | GeoVision | Optional internal contact reference only |
| Assets, missions, acquisitions and datasets | GeoVision | Not synchronized |
| KPI measurements, observations, actions, reports and monitoring | GeoVision | Not synchronized |
| Catalogue product/service identity and customer orders | GeoVision | Allowlisted commercial projection |
| Suppliers, purchasing, warehouse and accounting operations | Odoo internal operations, linked to GeoVision references where needed | Internal CRM/ERP workflow |
| Invoice, stock and purchase status | Odoo status projected into GeoVision | Never replaces the GeoVision UUID or order lifecycle authority |

Provider record IDs are opaque values in `erp_external_references`. The unique
GeoVision mapping key is provider, canonical resource type and internal UUID. An
Odoo ID must never be accepted as a tenant, organization, order or asset identity.

## Runtime flow

```text
GeoVision order/domain transaction
        |
        +-- authoritative PostgreSQL rows
        +-- provider-pinned integration_outbox command -- ERP worker
        |                                                    |
        |                                             ERPProvider port
        |                                                    |
        |                                          OdooAdapter (JSON-2)
        |                                                    |
        |                                  geovision.integration.bridge
        |                                                    |
        |                                       allowlisted Odoo records
        +-- erp.sync_requested event -- event worker receipt/audit

Odoo bridge/signer -- signed callback --> GeoVision callback receipt
                                             |
                                  external status projection
```

The order, line snapshot, ERP command and canonical sync-request event are
committed as one GeoVision transaction. The general event consumer validates and
acknowledges the signal without making a network call. The independent ERP worker
claims the command and performs Odoo I/O later, outside its short database
transactions.
An Odoo outage therefore leaves checkout, customer intelligence and the in-app
account available while ERP work is visibly pending, retrying or dead-lettered.

The adapter is the only component that knows the Odoo protocol. Domain services
provide canonical resource names and allowlisted values; they cannot choose an
arbitrary Odoo model or method. The configured bridge performs all related Odoo
writes in one method call.

The automatic Phase 21 producer is order creation. The ERP worker/adapter also
allow canonical `customer`, `product`, `service`, `invoice`, `payment`,
`delivery`, `supplier`, `purchase_order`, and `inventory` commands so owning
services can add explicit projections without changing the vendor boundary. This
allowlist is not itself an automatic producer or a bidirectional master-data
sync; enable a resource only when its owning service and Odoo bridge mapping have
their own tests and Gate 17 evidence.

## Outbound JSON-2 contract

GeoVision uses the Odoo 19 JSON-2 API, not the deprecated XML-RPC or JSON-RPC
interfaces:

```http
POST /json/2/geovision.integration.bridge/sync_from_geovision
Authorization: bearer <ODOO_API_KEY>
Content-Type: application/json; charset=utf-8
X-Odoo-Database: <ODOO_DATABASE>
```

The model and method can be overridden only by the validated server-side
`ODOO_BRIDGE_MODEL` and `ODOO_BRIDGE_METHOD` settings. Do not expose either
choice to an event payload or customer request. `X-Odoo-Database` is optional in
Odoo's general protocol, but GeoVision deliberately requires `ODOO_DATABASE` and
always sends the header. Pinning one reviewed database prevents host routing or a
future multi-database change from silently sending commercial data elsewhere.

The request body is one JSON object with named arguments:

```json
{
  "resource_type": "order",
  "geovision_id": "<GeoVision UUID>",
  "organization_id": "<GeoVision organization UUID>",
  "source_event": "order.created",
  "idempotency_key": "order:<uuid>:order.created:created.v1",
  "values": {
    "order_number": "GV-...",
    "currency": "AOA",
    "total_cents": 125000,
    "items": []
  },
  "context": {
    "tracking_disable": false
  }
}
```

The bridge response must contain `external_id`. It may also contain
`external_model`, `invoice_status`, `stock_status`, and `purchase_status`:

```json
{
  "external_id": "8241",
  "external_model": "sale.order",
  "invoice_status": "to invoice",
  "stock_status": "waiting",
  "purchase_status": null
}
```

GeoVision treats a missing/blank `external_id` or a non-object response as a
provider failure. Odoo error bodies and debug traces are not persisted or returned
to clients. Authentication failures, validation failures, rate limits, timeouts
and provider unavailability are normalized by the adapter.

### Required Odoo-side bridge behavior

The GeoVision repository does not install or configure the target Odoo database.
A reviewed Odoo addon must define the public model method above and must:

- allow only the agreed canonical resource types and fields;
- validate every GeoVision UUID, organization relationship, money/currency value
  and line item instead of passing arbitrary payload keys to Odoo models;
- enforce a unique idempotency key and return the same logical result for an
  identical retry;
- atomically find/create/update all related Odoo records inside this single
  method call;
- keep the GeoVision UUID on the Odoo-side integration mapping and return only
  the normalized response fields above;
- use ordinary Odoo ORM access checks and avoid `sudo()` unless a separately
  reviewed, narrowly scoped operation makes it unavoidable; and
- emit no asset, mission, dataset, KPI, observation, action, report or monitoring
  data.

Odoo documents that every JSON-2 call is its own SQL transaction and recommends
one method for related operations. That is why GeoVision calls one bridge method
instead of chaining generic model calls.

## Signed Odoo status callback

The reviewed Odoo addon or an equally trusted server-side signer sends status
changes to:

```http
POST /integrations/erp/odoo/callback
Content-Type: application/json
X-GeoVision-Timestamp: <Unix seconds>
X-GeoVision-Signature: sha256=<lowercase HMAC-SHA256 hex digest>
```

The callback body is:

```json
{
  "event_id": "<stable Odoo event identifier>",
  "event_type": "invoice.status",
  "resource_type": "order",
  "geovision_id": "<GeoVision UUID>",
  "external_id": "8241",
  "external_model": "sale.order",
  "invoice_status": "invoiced",
  "stock_status": "done",
  "purchase_status": null
}
```

`event_type` is one of `order.status`, `invoice.status`, `stock.status`, or
`purchase.status`. Callback status projections are accepted only for `order`,
`invoice`, `product`, `service`, `purchase_order`, or `inventory`, and at least
one of the three status fields must be present.

The signature key is `ODOO_WEBHOOK_SECRET`. The signed bytes are the ASCII/UTF-8
timestamp value, one period byte (`.`), and the exact raw HTTP body bytes, in that
order:

```text
HMAC-SHA256(secret, timestamp_bytes + b"." + raw_body_bytes)
```

The sender must sign the bytes before transmission and must not reserialize JSON
after signing. GeoVision verifies the digest in constant time before trusting the
JSON, rejects timestamps outside `ERP_CALLBACK_REPLAY_WINDOW_SECONDS` (300
seconds by default), and requires the configured secret. Keep clocks synchronized.

The pair `(provider, event_id)` is the replay key and the raw body SHA-256 is
retained for audit without retaining the raw payload. A valid callback can update
only the mapped external projection's allowlisted invoice, stock and purchase
status fields. The `geovision_id`, resource type and external reference must
match the existing Odoo mapping; the callback cannot create a new tenant binding,
change ownership or update core intelligence.

Odoo Studio documents outbound POST webhook notifications, but its public Odoo
19 documentation does not specify this HMAC header contract. Therefore a generic
unsigned Studio webhook is not sufficient. This is a GeoVision security inference:
use the reviewed custom addon or a trusted gateway that signs the exact bytes and
preserves the stable event ID.

## Retry, dead-letter and reconciliation runbook

Run the ERP worker independently from API replicas. Also run the general event
worker so request/result facts receive their normal receipts and downstream
consumers:

```bash
cd backend
python -m app.workers.erp_worker
python -m app.workers.event_worker
```

`python -m app.workers.erp_worker --once` performs one bounded release/operations
cycle. The ERP worker uses short leases, recovers expired claims, revalidates the
command, releases database locks before provider I/O, honors the provider recorded
when each command was created, and applies bounded retry/backoff. A provider
change never reroutes old work. Command states are `pending`, `processing`,
`failed` (scheduled retry), `completed`, and `dead_letter`; legacy
`failed_terminal` is accepted for controlled requeue. New commands snapshot
`INTEGRATION_RETRY_ATTEMPTS`; migrated existing rows default to three attempts,
and changing a process setting later does not rewrite queued rows.

Monitor both layers:

- `GET /integrations/erp/status` shows the authenticated organization's provider,
  pending/retrying/dead-letter counts, provider split and oldest due work;
- `GET /integrations/erp/outbox` lists that organization's safe command state;
- `GET /integrations/erp/references/{resource_type}/{internal_id}` returns a
  tenant-filtered sync/status projection without exposing the Odoo ID;
- `POST /integrations/erp/outbox/{outbox_id}/requeue` requeues one reviewed ERP
  dead letter and resets its command attempt budget;
- `python -m app.workers.erp_worker --requeue <OUTBOX_ID>` is the server-side
  equivalent for an operator with deployment access;
- the legacy administrator `POST /integrations/erp/sync` performs one compatible
  in-process cycle; and
- `/integrations/events/*` separately exposes the canonical event queue, receipts
  and attempts. Requeuing a canonical event does not requeue an ERP command.

The provider object returned by ERP status is a secret-free configuration
summary, not a live JSON-2 probe. Gate 17 requires a real bridge call and callback
test before treating Odoo as reachable.

Do not blindly requeue a timeout. First use the GeoVision idempotency key and
mapping to determine whether Odoo committed the bridge transaction. Provider-side
idempotency makes a byte-for-byte logical retry safe; without verified uniqueness,
an unknown outcome requires manual reconciliation. Correct credentials, bridge
validation or downstream data first, record the reconciliation decision, and then
requeue the ERP command. Never edit the authoritative order UUID or substitute
an Odoo ID to make a retry pass.

Alert on oldest due command, claim age, retries, terminal/dead-letter count,
authentication errors, rate limits, latency, callback rejection/replay count,
mapping mismatch and callback age. Never log API keys, webhook secrets,
authorization/signature headers, raw Odoo debug responses or unrestricted
commercial payloads.

## Live setup and API-key rotation

1. Use an Odoo 19 **Custom** plan. Odoo documents that its external API is not
   available on One App Free or Standard plans.
2. Start with a duplicate/staging database. Confirm Odoo 19 via `/web/version`
   and inspect the database-specific `/doc` page for the installed bridge model
   and method.
3. Install and review the GeoVision bridge addon. Verify its resource/field
   allowlist, unique idempotency constraint, company scoping, callback signer and
   tests before granting network access.
4. Create a dedicated integration bot. Give it only the ACLs, record rules,
   companies and fields required by the bridge. Odoo record rules are
   default-allow after access rights grant an operation, so explicitly audit the
   resulting access rather than assuming an absent rule denies it.
5. Generate a dedicated API key with a clear description and expiry. Odoo permits
   at most three months; rotate it at least that often and immediately on suspected
   disclosure. Its value is shown once, so place it directly in the server secret
   manager.
6. Configure GeoVision server/workers only:

   ```dotenv
   ERP_PROVIDER=odoo
   ODOO_BASE_URL=https://odoo.example.invalid
   ODOO_DATABASE=geovision-staging
   ODOO_API_KEY=<secret>
   ODOO_WEBHOOK_SECRET=<independent high-entropy secret, at least 32 characters>
   ODOO_BRIDGE_MODEL=geovision.integration.bridge
   ODOO_BRIDGE_METHOD=sync_from_geovision
   ERP_WORKER_POLL_SECONDS=5
   ERP_WORKER_BATCH_SIZE=50
   ERP_WORKER_CLAIM_TIMEOUT_SECONDS=300
   ERP_CALLBACK_REPLAY_WINDOW_SECONDS=300
   ```

7. Restrict egress to the exact HTTPS Odoo origin and restrict callback ingress
   at the edge. Keep TLS verification enabled and synchronize both clocks.
8. Complete Gate 17, including Angolan fiscal/accounting review, before production
   activation.

For a planned API-key rotation, create the replacement key first, update the
secret manager, roll/restart every ERP worker and any API replica that can
resolve the adapter, verify a new staging sync, and only then revoke the prior
key. Record the expiry owner and next rotation date. GeoVision currently selects
one active `ODOO_API_KEY`; overlap is achieved by keeping the old Odoo key valid
until all processes have loaded the replacement, not by storing two keys in the
application.

## Cutover and rollback

- Inventory all pending/retrying/dead-lettered ERPNext rows before selecting
  Odoo. Drain or reconcile them with ERPNext; do not relabel their `provider`.
- Back up and restore-test GeoVision and Odoo staging data before the migration.
- Select `ERP_PROVIDER=odoo` only after bridge, callback and representative
  commercial flows pass Gate 17. New commands pin to Odoo; old rows stay pinned
  to their original provider.
- On rollback, stop new Odoo-producing work, restore the previous provider for
  new commands, retain the Odoo adapter/secret long enough to reconcile already
  accepted commands and callbacks, and never delete external mappings as a
  shortcut.
- Odoo downtime is not a reason to roll back GeoVision customer functionality.
  Keep the authoritative application operating and recover the projection later.

## Official Odoo 19 references

Verified on 2026-09-10 against official Odoo documentation only:

- [External JSON-2 API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html): endpoint/headers, named arguments, API-key lifecycle, Custom-plan requirement, access controls, per-call transactions, dynamic `/doc`, and migration away from XML-RPC/JSON-RPC.
- [Security in Odoo](https://www.odoo.com/documentation/19.0/developer/reference/backend/security.html): access rights, record rules, field restrictions and public-method/security pitfalls.
- [Odoo 19 automation rules](https://www.odoo.com/documentation/19.0/applications/studio/automated_actions.html) and [webhooks](https://www.odoo.com/documentation/19.0/applications/studio/automated_actions/webhooks.html): outbound POST automation capabilities and the warning to validate webhook configuration on a duplicate database.

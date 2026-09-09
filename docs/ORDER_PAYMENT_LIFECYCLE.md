# GeoVision commercial order and payment lifecycle

Phase 8 establishes one GeoVision-owned commercial core for physical products,
field/remote services, monitoring plans, and mixed orders. GeoVision remains the
seller and service provider. There are no seller accounts, marketplace payouts,
contractor payouts, bids, or customer-to-supplier payment flows.

## Identity and ownership

`orders.id` is an immutable GeoVision UUID. `order_number` is a human reference;
neither it nor a payment-provider reference is a primary key. A canonical order
records its customer, organization, workspace, optional site, currency, totals,
and a snapshot of every catalogue line. The compatibility `company_id`,
`site_id`, `product_id`, and `status` fields remain while older clients migrate.

`order_items.catalog_item_id` points to the Phase 7 first-party catalogue.
`pricing_snapshot_json` retains the code, name, type, price model, currency,
unit amount, quantity, discount, tax rate, and capture time used for the sale.
Later catalogue edits therefore cannot rewrite an existing commercial record.
`fulfilment_hints_json` carries scheduling, site, duration, and fulfilment hints
without starting operational work.

Customer reads are owner-scoped. Organization finance roles may read/manage
organization payments through their explicit `billing:read`/`billing:manage`
permissions. Internal order operations require an explicit GeoVision staff role:
`GV_SUPER_ADMIN`, `GV_OPERATIONS`, `GV_SALES`, `GV_FINANCE`, or
`GV_INVENTORY`, depending on the endpoint. Missing and foreign resources return
the same not-found response.

## Separate state machines

Fulfilment is authoritative in `orders.fulfilment_status`:

`DRAFT → QUOTED → CONFIRMED → PAYMENT_AUTHORIZED/PAID → SCHEDULING →
ASSIGNED → IN_PROGRESS → DATA_UPLOADED → PROCESSING → QA_REVIEW →
RESULTS_READY → DELIVERED → COMPLETED`

Reviewed branches support `CANCELLED`, `FAILED`, `NEEDS_REFLIGHT`, and
`ON_HOLD`. Terminal states cannot be reopened. Exceptional transitions require
a reason, stale `expected_version` updates fail with a conflict, and advancing
into paid work requires provider-reported authorization, settlement, or an
explicit zero-value `NOT_REQUIRED` payment state.

Settlement is authoritative in `orders.payment_status`:

- `NOT_REQUIRED`
- `PENDING`
- `AUTHORIZED`
- `PAID`
- `FAILED`
- `CANCELLED`
- `PARTIALLY_REFUNDED`
- `REFUNDED`

Payment events may advance the pre-fulfilment milestone to
`PAYMENT_AUTHORIZED` or `PAID`; they never silently start scheduling,
processing, delivery, or completion. Refunds update settlement without erasing
what was fulfilled. `orders.status` remains a derived compatibility projection
for older web/mobile clients.

## Provider boundary and settlement truth

Every live create, status, refund, and signature-verification operation passes
through the billing module's `PaymentProvider` interface. Existing Multicaixa,
Stripe/card, IBAN, and PayPal implementations are compatibility adapters behind
that interface. Tests inject provider fakes without loading gateway SDKs.

Missing gateway credentials produce simulated responses only in local/dev/test.
Deployed profiles fail closed. The storefront advertises only configured gateway
methods; IBAN remains a manual settlement path. PayPal webhook verification and
API-backed refunds remain unavailable in deployed mode and must not be reported
as live capabilities.

Payment creation derives organization, amount, currency, description, and order
identity from the owned GeoVision order. Client-supplied mismatches are rejected.
An idempotency key is bound to that immutable request tuple; reuse for another
tenant, order, amount, currency, or provider is a conflict.

## Webhook idempotency

Signatures are verified before JSON is interpreted or any receipt is stored.
`payment_webhook_events` keeps only the provider, provider event ID (or a
deterministic SHA-256 fallback), payload digest, references, outcome, and
timestamps. It never stores the raw payload or signature. A unique
`(provider, event_id)` constraint means repeated delivery returns the original
receipt and cannot duplicate payment updates, order events, or lifecycle
effects. Stale events cannot reverse a completed/refunded payment.

An older enterprise prototype table did store complete payloads. The migration
renames it to `legacy_payment_webhook_events`, preserving every historical row
for an explicit retention/security review while ensuring new callbacks use the
digest-only ledger. Downgrade restores the historical name and data.

## APIs

Customer routes:

- `POST /orders/checkout/{cart_id}` with optional `Idempotency-Key`
- `GET /orders`
- `GET /orders/{order_id}`
- `POST /orders/{order_id}/cancel`

GeoVision staff routes:

- `POST /orders/internal` creates a priced or quoted draft from catalogue items
- `GET /orders/internal`
- `GET /orders/internal/{order_id}`
- `PATCH /orders/internal/{order_id}/fulfilment`

Legacy `/shop/checkout`, `/shop/orders`, `/orders/orders`, and `/payments`
paths remain available. Shop checkout now writes canonical ownership/state and
catalogue snapshots. The legacy customer cancellation path now authenticates
and checks ownership. Payment reads/lists are tenant-filtered, and payment
creation can no longer choose another organization's ID or a different amount.

## Migration and rollback

`commercial_order_lifecycle_v1` is additive. It backfills lifecycle/payment
state from legacy order and payment values, links resolvable catalogue items,
builds immutable pricing snapshots, leaves unresolvable legacy references in
place, and retains every old order/payment row. A preflight rejects non-positive
historical payment amounts rather than silently modifying financial data.

The verified rollback drops only Phase 8 fields and the new digest ledger. It
restores the renamed enterprise webhook table and retains orders, order items,
payments, catalogue records, and provider references. Production cutover still
requires the backup/restore rehearsal and sign-off tracked in the risk register.

## Acceptance coverage

Automated coverage proves that:

- physical and service lines share one order and snapshot model;
- checkout retries do not duplicate orders or provider calls;
- swapping a fake provider does not change GeoVision order/payment IDs;
- repeated webhooks create one receipt and one settlement/order effect;
- stale and invalid fulfilment transitions fail closed;
- unpaid work cannot skip into operational execution;
- customer and payment ownership cannot cross tenants; and
- SQLite migration, downgrade, and re-upgrade preserve historical commerce.

The Phase 8 application contract contains 250 HTTP/WebSocket routes with route
SHA-256 `ac89aacc0091bbd4a170aae9f4ecef70987f9db831afcd27e53bab0673f41d8d`.
Its canonical JSON OpenAPI SHA-256 is
`e451e9c0d2c1c7605260b020b83e5c45f49330158f0eb1fc52cf0d7e197d1fa8`.

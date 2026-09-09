# GeoVision first-party catalogue

Phase 7 replaces the two historical product stores with one canonical commercial
contract. GeoVision is the merchant of record for every published item. There is
no public seller account, provider bid, contractor storefront, seller payout, or
customer-to-supplier relationship.

## Canonical item

`catalog_items` represents all offers with one identifier and one publication
lifecycle. Its supported types are:

- `PHYSICAL_PRODUCT`
- `SERVICE`
- `MONITORING_PLAN`
- `INSTALLATION`
- `INSPECTION`
- `ANALYSIS`

Each row has sector and asset-type applicability, customer-safe content,
deliverables, a price model, minor-unit multi-currency prices, availability,
recommendation triggers, and optional fulfilment/installed-product hints. The
five normalized sector values are `AGRICULTURE`, `INFRASTRUCTURE`,
`ENVIRONMENTAL`, `MINING`, and `PORTS_INDUSTRIAL`; the schema remains extensible
for reviewed future sectors and asset types.

Only `PUBLISHED` rows appear through the customer API. `DRAFT`, `UNAVAILABLE`,
and `ARCHIVED` remain visible only to authorized GeoVision staff. Non-quote
items cannot be published without a non-negative price in integer minor units.
Credential-like keys are rejected in catalogue metadata and recommendation
triggers.

## APIs and permissions

Customer-safe routes:

- `GET /catalog/items`
- `GET /catalog/items/{id-or-slug-or-code}`

The list supports `item_type`, `sector`, `asset_type`, and `search` filters.
Public responses never contain procurement contacts, supplier IDs, internal
notes, internal metadata, or legacy migration details.

Internal routes live under `/catalog/internal`. `GV_SUPER_ADMIN`,
`GV_INVENTORY`, `GV_SALES`, and `GV_OPERATIONS` may list/create/update items and
internal procurement suppliers. Customer organization roles do not imply any
catalogue-management permission.

Suppliers are stored in `procurement_suppliers`. This is deliberately a private
procurement record, not an identity that can publish or sell. Phase 9 may expand
qualification and purchasing fields without changing the public catalogue.

## Compatibility and migration

The migration imports every `shop_products` and `products` row without deleting
or rewriting its source record. Legacy source identifiers are retained for
audit and rollback. Active offers become published; inactive/standby offers are
archived.

Existing consumers may continue to use `/shop/products`, `/shop/cart`, and the
legacy `/products` and `/admin/products` routes during cutover:

- `/shop/products` is now a read projection of canonical published items.
- canonical writes maintain a `shop_products` checkout projection with the same
  item ID, so existing carts and order snapshots continue to work.
- old admin creates/updates write through to the canonical record.
- old admin delete now archives instead of deleting commercial history.
- the browser sector preference reads the historical
  `gv_marketplace_sector` key once and writes `gv_catalog_sector` thereafter.

The historical `marketplace` recommendation action value remains only as a
serialized compatibility alias until Phase 17 migrates action contracts. It
means “open the GeoVision catalogue”; it never means route work or money to an
external seller.

## Downstream hooks

`fulfilment_type` tells later order phases whether an item can result in a
shipment, field service, installation, remote analysis, monitoring activation,
or another reviewed fulfilment template. `installed_product_type` lets a later
completed order create a registered device/product asset. Neither field starts
fulfilment by itself; Phase 8 owns the order lifecycle and Phase 10 owns jobs.

## Verification

Phase 7 acceptance covers:

- all six offer types in one table and API;
- published-only customer browsing and filters;
- internal-role authorization and customer denial;
- private supplier data;
- metadata secret rejection and price publication rules;
- non-destructive legacy archive behavior;
- shop/cart compatibility; and
- absence of public seller, vendor, bidding, or contractor-storefront routes.

The Phase 7 application contract contains 242 HTTP/WebSocket routes with route
SHA-256 `04b52b24c9ffa8df43d4a1e893d672d448cb0c9a5124810f9b14241cc5e880c6`.
Its canonical JSON OpenAPI SHA-256 is
`0717d1701a219b674e1efde0fdba8f4246485740b15dc60a35abd8c684466016`.

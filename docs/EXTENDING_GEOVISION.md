# Extending GeoVision safely

New capabilities should use the existing identity, organization/workspace,
Asset, acquisition, dataset, intelligence, action, report, catalogue, order,
fulfilment, event, and notification cores. A vertical or vendor does not get a
parallel architecture.

## Add a sector

1. Create `backend/app/sectors/<sector>` implementing the sector module
   contract. Declare only existing common-module dependencies.
2. Define normalized Asset types and aliases. Do not add vertical-only identity
   or workspace tables.
3. Register versioned KPI definitions/calculators and cautious rules through
   `app.modules.analytics`. Use explicit UNKNOWN/needs-review behavior when
   evidence is incomplete.
4. Build observations and actions through the common persistence services.
   Recommendations may reference GeoVision catalogue items, never a public
   third-party seller.
5. Build map layers and report context through the shared Asset and report
   contracts. Narrative can explain validated structured results but cannot
   create measurements.
6. Add a clearly synthetic fixture with mission, dataset, KPI, observation,
   action, and report history.
7. Add the package exactly once to `app/sectors/registry.py`; use the canonical
   `geovision.sectors.<sector>` rollout decision.
8. Test coexistence, fixture determinism, tenant/workspace isolation, failure
   semantics, report provenance, and route uniqueness. Update the product and
   provider catalogues.

## Add a sensor or device capability

1. Add the channel/measurement unit to the IoT registry and schema.
2. Normalize authenticated REST, signed MQTT, or reviewed cloud ingress into
   the same versioned receipt boundary.
3. Map in-order numeric readings to the shared technical KPI projection and
   new alerts to common observations/actions. Preserve receipt idempotency and
   skip decision projection for old out-of-order replay.
4. For commands, require declared capability, explicit remote-control opt-in,
   confirmation, reason, expiry, and safe/fail-safe state. Keep local hardware
   interlocks authoritative.
5. Test duplicate message/provider identity, stream sequence collision,
   store-and-forward age, tenant assignment, offline detection, and customer
   visibility.

## Add an external provider

1. Put the provider-neutral port in the domain that needs it. Do not read
   credentials or import a vendor SDK from domain or sector code.
2. Implement the concrete adapter under `backend/app/integrations/<capability>`
   and load it lazily from a factory.
3. Add typed, redacted configuration in `app/core/config.py`. Deployed profiles
   must fail closed; deterministic fakes remain local/test only.
4. Keep the GeoVision UUID authoritative and store the provider ID as an opaque
   external reference.
5. Return normalized safe results. Bound timeouts, response sizes, retries, and
   error text. Retry writes only after provider-side idempotency is proven.
6. If customer-controlled, register the reviewed family/provider/capabilities,
   require Key Vault references, and enforce membership, entitlement,
   connection, rollout, and operation gates independently.
7. Test success and every important failure without network access, then run a
   separately approved live sandbox rehearsal.
8. Update `INTEGRATION_PROVIDER_CATALOG.md`, deployment variables, health
   checks, human gates, rollback, and data migration plan before activation.

## Add a first-party service

1. Add or version a GeoVision-owned catalogue item and price snapshot rules.
2. Map the item to an existing fulfilment-job template and required private
   capabilities. Do not expose contractors as sellers.
3. Link the order/job to the canonical Workspace and Asset, then reuse missions,
   datasets, processing, reports, notifications, and ERP projection.
4. Add a service-first onboarding test when the customer can arrive after work
   starts.

## Definition of done

The extension has no duplicate core entity, preserves tenant isolation and
least privilege, uses an additive Alembic migration for persisted changes,
emits canonical events, documents provider/live gates honestly, and passes the
full backend, browser, mobile, migration, security, and container release gates
appropriate to its surface.

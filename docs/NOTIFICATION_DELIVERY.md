# Contextual notifications and external delivery

## Purpose

Phase 20 turns customer-facing events into a durable in-app history and, when
enabled, separate email or push deliveries. A provider outage cannot roll back
the report, action, order, service update, invitation, or device event that
caused a notification.

GeoVision owns notification identity and navigation. Provider message IDs,
installation identifiers, and credentials never become GeoVision primary IDs.
Push messages contain only a notification ID; the authenticated API resolves
the destination again when the customer opens it.

## Runtime flow

```text
owning domain transaction
  -> operational_domain_events
  -> event worker / notification_materializer_v1
  -> notifications + notification_event_links
  -> notification_deliveries
  -> independent notification worker
  -> SMTP or Azure Notification Hubs

customer inbox/tap
  -> authenticated notifications API
  -> current membership + permission + target-state check
  -> server-generated app_path / portal_path
```

The event worker materializes the inbox row and external-delivery projections
in one database transaction with its consumer receipt. Provider I/O is not
performed in that transaction. The notification worker claims a bounded batch,
commits the claim, revalidates the recipient and preference state, releases the
database transaction, calls the provider, and then records the outcome.

Invitation creation is the deliberate special case. The API stages the
pre-account notification and its email delivery in the same transaction as the
invitation, while the one-time token is available. Token-bearing URLs exist
only in a Fernet-encrypted delivery payload with a SHA-256 integrity digest. If
a valid `ENCRYPTION_KEY` is unavailable, the external delivery is marked
`SUPPRESSED`; the token is never stored through the local `plain:` fallback.
After acceptance, the notification is rebound to the authenticated user so it
can remain in that user's history.

Both of these processes are required in deployed environments:

```bash
python -m app.workers.event_worker
python -m app.workers.notification_worker
```

Use `--once` on either worker for a bounded release check. Do not run provider
delivery inside every API replica.

## Persistence and ownership

| Record | Purpose |
|---|---|
| `notifications` | Provider-neutral inbox item, recipient, organization/workspace, category/type, safe typed target, severity, occurrence count, read state and correlation |
| `notification_event_links` | Unique source-event/recipient linkage, including every event folded into an aggregate |
| `notification_preferences` | Global or per-organization category policy for in-app, push, email, SMS, minimum severity and quiet hours |
| `notification_endpoints` | Authenticated installation registration; the APNs/FCM token is encrypted and digested, and lifecycle changes are audited |
| `notification_deliveries` | Channel/provider-pinned claim, retry, suppression, acknowledgement and dead-letter state |

`recipient_key` is an opaque `user:<id>` or `invitation:<id>` correlation key,
not an email address. The APNs/FCM token is protected at rest. The installation
ID remains an operational routing identifier, so database access, exports and
retention must treat endpoint rows as personal operational data.

The inbox record is independent from its external deliveries. Disabling an
in-app category hides matching rows but does not delete their history. A failed
or dead-lettered SMTP/push attempt likewise does not delete or unread the inbox
item.

## Event catalogue

The `notification_materializer_v1` consumer handles these canonical facts:

| Source event | Customer notification | Context target | Aggregation |
|---|---|---|---|
| `invitation.created` | Existing workspace invitation | Accepted invitation/workspace | One per event/recipient |
| `report.published` | “Your results are ready” | Exact published report | One per event/recipient |
| `action.requested` | Action ready for review | Exact action | Same open action for 15 minutes |
| `device.alert_triggered` | Field or critical alert | Assigned Asset | Same device/rule for 15 minutes |
| `device.offline_detected` | Device stopped reporting | Assigned Asset | Same device for 15 minutes |
| `fulfilment_job.schedule_changed` | Service schedule updated | Owning customer order | One per event/recipient |
| `fulfilment_job.state_changed` | Service status updated | Owning customer order | One per event/recipient |
| `order.created` | Order received | Exact order | One per event/recipient |
| `order.state_changed` | Customer-visible order update | Exact order | One per event/recipient |
| `shipment.state_changed` | Shipment status updated | Exact order/shipment context | One per event/recipient |

Materialization derives customer text, severity, scope and target from current
GeoVision records rather than trusting event-provided titles or URLs. Replaying
the same event for the same recipient returns the existing row. The database
also enforces unique notification and delivery idempotency keys.

For aggregated device/action events, every source event is linked to the same
inbox item, `occurrence_count` increases, the item becomes unread again, and the
15-minute window extends. Aggregation does not enqueue another external
delivery, preventing telemetry bursts from becoming push/email bursts.

`notification.created`, `notification.delivered`, and
`notification.delivery_failed` are reserved canonical vocabulary. The current
worker persists delivery state directly and does not yet publish those three
lifecycle facts; consumers must not depend on them until an owning service
emits them transactionally.

## Inbox and preference API

All routes require an authenticated GeoVision session:

- `GET /notifications` — filtered, paginated inbox and unread count;
- `GET /notifications/unread-count` — lightweight unread count;
- `POST /notifications/{id}/read` — idempotently mark one visible item read;
- `POST /notifications/read-all` — mark the current user's visible items read;
- `GET /notifications/{id}/target` — reauthorize and resolve safe app/portal
  paths;
- `GET /notification-preferences` and `PUT /notification-preferences` — read
  and upsert global or organization/category policy;
- `PUT /notification-endpoints/{installation_id}` and
  `DELETE /notification-endpoints/{installation_id}` — register, rotate or
  revoke an authenticated installation.

Preferences support `INFO`, `WATCH`, `WARNING`, and `CRITICAL` minimum
severity. Quiet hours use paired `HH:MM` values and an IANA timezone. Global
policy is the fallback; a matching organization policy takes precedence.
Channel and severity policy is checked at materialization and again immediately
before delivery, so a newly revoked membership, endpoint, or preference takes
effect while work is queued. Quiet hours defer rather than consume an attempt.

SMS is represented in the domain and preference contract, but no SMS adapter
is active. It must remain disabled until a separately approved provider and
live verification gate are added.

## Contextual-target security

Persist only `target_type` and an internal GeoVision `target_id`; never persist
an arbitrary client/provider URL. When resolving a target, the API verifies all
of the following again:

- the notification belongs to the authenticated user;
- organization and optional workspace memberships are still active;
- the current role grants the required permission;
- the target still belongs to the same organization/workspace;
- reports are still `PUBLISHED`, Assets are not archived, and customer orders
  belong to the intended customer unless an internal role is acting;
- accepted invitation context belongs to the same identity.

Missing or unauthorized notifications and targets return the same not-found
surface. A push payload carries only `notification_id`, so a forged or stale
device-side path cannot bypass these checks. The client must call the target
endpoint after authentication and accept only the returned allowlisted relative
path.

## Providers and delivery states

Email delivery rows are pinned to `smtp`, local `file`, or disabled state when
materialized. Push rows are pinned to the provider registered on the endpoint;
the implemented live adapter is `azure_notification_hubs`. Changing a default
does not silently rename pending rows.

Flutter includes a fail-closed `NativePushProvider` boundary. It requests the
APNs/FCM token through the `com.geovision.notifications/push` method channel and
accepts tap data through the `com.geovision.notifications/push_taps` event
channel. Supported non-demo selectors use that boundary; if the signed host
does not implement it, registration returns no token and never falls back to a
mock endpoint. The iOS/Android host handlers, platform credentials/configuration
files and physical-device verification remain Gate 16 work.

The authenticated endpoint API encrypts and digests the platform token. Before
each Azure delivery, the worker decrypts and validates that token. The Azure
Notification Hubs adapter then idempotently creates or updates the installation
for the stored opaque installation ID, platform and APNs/FCM v1 token before it
sends the targeted `geovision` template. The application payload contains only
`{"notification_id":"..."}`. SMTP sends plain-text messages with a stable
`X-GeoVision-Delivery-ID` header and requires verified STARTTLS in staging and
production. The local durable sink records only timestamp, delivery ID,
notification ID and channel in `backend/notification_delivery_log.txt`; it is
not a production provider.

Delivery states are:

```text
PENDING -> PROCESSING -> DELIVERED
                    \-> RETRY -> PROCESSING
                    \-> SUPPRESSED
                    \-> DEAD_LETTER
```

Stale claims return to `RETRY` until their attempt budget is exhausted. Provider
timeouts, throttling and server errors use bounded exponential backoff; explicit
provider rejection, invalid payload, missing configuration, exhausted attempts,
or repeatedly expired claims become terminal. Stored error text is sanitized.

External delivery is at least once. A process can stop after a provider accepts
a message but before GeoVision records `DELIVERED`; SMTP and Azure Notification
Hubs do not prove provider-side deduplication from GeoVision's database key.
Templates and customer wording must tolerate an occasional duplicate, and
operators must reconcile uncertain outcomes rather than assuming exactly once.

## Configuration

The complete variable list and fail-closed behavior are in
[`backend/ENV_CONFIG_GUIDE.md`](../backend/ENV_CONFIG_GUIDE.md). At minimum:

```dotenv
NOTIFICATION_PROVIDER=smtp
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_TLS=true
SMTP_TIMEOUT_SECONDS=15

AZURE_NOTIFICATION_HUBS_NAMESPACE=
AZURE_NOTIFICATION_HUBS_HUB_NAME=
AZURE_NOTIFICATION_HUBS_SAS_KEY_NAME=
AZURE_NOTIFICATION_HUBS_SAS_KEY=
NOTIFICATION_DELIVERY_TIMEOUT_SECONDS=10

NOTIFICATION_WORKER_POLL_SECONDS=5
NOTIFICATION_WORKER_BATCH_SIZE=50
NOTIFICATION_WORKER_CLAIM_TIMEOUT_SECONDS=300
NOTIFICATION_WORKER_RETRY_BASE_SECONDS=30
NOTIFICATION_WORKER_RETRY_MAX_SECONDS=3600
```

Endpoint registration and token-bearing invitation delivery also require a
valid, stable Fernet `ENCRYPTION_KEY`. Store SMTP and Azure credentials in the
server-side secret manager. Never put them in a mobile build, push payload,
event, notification body, audit detail or checked-in environment file.
The Azure SAS policy is backend-only and must grant the registration/listen and
send rights needed for installation updates and targeted sends; do not embed a
full-access or server send credential in either mobile binary.

## Operations and recovery

Monitor at least the following, split by provider and channel:

- due `PENDING`/`RETRY` count and age of the oldest due row;
- `PROCESSING` rows past their lease and claim-loss frequency;
- delivery success, retry, suppression and dead-letter counts/rates;
- stable `last_error_code` distribution, without exporting message content;
- provider latency, timeout, throttling, rejection and authentication errors;
- active/revoked endpoint counts and repeated endpoint-unavailable suppression;
- notification creation and aggregation rates by type/severity;
- event-worker dead letters for `notification_materializer_v1`;
- invitation issue-to-delivery-to-accept conversion using IDs only.

An in-app item remains available during an external outage, so restore provider
connectivity before modifying business records. Correct configuration or data,
then requeue one reviewed dead letter:

```bash
python -m app.workers.notification_worker --requeue DELIVERY_ID
python -m app.workers.notification_worker --once
```

Do not bulk requeue until the failure code, provider health and potential
customer impact are understood. Requeue resets the attempt budget but preserves
the same delivery/idempotency identity. Never requeue a suspected uncertain
provider success merely to make the database green.

Before production activation, complete
[Gate 16](../HUMAN_GATES.md#16-live-email-and-mobile-push-activation) for real SMTP plus APNs/FCM
through Azure Notification Hubs, including signed native host channel/plugin
implementation, platform configuration and physical-device verification. A
configured server adapter or successful health endpoint is not evidence of live
external delivery.

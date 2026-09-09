# Invitation-first onboarding and deep links

Phase 6 adds a secure route into work that GeoVision has already created. A
recipient can authenticate, accept an invitation, and open an existing
workspace, asset, report, service result, or order. Acceptance never creates a
replacement asset or result.

## Lifecycle and persisted data

`Invitation` belongs to one organization and one active workspace. It records:

- a SHA-256 token digest and a short non-secret support prefix (never the clear
  bearer token);
- the normalized target email and optional non-authoritative identity hint;
- the intended customer role, target type/ID, inviter, expiry, status, and
  acceptance/revocation timestamps;
- a link to the pending organization membership; and
- bounded, JSON-only metadata that rejects secret-like keys.

Statuses are `pending`, `accepted`, `revoked`, and `expired`. A portable unique
pending-email key closes concurrent double-issue races and is cleared on every
terminal transition so a later deliberate reissue remains possible. Tokens contain at
least 256 bits of randomness, are returned only by the creation response, and
are never retrievable later. Creation rejects a second live invitation for the
same organization/email. Revoke is idempotent while pending. An accepted token
is idempotent only for the same authenticated GeoVision user and cannot grant
access to another user.

Organization ownership is deliberately not invitable. Ownership must use the
separate authenticated transfer procedure so possession of an email link can
never silently transfer the last-owner invariant.

## Email mismatch policy

The acceptance service derives identity only from the validated GeoVision
session. It ignores client-supplied user IDs and email claims. The normalized
email on that internal identity must exactly match the invitation target.

On mismatch, the API returns `403 authenticated_email_mismatch` and grants
nothing. There is no administrator override parameter. The safe recovery is to
sign in with the invited identity or revoke and reissue to the corrected email.
This makes the policy explicit and auditable.

## API contract

| Method and path | Authentication | Purpose |
|---|---|---|
| `POST /invitations` | organization member manager | Issue a one-time invitation; clear token is returned once with `Cache-Control: no-store` |
| `GET /invitations?organization_id=…` | organization member manager | List redacted invitation records; clear tokens are never returned |
| `POST /invitations/preview` | public | Validate a token in the request body and return a masked email plus organization/workspace destination |
| `POST /invitations/accept` | authenticated identity | Bind the session identity, activate exact role/workspace access, and return the allowlisted destination |
| `POST /invitations/{id}/revoke` | organization member manager | Revoke an unused invitation |
| `GET /onboarding/options` | public | Return the four service-first choices |
| `POST /onboarding/intent` | optional session | Resolve a choice to the next client route; invitation preview remains token-bound |
| `GET /onboarding/context` | authenticated identity | Return completion state, membership IDs, and the count of matching live invitations |

The four intent identifiers are `request_service`, `monitor_asset`,
`buy_product`, and `view_invitation`. These are outcomes, not account types.
The server privately maps the first three to compatible starter-workspace
defaults so older data structures continue to work. `view_invitation` never
creates a starter organization or workspace; the client calls
`/invitations/accept` instead.

Legacy callers may continue sending `customer_type`, sector, and use-case
fields to `/auth/register` or `/auth/onboarding`. New browser and Flutter flows
send `intent`. This is an additive compatibility transition.

## Target validation and destinations

The server constructs destinations; clients cannot submit redirect paths.
Before issue and again before acceptance it proves that the workspace and
target are active and belong to the invitation organization. Cross-tenant UUIDs
return a non-disclosing `404`.

| Target | Canonical destination |
|---|---|
| workspace | `/portal` |
| asset | `/assets/{asset_id}` |
| report | `/reports/{document_id}` |
| service result | `/work/{request_id}` |
| order | `/orders/{order_id}` |

Web currently translates these canonical destinations to its static
dashboard/order pages. Flutter opens the closest current native surface; the
unified asset/result detail views will consume the same destination object in
the later navigation phase.

## Deep-link transport

The web acceptance URL uses
`onboarding.html#invitation=<opaque-token>`. A fragment is not sent to the web
server or included in normal `Referer` headers. The page copies the token into
tab-scoped session storage before authentication, posts it in a JSON body for
preview/acceptance, and removes it after success. OAuth callback handling
preserves the same tab-scoped value.

Native clients use `geovision://app/invitation/accept#token=<opaque-token>`.
Android and iOS register the `geovision` custom scheme, and Flutter preserves
the requested route across login/registration. Production HTTPS universal/app
links still require the deployed domain association files and signed app
entitlements; that infrastructure gate must be completed with the release
phase before email links prefer HTTPS-to-app handoff.

Do not place tokens in analytics, crash reports, support screenshots, query
parameters, push payload logs, or audit details. Token-bearing responses are
`no-store`.

## Security and operations

- Preview reveals only a masked email and scoped destination metadata.
- Expired and revoked tokens return `410`; tampered/unknown tokens return a
  generic `404`; reuse by another identity returns `409`.
- Viewer roles cannot issue, list, or revoke invitations.
- Accepted membership role is copied from the locked invitation, never from an
  acceptance request.
- Organization member limits are checked at acceptance, not only at issue.
- Creation, acceptance, and revocation write audit events without token data.
- The Alembic migration is additive. Legacy `CompanyUser(status=invited)` rows
  remain pending and can receive a newly issued token; no unrecoverable token is
  fabricated during backfill.

Before a production rollout, rehearse the migration on a restored database,
configure the public frontend origin, test email delivery through the durable
notification phase, and verify iOS/Android domain association on signed builds.

# Microsoft Entra External ID cutover runbook

This runbook moves GeoVision API authentication from internal-only sessions
toward Microsoft Entra External ID without changing internal user UUIDs or
prematurely consolidating organizations. Execute it first in a production-like
environment with a restorable database backup.

## Preconditions

- The Phase 3 additive Alembic migration is at the single repository head and
  has been tested from both a fresh database and a pre-Phase-3 database.
- A GeoVision API application and delegated API scope exist in the intended
  Entra External ID tenant. Do not use Microsoft Graph as the API audience.
- Each client application is authorized to request the GeoVision API scope.
- The approved flow emits the email and literal Boolean `email_verified=true`
  needed for automatic first login, or every pilot identity has been pre-linked
  through an audited invitation/migration. Do not assume optional claims exist.
- Exact issuer, tenant UUID, audience, scope, and optional authorized-party ID
  have been recorded in the deployment secret/configuration system.
- Redirect URIs for any separately approved interactive client match exactly.
  The Phase 3 API adapter itself validates API access tokens; it is not an
  interactive ID-token callback.
- If the legacy Microsoft browser callback remains enabled during transition,
  pin `MICROSOFT_TENANT_ID` to its approved tenant UUID. The Entra External ID
  tenant setting does not constrain that older Microsoft Graph callback. In
  deployed profiles, generic `common`, `organizations`, and `consumers`
  tenant selectors are rejected. If the callback is not required,
  remove its client credentials and block or retire the route.
- A database backup, restore rehearsal, owner, maintenance window, rollback
  decision point, and customer sign-in communication are recorded.
- Public registration and all old application writers can be quiesced for the
  migration. This is not a rolling mixed-version migration: pre-Phase-3 code
  cannot create the new refresh-family parent row after the foreign key exists,
  and old code rejects version 2 sessions containing an audience. Drain or stop
  old instances before migration and do not route new-token traffic to them.

Never paste tokens, client secrets, discovery documents containing unexpected
data, or historical `raw_data` into tickets or logs.

## Stage 1: inventory and migration

1. Pause registration and old writers. Inventory users, refresh tokens,
   `CompanyUser` rows, `AuthIdentity` rows, duplicate/blank provider identifiers,
   and historical `raw_data`. Reconcile non-canonical `users.id` values, duplicate
   `lower(trim(users.email))` values, case-insensitive duplicate Google subjects,
   duplicate company/user membership candidates, blank refresh-family IDs, and
   refresh families that span users before migration. The migration preflight
   stops before DDL when any of those conditions exists.
2. Export and operator-review the candidate mapping from each legacy
   `CompanyUser.email` or unique Company-only email to exactly one normalized
   `User.email`. Historical registration did not prove mailbox ownership, so
   preserve this snapshot and risk decision with the migration evidence.
   Ambiguous/orphan rows remain unbound and non-authoritative.
3. Apply the additive migration in online mode. This revision rejects Alembic
   offline `--sql` generation because its collision checks and data-driven
   compatibility backfills require a live transaction. Startup fails closed on
   any Alembic error;
   never stamp `head` or use `create_all` to bypass a failed migration. Verify
   that all `users.id`, profile links,
   account memberships, orders, and other user foreign keys are unchanged.
4. Verify the safe Google backfill uses the canonical Google issuer and the
   stored Google subject.
5. Confirm historical Microsoft rows without a verified issuer/tenant/subject
   remain nullable. Do not relabel Graph `/me.id` as an OpenID Connect `sub` and
   do not infer a tenant from email domains.
6. Confirm the normalized-email and issuer/subject unique indexes, immutable
   `CompanyUser.user_id` links, reset-link authentication generations,
   refresh-family rows/foreign key, and existing legacy provider-ID index all
   exist. Migrated legacy refresh families intentionally retain unknown issuer
   provenance as internal transition state.
7. Record only aggregate counts and anomalies. Restrict, retain, or erase
   historical `raw_data` under the approved privacy and backup policy.
8. Notify users that password-reset links issued before the maintenance window
   are invalid and must be requested again. The migration marks them used so
   historical plaintext bearer secrets cannot remain active.

## Stage 2: configure validation

Configure the implemented names using deployment-managed values:

```dotenv
IDENTITY_PROVIDER=transition
IDENTITY_AUTO_LINK_VERIFIED_EMAIL=false
INTERNAL_TOKEN_ISSUER=geovision
INTERNAL_TOKEN_AUDIENCE=geovision-api
ACCEPT_LEGACY_ACCESS_TOKENS=true
EXTERNAL_IDENTITY_SESSION_MAX_HOURS=24
ADMIN_EMAILS=
ENTRA_EXTERNAL_ID_ISSUER=https://example.invalid/replace-with-exact-issuer/v2.0
ENTRA_EXTERNAL_ID_AUDIENCE=replace-with-geovision-api-audience
ENTRA_EXTERNAL_ID_TENANT_ID=00000000-0000-0000-0000-000000000000
ENTRA_EXTERNAL_ID_DISCOVERY_URL=https://example.invalid/replace-with-discovery-document
ENTRA_EXTERNAL_ID_REQUIRED_SCOPE=access_as_user
ENTRA_EXTERNAL_ID_AUTHORIZED_PARTY=
ENTRA_EXTERNAL_ID_CLOCK_SKEW_SECONDS=60
ENTRA_EXTERNAL_ID_JWKS_CACHE_SECONDS=3600
```

The values above are nonfunctional placeholders. Use the exact values published
for the approved external tenant. `ADMIN_EMAILS` is a legacy GeoVision admin
list, not an Entra assignment. Audit it separately and never derive it from a
token email or role.

The checked-in DigitalOcean specification deliberately defaults
`IDENTITY_PROVIDER` to `internal`; it does not perform the cutover by itself.
Change the deployed selector to `transition`, preserve all secret-manager values,
and redeploy the service for this stage. Before applying the spec, authenticate
`doctl apps spec validate` (or use the platform UI), export the currently deployed
configuration, and compare it after deployment so blank secret declarations do
not accidentally clear existing values.

Purge or invalidate cached login, OAuth-callback, reset-password, and auth-script
assets during this release. The new browser nonce and fragment-only reset flow
are a coordinated compatibility boundary; serving an old page with the new
backend can fail login or password recovery. Backend-generated handoff URLs use
a version query as an additional cache key, but it does not replace CDN purge.

Before traffic, verify that partial Entra configuration is rejected, URLs are
absolute HTTPS URLs without user information or fragments, discovery reports the
exact configured issuer, and its JWKS URI is HTTPS. `FRONTEND_BASE` and
`BACKEND_BASE` must also be absolute HTTPS origins without userinfo, queries, or
fragments. Do not add a shared static-host origin to authenticated CORS; the
checked-in deployment spec trusts only the dedicated GeoVision origins.
Configuration must reject Microsoft Graph's application ID/resource
and Graph scopes such as `User.Read` as the GeoVision audience/scope.

## Stage 3: shadow verification

Keep `IDENTITY_PROVIDER=transition`. Send Entra tokens only to
`POST /auth/identity/session` while existing GeoVision sessions continue through
the internal-session path. The endpoint validates and exchanges the external
token for a UUID-based GeoVision session. Token purpose must be chosen by the
trusted endpoint.

Exercise these negative gates:

- expired, premature, malformed, unsigned, and non-RS256 tokens;
- wrong issuer, audience, tenant, scope, authorized party, or signing key;
- ID tokens, application-only tokens, and Microsoft Graph access tokens;
- missing `sub`, `tid`, `oid`, `iat`, `nbf`, or `exp`;
- redirected, oversized, invalid, unavailable, or mismatched discovery/JWKS;
- unknown key rotation and recovery after a valid JWKS refresh.

For local password accounts, verify that a completed password reset rejects
both the old access token and every old refresh family. Session issuance is
generation-bound so a login racing the reset cannot leave a usable stale
session behind.

Every case must fail without creating a user, profile, identity, account,
company, membership, refresh token, or audit entry containing token material.
Monitor only bounded failure codes and aggregate rates.

Rate limits use the direct network peer unless it belongs to an explicitly
configured `TRUSTED_PROXY_CIDRS` network. Configure only verified ingress
addresses, make the edge strip or correctly append forwarding headers, and do
not expose the application around that edge. The in-process limiter has bounded
memory but is per worker; use a shared Redis-backed limiter before scaling to
multiple application instances.

## Stage 4: controlled first login

Start with invited/test users. A successful new external principal may create
only a local user UUID, issuer/subject mapping, and minimal profile. It must not
create an organization or workspace. Phase 4 will define the canonical
organization and attach identities through an explicit organization workflow.

Keep `IDENTITY_AUTO_LINK_VERIFIED_EMAIL=false`. If a verified external email
matches an existing GeoVision user, require a separately authenticated linking
or operator-reviewed migration. If the business explicitly approves temporary
automatic linking, document its scope and rollback before enabling the setting;
never enable it for unverified email.

Verify returning login preserves the internal user UUID when provider email or
display name changes. Verify duplicate/concurrent first logins produce one
identity mapping. External roles and email domains must not create GeoVision
admin or workspace permissions.

## Stage 5: make Entra the external login authority

After negative tests, user mapping, monitoring, and rollback rehearsal pass:

1. Route client sign-in through `POST /auth/identity/session`. This is the only
   Phase 3 endpoint that directly accepts an Entra API access token; it validates
   and exchanges that token for a GeoVision internal session.
2. Set the deployed `IDENTITY_PROVIDER=entra_external_id` after the compatibility
   external adapter is no longer needed, then redeploy. This selector makes
   Entra the external exchange adapter; it does not make business API routes
   accept raw Entra tokens. Those routes continue to require UUID-based
   GeoVision sessions in both `transition` and `entra_external_id` modes.
3. Confirm clients request the GeoVision API audience and delegated scope. A
   Graph token must continue to receive an authentication failure.
4. Confirm workspace selection and permission checks still resolve from the
   internal UUID and database membership.
5. Watch invalid-token, unknown-key, discovery/JWKS availability, identity
   conflict, first-login, and session-refresh rates without logging PII/tokens.

The repository currently has no production web/mobile MSAL integration for this
exchange. Complete that client work, tenant policy/Conditional Access testing,
and an end-to-end login rehearsal before executing this stage.

The browser and mobile API base, `BACKEND_BASE`, DNS/TLS, and both registered
OAuth callback URLs must all use the same stable canonical API host. The
checked-in target is `https://api.geovisionops.com`; do not cut over while that
host resolves to an old or unavailable service.

## Retire legacy sessions and callbacks

Stopping legacy acceptance is an explicit security cutover:

1. Stop minting pre-version-2 GeoVision access tokens.
2. Drain all old application instances before allowing version 2 sessions to
   reach users; mixed-version compatibility is one-way.
3. Wait at least the old tokens' maximum lifetime, or announce and perform a forced
   sign-in event.
4. Revoke affected refresh-token families if legacy refresh sessions must also
   end. Database revocation and `ACCEPT_LEGACY_ACCESS_TOKENS=false` solve
   different problems.
5. Set `ACCEPT_LEGACY_ACCESS_TOKENS=false` and verify legacy tokens fail while
   version 2 internal sessions still validate where allowed.
6. Disable the legacy Google/Microsoft callback routes only after usage is zero
   and every required user has an approved new mapping/recovery path.
7. Remove obsolete provider secrets from deployment storage after the rollback
   window, then rotate credentials that remain active.

While the compatibility callbacks remain enabled, initiate them only through the
GeoVision login page. The page creates a per-tab browser nonce; direct or copied
callback fragments fail the browser-binding check.

There is no Firebase authentication path to disable or migrate.

External-origin refresh families require reauthentication at
`EXTERNAL_IDENTITY_SESSION_MAX_HOURS`; refreshed access tokens never outlive
that deadline. Until live provider revocation synchronization exists, urgent
offboarding requires deactivating the local user or deleting the identity
mapping/revoking its families. Already issued access tokens retain only their
configured short lifetime.

## Rollback

Rollback changes routing and configuration before it changes identity data:

1. Restore the previous deployed `IDENTITY_PROVIDER` value (`transition` or
   `internal` as appropriate) and redeploy the service.
2. Restore the previous API/client token acquisition path. Do not point clients
   at Microsoft Graph as a substitute audience.
3. Re-enable legacy access-token acceptance only if its signing key remains
   controlled, the risk is approved, and old token lifetimes are understood.
4. Keep additive issuer/subject columns and mappings. Do not regenerate user IDs,
   delete identities, unlink memberships, or downgrade the database during an
   authentication incident.
5. If a bad mapping was created, quarantine it for audited repair; never merge
   users automatically by email.
6. If discovery/JWKS is unavailable, fail Entra authentication closed and use an
   approved internal recovery path rather than bypassing signature validation.

The schema downgrade is structural, not a data rewind. It does not reactivate
pre-cutover password-reset links or remove the unambiguous owner memberships
materialized from the frozen legacy Company-email snapshot. Pre-Phase-3 binaries
are also incompatible with the refresh-family foreign key, so application
rollback means deploying a compatible Phase 3 build/configuration, not restarting
old code against the upgraded database.

## Completion evidence

Record the migration revision, configuration review, restore rehearsal,
negative-token results, mapping counts, first-login side-effect check, Graph
token rejection, legacy-session retirement decision, monitored error rates,
rollback rehearsal, owners, and timestamps. Do not include secrets, bearer
tokens, raw claims, or personal-data extracts.

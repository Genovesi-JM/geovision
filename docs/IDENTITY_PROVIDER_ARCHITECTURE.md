# GeoVision identity-provider architecture

Phase 3 separates authentication by an external provider from GeoVision's own
user, authorization, and session concepts. The boundary is additive: existing
password, Google, and Microsoft compatibility logins remain available during a
controlled transition, while Microsoft Entra External ID API tokens can be
validated through a strict provider adapter.

## Identity invariants

- `User.id` is GeoVision's immutable internal user identifier. It is a UUID and
  remains the subject of GeoVision-issued version 2 session tokens.
- An external identity is the issuer-qualified pair `(issuer, subject)`. Neither
  an email address, tenant display name, provider object ID, nor access-token
  text replaces the internal UUID.
- Email is a mutable contact and login hint. Automatic linking to an existing
  user by email is disabled by default, even when a provider marks it verified.
- Workspace permissions come from GeoVision database roles and memberships,
  never directly from external token roles or email domains.
- Raw external tokens and unbounded provider claims are not persisted.

`AuthIdentity` retains legacy `provider` and `provider_user_id` fields while
adding `issuer`, `subject`, `tenant_id`, `email_verified`, and `last_login_at`.
The unique issuer/subject mapping points to, but never changes, `User.id`.
Historical Google rows can be backfilled because their stored identifier is the
Google subject. Historical Microsoft rows used Microsoft Graph `/me.id`; that
value must not be relabelled as an OpenID Connect subject or assigned an inferred
tenant.

## Normalized identity and authorization context

An identity adapter returns a validated `ExternalPrincipal`. It contains only
the provider name, issuer, subject, tenant/object identifiers where applicable,
verified-email status, display hints, scopes, and roles needed by the boundary.
It never contains the bearer token.

Identity resolution maps that principal to one immutable GeoVision user. Only
after this mapping succeeds does GeoVision build an `AuthorizationContext` with:

- the internal user UUID;
- a diagnostic external identity subject;
- the selected current `Account` workspace, if any; and
- permissions derived from persisted global and workspace roles.

`active_organization_id` intentionally remains empty. `Account`, `Company`, and
the separate accounts database are not yet one canonical organization model;
Phase 4 owns that consolidation and its RBAC migration.

The current `ADMIN_EMAILS` compatibility setting can create a missing local
administrator when paired with `ADMIN_PASSWORD`. It refuses to promote an
existing non-admin user with the same normalized email. It is not an Entra role
mapping and must not be populated from an external claim. Treat changes to it as
privileged configuration, audit the configured addresses, and remove this
compatibility mechanism only with an explicit authorization migration.
Deployed profiles require the two settings together, and the bootstrap password
must contain at least 12 characters without exceeding bcrypt's 72-byte limit.

Legacy `CompanyUser` authorization is now UUID-bound. The Phase 3 migration
backfills `CompanyUser.user_id` only for a unique normalized-email snapshot;
ambiguous or orphan rows remain unbound and grant no runtime access. New admin
assignments accept an explicit internal `user_id`. The old email-only admin
request remains as a temporary boundary adapter: it resolves one normalized
user once, then persists only that internal ID; email remains contact metadata.
A unique company/user constraint prevents conflicting duplicate role
rows from producing order-dependent authorization. Phase 4 will replace the
overlapping Account/Company membership
models, and Phase 6 owns real pending invitations.

## GeoVision sessions

GeoVision version 2 access tokens are internal sessions. Their `sub` and `uid`
claims both carry `User.id`; `email` is informational. The token also has the
configured GeoVision issuer and audience and records the originating identity
provider for traceability.

`ACCEPT_LEGACY_ACCESS_TOKENS=true` allows older GeoVision tokens during the
transition only when they contain a signed, valid UUID `uid`. Email-only legacy
sessions are rejected because deletion and re-registration could otherwise
attach them to a different human. The switch does not make Google, Microsoft
Graph, or Entra tokens into GeoVision sessions. Set it to `false` only after the
legacy maximum access-token lifetime has elapsed or after an intentional forced
sign-in.

Refresh tokens are random, hashed, one-time values grouped into a persisted
family. Rotation atomically consumes the old value; replay compromises and
revokes the whole family. The family records the originating provider,
issuer/subject, optional external mapping, and an absolute expiry. External
families default to a 24-hour maximum and refreshed access tokens are clamped to
that deadline. Password reset revokes all families. Provider removal, user
deactivation, logout, and account deletion also prevent further refresh.
Password reset advances the user's authentication generation, invalidating old
access tokens immediately as well as revoking every family.

Flutter persists and rotates refresh tokens in platform secure storage and
revokes the family on logout. The static browser client deliberately requests
access-token-only password sessions and the legacy OAuth callbacks likewise
return no refresh token; browser users sign in again after the short access
expiry. This avoids minting an untracked browser refresh family until an
HttpOnly-cookie browser session design is implemented.

Password-reset bearer secrets are delivered in a URL fragment, cleared from the
browser location immediately, and stored only as SHA-256 digests. A successful
reset advances the credential generation with an atomic compare-and-swap, so
concurrent sibling links cannot overwrite one another; it then invalidates every
reset link and refresh family for that user. The Phase 3
migration deliberately invalidates reset links issued by older code because
those historical secrets were stored in plaintext.

## Entra External ID API boundary

The Entra adapter accepts only delegated version 2 API access tokens for the
GeoVision API. A trusted route chooses the token use; the adapter does not infer
the purpose from an unverified header. It does not accept ID tokens and it does
not accept Microsoft Graph access tokens.

Validation is fail-closed and requires:

- an RS256 signature from a key obtained through the configured HTTPS discovery
  document and JWKS;
- exact configured issuer and audience;
- `exp`, `iat`, `nbf`, `sub`, `tid`, and `oid` claims;
- the configured tenant UUID and a non-application token;
- the delegated scope configured by `ENTRA_EXTERNAL_ID_REQUIRED_SCOPE`; and
- the configured `azp` value when
  `ENTRA_EXTERNAL_ID_AUTHORIZED_PARTY` is set.

Discovery and JWKS responses are TLS-verified, size-bounded, redirect-refusing,
and cached. An unknown signing key triggers a bounded refresh. Provider document
unavailability is reported separately from an invalid token, but neither grants
access. Clock skew is bounded by configuration and is not a substitute for
correct host time.

The audience must identify the GeoVision API registration, not Microsoft Graph.
Frontend or mobile clients must request the GeoVision delegated API scope and
send that access token to `POST /auth/identity/session`. After validation and
identity resolution, that endpoint returns an ordinary GeoVision session;
downstream APIs continue to consume the internal UUID-based session. Tokens
acquired for Graph (`User.Read` or a Graph audience) remain usable only with
Microsoft Graph and must be rejected by the GeoVision API.

Phase 3 provides this backend exchange boundary, not a production MSAL client.
The checked-in web and Flutter clients do not yet acquire Entra External ID API
tokens or call the exchange endpoint. That client cutover must be completed and
tested in a later controlled rollout before Entra is described as live on the
customer page.

Every GeoVision access token and refresh-token family is also bound to the
user's persisted authentication generation. A password reset advances that
generation in the same transaction as password replacement and family
revocation, so a session issued concurrently from stale credentials cannot
survive the reset. Password login, password reset, and account deletion also
serialize on the internal user row where the database supports row locks.

## Resolution and first login

Resolution order is:

1. Find the unique `(issuer, subject)` mapping.
2. For supported legacy providers only, upgrade a safe same-provider legacy
   mapping. Unknown-tenant Microsoft Graph rows are not automatically bridged to
   Entra External ID.
3. If provisioning is allowed, require a valid provider-verified email.
4. When that email already belongs to a user, stop for confirmation unless
   `IDENTITY_AUTO_LINK_VERIFIED_EMAIL=true` was deliberately approved.
5. Otherwise create one local user UUID, one external mapping, and one minimal
   profile. Resolve concurrent insert races through the unique mapping.

Automatic first login requires the validated token to contain both an email and
a literal Boolean `email_verified=true`. Microsoft does not guarantee every
optional claim in every access token, so the approved user flow or claims
mapping must be tested for this exact output. When it is unavailable, pre-link
the issuer/subject through an audited invitation or migration; do not infer
verification from `preferred_username`, an email-shaped string, or a valid
token signature.

First login is profile-only provisioning. It must not create an `Account`, a
`Company`, an organization, an owner membership, sites, assets, subscriptions,
or entitlements. Invitation-led organization attachment belongs to Phase 4 and
the later invitation phase. Returning login may fill an empty display name but
must not replace the internal UUID or elevate permissions.

## Legacy browser logins

The Google and Microsoft browser callback routes are compatibility paths. They
continue to mint GeoVision sessions during transition, but they are not evidence
that Entra External ID API-token validation is enabled.

Both compatibility callbacks bind the authorization request to an HttpOnly,
SameSite browser cookie, store a provider-qualified one-time state, use PKCE,
and consume state before contacting the token endpoint. A random nonce held in
the initiating tab's `sessionStorage` and a matching HttpOnly backend cookie bind
the final frontend handoff to that browser. The callback page accepts credentials
only from a URL fragment, verifies the GeoVision session through `/auth/me`, and
allows only known same-directory destinations. Google userinfo receives its
bearer in the Authorization header rather than the URL. OAuth HTTP clients refuse
redirects, and state rows are purged after use/expiry.

- Google's stable stored identifier can be associated with the canonical Google
  issuer during the additive migration.
- The legacy Microsoft callback exchanges an authorization code and calls
  Microsoft Graph. Its Graph object ID is not an Entra External ID `sub`, so its
  historical rows remain distinguishable and require an audited mapping or a new
  login under the new authority. Because Graph `mail`/`userPrincipalName` is not
  treated as a verified mailbox claim, this path supports previously mapped
  Microsoft users only; it cannot provision or email-link a new user.
- Legacy `raw_data` may contain names, email addresses, provider identifiers, or
  other personal data. New Phase 3 resolution does not persist raw claims.
  Inventory access, retention, backups, and deletion obligations before clearing
  historical values; do not copy them into logs or migration reports.

There is no Firebase identity implementation in this repository. Phase 3 does
not add, migrate, or claim support for Firebase Authentication.

## Configuration

The typed names implemented in `backend/app/core/config.py` are:

| Setting | Purpose |
|---|---|
| `IDENTITY_PROVIDER` | `internal`, `transition`, or `entra_external_id` |
| `IDENTITY_AUTO_LINK_VERIFIED_EMAIL` | Exceptional opt-in for verified-email linking; default is `false` |
| `INTERNAL_TOKEN_ISSUER` | Exact issuer for GeoVision session tokens |
| `INTERNAL_TOKEN_AUDIENCE` | Exact audience for GeoVision session tokens |
| `ACCEPT_LEGACY_ACCESS_TOKENS` | Temporary acceptance of pre-version-2 GeoVision sessions |
| `EXTERNAL_IDENTITY_SESSION_MAX_HOURS` | Absolute lifetime of an external-origin GeoVision refresh family; default `24` |
| `ADMIN_EMAILS` | Comma-separated legacy global-admin compatibility list |
| `ENTRA_EXTERNAL_ID_ISSUER` | Exact HTTPS issuer advertised by the external tenant |
| `ENTRA_EXTERNAL_ID_AUDIENCE` | GeoVision API audience, never the Graph audience |
| `ENTRA_EXTERNAL_ID_TENANT_ID` | Allowed external tenant UUID |
| `ENTRA_EXTERNAL_ID_DISCOVERY_URL` | Optional exact HTTPS discovery URL; otherwise derived from issuer |
| `ENTRA_EXTERNAL_ID_REQUIRED_SCOPE` | Required delegated GeoVision API scope |
| `ENTRA_EXTERNAL_ID_AUTHORIZED_PARTY` | Optional exact authorized client application ID (`azp`) |
| `ENTRA_EXTERNAL_ID_CLOCK_SKEW_SECONDS` | Bounded JWT validation leeway |
| `ENTRA_EXTERNAL_ID_JWKS_CACHE_SECONDS` | Discovery/signing-key cache lifetime |

Legacy `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`,
`MICROSOFT_CLIENT_SECRET`, and `MICROSOFT_TENANT_ID` configure the old browser
callbacks only. They do not configure or weaken the Entra External ID adapter.
In staging and production, `FRONTEND_BASE` and `BACKEND_BASE` must be dedicated
absolute HTTPS URLs without userinfo, query strings, or fragments.

See [the Entra cutover runbook](ENTRA_CUTOVER_RUNBOOK.md) for deployment,
backfill, rollback, and session-retirement steps.

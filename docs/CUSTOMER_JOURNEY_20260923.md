# Azure customer journey verification — 23 September 2026

The user's instruction to continue the post-migration work was used to test the
customer journey and fix defects found along the way. Tests used one clearly
synthetic customer in the existing Azure database. No existing customer or owner
account was reset or changed.

## Verified against Azure

- Registration in the website's three-step form created a customer and workspace
  successfully after fixing the focus bug. This first registration used the
  candidate JavaScript against the real Azure backend; subsequent sign-in,
  dashboard, map and chat checks used the deployed website without overrides.
- Email/password login returned a verified customer session; the workspace and
  capability-driven dashboard loaded. Logout cleared the browser token, and the
  same customer could sign back in.
- The authenticated customer API created one georeferenced synthetic site. It
  appeared in the actual web portal's asset view and map.
- The dataset API uploaded a 53-byte synthetic CSV into private Azure Blob
  storage. The API-reported SHA-256 matched the source, and an authorized download
  returned exactly the uploaded bytes.
- A customer request for staff administration returned 403.
- The actual signed-in GAIA widget responded using the visible synthetic site
  name. Read-only database evidence records OpenAI chat completion usage for the
  synthetic customer, with model `gpt-4o-mini-2024-07-18`.
- Google initially returned `redirect_uri_mismatch`. The existing GeoVision
  OAuth client in Google project `geovision-483710` had only local and old
  DigitalOcean callback addresses. Added
  `https://api.geovisionops.com/auth/google/callback`, retained other entries,
  saved and re-opened the configuration, and verified that Google now displays
  its sign-in page for `geovisionops.com`.

The browser tests resolve the real GeoVision domain names directly to Azure only
inside an isolated test browser, with TLS verification enabled. This avoids the
old destinations still held by the computer's DNS cache. The user's browser
profile, host file and system DNS were not modified.

## Fixes deployed

1. `auth.js` now focuses the current registration field synchronously. The former
   30 ms delayed callback could steal focus while typing or autofilling the
   confirmation field; the observed result was a duplicated password in the
   first field and an empty confirmation field. The regression test now checks
   that the third step is actually visible and selectable.
2. The customer portal aborts a request after 30 seconds and displays its existing
   recovery screen instead of remaining on a loading screen. It does not retry
   writes automatically or display unauthorized modules after a timeout.
3. The GAIA widget now sends the bearer token and selected workspace on both
   context and chat requests. Anonymous visitors get a sign-in message. Context
   and chat requests have bounded timeouts.
4. `www.geovisionops.com` redirects with 308 to `geovisionops.com`, preserving the
   path and query. This keeps the OAuth browser nonce on the same origin as the
   callback page. The private pilot and its gateway were not changed.

Final public website image:
`sha256:4619e029e008ed2ed6ab3d2e5602ab8c91d39bb7e9420e77eb5ac94f4bb301dd`.
The backend application image and database schema were not changed. Existing
custom-domain certificate bindings were retained during the website updates.
The [public-web parameters](../infra/azure/public_web/live.parameters.json) now
record the updated image.

Validation: 19 login/customer-portal browser tests passed; one existing
credential-dependent local smoke test was skipped because live credentials were
not supplied to that suite. Two additional chatbot regression tests and two
static-server routing tests passed. The separate live journey verifies the real
customer login that the local suite skips. Artifacts and sanitized evidence are
in [journey-evidence/20260923](journey-evidence/20260923).

## Remaining work

- Google account consent, callback completion and account linking still need a
  real interactive account session. Reaching Google's sign-in page is not a full
  login test.
- Outbound email is not configured on the canonical Azure API. Password-reset
  delivery, invitation email and notifications are not live-verified. Signup
  currently does not require email ownership verification.
- Site creation and file upload were verified through the authenticated API;
  the existing web asset view is a viewer and does not yet expose these complete
  creation/upload controls. They are suitable next screens for the FlutterFlow
  prototype, using the already-tested contracts.
- Map display works with the existing OpenStreetMap renderer. Google Places,
  geocoding and route estimates still require their own billing/API setup. OAuth
  configuration does not activate these services.
- Mixed-language text remains in the existing portal. This test did not perform
  a full localization or mobile-device acceptance pass.
- Payments, NodeODM, ERP, push and physical hardware remain at the states listed
  in [INTEGRATIONS.md](../INTEGRATIONS.md). FlutterFlow was not edited in this pass.

The synthetic customer, workspace, site and dataset were retained for repeatable
acceptance testing. Their names/data identify them as QA; the CSV is not a real
observation and was not finalized into an operational processing job. The test
account's credentials are stored only in the owner's private local migration
directory with mode 0600, outside the repository and website artifact. Render
cleanup remains deferred until the old DNS caches expire and account-level
checks finish.

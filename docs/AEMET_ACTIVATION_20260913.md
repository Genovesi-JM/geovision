# AEMET activation — 13 September 2026

The user confirmed obtaining an AEMET API key and explicitly requested activation.
It was entered in a hidden Mac dialog, not chat. A fixed Madrid-Retiro station
query from an isolated process on the Mac succeeded: **1 observation, 12 variables,
observed at 2026-09-13T05:00:00Z**. These are station observations, not forecasts,
customer asset measurements or proof of complete KPI/report workflows.

## Code and guards

Runtime source commit: `e2090bfc7c3651ad94c5f18b68ab414e7a6def41`.

- Only `https://opendata.aemet.es` on port443 can receive the API key.
- The first observation-envelope request contains the key in a header, not its URL.
  The temporary `/opendata/sh/<token>` data request contains no API key, browser
  cookies, Authorization or Proxy-Authorization. No redirects are followed.
- Default transport ignores proxy environment variables. Raw, identity-encoded
  response sizes are bounded (16 MiB adapter maximum; 2 MiB for the diagnostic).
  A body-read deadline is additional to request timeouts, not an absolute SLA.
- Infinite values, invalid coordinates and unexpected station rows are excluded.
- New administrator-only check: `POST /operations/providers/aemet/check`, empty
  body or `{}` only; no user-supplied URL, station, coordinates or credentials.
  It queries station3195 using a fixed Madrid location and a recent observation
  window, with one request attempt per protocol step and no database writes.
- The UI marks this as a server-credentialed AEMET observation check, separately
  from the no-key Copernicus/MITECO checks. Only dates/counts pass to the browser.
  Listing configuration never makes vendor requests or claims proven connectivity.
- Shared per-process concurrency/cooldown guards remain; even client-close errors
  release the lock. They are not a cross-replica global quota.

Protocol references: [AEMET Swagger](https://opendata.aemet.es/dist/),
[official two-step protocol FAQ](https://opendata.aemet.es/centrodedescargas/docs/FAQs220424.pdf),
[station3195](https://www.aemet.es/en/eltiempo/observacion/ultimosdatos?datos=det&l=3195&w=1).

## Secret handling and deployment scope

For this private pilot the key is stored as the **GeoVision API Container Apps
secret** `provider-aemet-key`, referenced by `AEMET_API_KEY`; it is not a frontend
setting or a committed/local `.env` value. `WEATHER_PROVIDER=aemet` and the exact
official `AEMET_BASE_URL` select the existing adapter.

The four original Azure Key Vault references remain untouched. No Vault metadata
or secret was read, no role was granted and no alternate identity was used to
bypass the earlier Vault denial. ACA direct secrets are a supported separate
app-scoped storage mechanism. Before production, centralize/rotate through the
approved vault access model; do not blindly redeploy the provider Bicep option
that expects an AEMET key already present in Key Vault.

The bounded setup helper verifies account/tenant, exact app/image, private ingress,
existing references, replica bounds and Microsoft gate. It rechecks for changes
before its single PATCH and never retries uncertain mutations. This comparison
reduces conflicts but is not an atomic `If-Match` concurrency guarantee. No key
is passed as a command argument, printed or written to a file. The value exists
transiently in process memory and in Azure's app secret only.

No new vendor subscription, database migration, customer records, worker activation
or public-domain cutover was performed. No key was copied into Kasa or Kaya.

## Verification

- 96 isolated AEMET/provider/MITECO tests passed; the preceding all-stations AEMET
  contract also passed separately. Tests used invented credentials and no vendor.
- 74 gateway tests, 23 intercepted browser tests and 9 secret/setup tests passed.
- Updated 390px screenshot inspected after removing screenshot scroll/focus
  artefacts; no horizontal overflow. This is web-layout QA, not native-device QA.
- Backend no-network image smoke: UID10001, no `.env`, two mocked protocol requests,
  one valid observation and no key in the data GET/output.
- Gateway no-network image smoke: UID10001 and all116 static hashes valid. The
  first attempt accidentally ran its default server entrypoint, so it was stopped;
  the corrected explicit Python entrypoint ran and passed the actual assertions.

Immutable image digests:

- Backend: `b3b74c015f0b1a64bb4e1269f029e2c5d019cb08bf5d09f6687a22c0c3e83383`.
- Web: `957674f94e1ebec53249014a73e56afff295278f9b4a180fdeeb22ae89833158`.

Backend hardened-code revision `geovision-pilot-hcwka3w-api--0000003` was verified
Ready/Healthy before secret entry. Activation subsequently completed on API
revision `geovision-pilot-hcwka3w-api--0000004`; the matching web revision
`geovision-pilot-web-hcwka3w--0000004` was also read back Ready/Healthy.

The real authenticated Azure administration page then returned:

> Observación AEMET verificada · 12 variables · 13 sept 2026, 7:00.

The displayed local time is Europe/Madrid, corresponding to the observation at
`2026-09-13T05:00:00Z`. The page explicitly limits this result to the Madrid test
station and states that it is not a forecast or KPI validation. Its desktop
screenshot was captured and visually inspected in the working browser. The
configuration column remains configuration-only; check results are session-local,
not a persisted uptime/monitoring history. This proves the deployed Azure adapter's
fixed observation diagnostic, not every weather-dependent application workflow.

After this deployment, all 12 fixed anonymous gateway checks passed. Four further
anonymous requests (catalogue GET and Copernicus, MITECO and AEMET diagnostic
POSTs) each returned HTTP401. No redirects were followed or requests retried.

[Open the protected integration panel](https://geovision-pilot-web-hcwka3w.nicepebble-b3698140.spaincentral.azurecontainerapps.io/admin.html?view=integrations).

Remaining weather work includes customer-authorized locations, acquisition and
report/KPI flow verification, forecasts as a distinct capability, key rotation and
production secret governance. Neither Kasa nor Kaya was deployed in this phase.

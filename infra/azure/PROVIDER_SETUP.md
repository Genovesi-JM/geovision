# Opt-in Spain demonstration providers

This wiring connects **existing provider accounts and existing secrets** to the
GeoVision runtime. It does not create accounts, enable billable APIs, accept
terms, create provider secrets, deploy NodeODM, change DNS, or approve production
use. No provider is enabled by the checked-in environment parameter files.

`providerConfiguration` defaults to `{}`. It is a sealed, typed allowlist, not a
general environment-variable override. Unknown properties, credential values,
arbitrary vault URLs, secret names and unsupported providers are rejected. Core
database/signing/storage/queue settings cannot be overridden through it.

## Prepare before opting in

1. Approve the provider account, EU/Spain coverage, terms, scope, quotas and
   monthly budget. Configure Google Places API (New), Routes API and the
   Geocoding API version used by the adapter, not every Maps product.
2. Provision this environment's Azure foundation through the existing reviewed
   workflow. Obtain its `keyVaultName` output; do not select another project's
   vault. The deployment can keep `providerConfiguration = {}` at this stage.
3. Have the approved secret operator add the required fixed-name secrets below
   in **that vault**, through the approved secret-management workflow. Do not
   put credentials in Bicep parameters, repository files, shell history,
   workflow inputs, screenshots or client builds. This module never reads or
   creates a secret value. Missing/inaccessible references stop activation;
   they do not fall back to demo credentials.
4. Add only the chosen configuration members to a reviewed staging parameter
   file. Run local validation and a reviewed Azure what-if, then use the normal
   migration-first release. The frontend's map rendering remains a separate
   OpenStreetMap/Mapbox setting; this does not install a Google map SDK.
5. Rehearse successful and denied requests, attribution/provenance, quota errors
   and timeouts using synthetic Spain data. Record live health separately from
   configuration presence. This change alone does not close a human release gate.

## Fixed Key Vault secret names

The left column is a name, **not a credential value**. Secrets use versionless
references in this environment's vault and its existing managed identity.

| Existing secret name | Backend setting | Required when |
|---|---|---|
| `provider-google-maps-key` | `GOOGLE_MAPS_SERVER_API_KEY` | `googleMaps` object is present |
| `provider-aemet-key` | `AEMET_API_KEY` | `aemet` is `true` |
| `provider-copernicus-token` | `COPERNICUS_ACCESS_TOKEN` | `copernicus.useAccessToken` is `true` |
| `provider-smtp-host` | `SMTP_HOST` | `smtp` object is present |
| `provider-smtp-user` | `SMTP_USER` | `smtp` object is present |
| `provider-smtp-password` | `SMTP_PASSWORD` | `smtp` object is present |
| `provider-smtp-from` | `SMTP_FROM` | `smtp` object is present |
| `provider-nodeodm-url` | `NODEODM_BASE_URL` | `nodeOdm` object is present |
| `provider-nodeodm-token` | `NODEODM_TOKEN` | `nodeOdm` object is present |

MITECO and public Copernicus catalogue search need no credential. AEMET/MITECO/
Copernicus use the existing reviewed official endpoint defaults. Do not use
expired short-lived Copernicus tokens: authenticated downloads require an owned
refresh/rotation procedure; this configuration adds no token refresh service.

For SMTP, the host must support authenticated STARTTLS and certificate
verification; implicit TLS-only port 465 is not supported by this adapter.
`SMTP_USE_TLS` is always `true`, with port 587 unless overridden. The from address
must be approved by the mail provider; a Microsoft 365 mailbox alone does not
guarantee this app's SMTP authentication method is enabled or supported.
NodeODM must already exist with a verified HTTPS URL without userinfo, query or
fragment, and an approved token. Automatic processing stays off by default.

## Configuration example (no keys or secrets)

This example shows syntax only. **Presence of an object opts in**; omit the
member entirely to leave that provider disabled. Never paste the whole example
into a live parameter file before each provider is ready.

```bicep
param providerConfiguration = {
  googleMaps: {
    trafficAware: false
  }
  aemet: true
  miteco: true
  copernicus: {
    downloadAssets: false
    useAccessToken: false
  }
  smtp: {
    port: 587
  }
  nodeOdm: {
    autoCreate: false
  }
}
```

The smaller credential-free first step is:

```bicep
param providerConfiguration = {
  miteco: true
  copernicus: {}
}
```

Google traffic-aware routing, Copernicus asset downloads/token access and
NodeODM automatic creation are separate explicit flags, all off unless enabled.
No payment, Entra, ERP, IoT or push activation is included in this contract.

## Scope and safety

- API: only configured provider references, needed for its synchronous routes.
- Intelligence worker: AEMET/Copernicus only.
- Notification worker: SMTP only.
- Processing worker: NodeODM URL/token only.
- Event worker: SMTP selection only so materialized email deliveries are queued
  for the notification worker (no SMTP credentials), plus NodeODM scheduling
  flags and URL (the Settings contract requires the URL when NodeODM is
  selected); no NodeODM token.
- ERP worker and migration job: no first-demo provider references or settings.

This is **process configuration scoping**, not separate security identities:
the existing development stack shares one managed identity with vault-level
secret access. Separate identities and secret-level grants remain a reviewed
hardening task. No provider secrets are sent to Azure App Configuration, logs,
public outputs, the web client or mobile builds. Deployment metadata includes
only fixed secret names, URIs, provider flags and the SMTP port.

An empty object preserves the original API/event settings and the original
worker defaults (`auto` notifications, `none` weather/satellite/processing).
Returning to `{}` removes these selections from new runtime revisions, but
existing durable jobs remain pinned to providers. Drain or reconcile queued
work before disabling providers or deleting/rotating credentials; test rollback
using the existing release checklist.

## Offline verification

Run `BICEP_BIN=/path/to/bicep infra/azure/validate.sh` (Bicep 0.47.16 was used for
this change). The provider tests evaluate committed default/all/conservative
snapshots entirely locally, check typed negative cases, reject core overrides,
ensure unique names/resolved secret references, and verify worker scoping. The
fixtures have only an invented vault hostname and all-zero subscription ID.
No Azure session, provider credential or network call is required.

The Bicep [sealed type contract](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/user-defined-data-types)
also rejects extra object properties at ARM validation time. Actual secret
availability, managed-identity access and provider responses still require
separate staging evidence.

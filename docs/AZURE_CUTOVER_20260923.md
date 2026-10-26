# GeoVision Azure cutover — 23 September 2026

The public website and canonical API now run in the existing Azure Spain Central
environment. The user authorized moving GeoVision to Azure and explicitly chose
**“Proceed with existing Azure data.”** No Render database import was performed.

Later on the same date, [customer journey fixes](CUSTOMER_JOURNEY_20260923.md)
updated the website image, added a www-to-apex redirect and corrected the Google
OAuth callback configuration. The original cutover evidence below is historical.

| Address | Azure destination | Routing |
|---|---|---|
| `geovisionops.com` | `geovision-public-web` | A `68.221.208.37` |
| `www.geovisionops.com` | `geovision-public-web` | CNAME `geovision-public-web.nicepebble-b3698140.spaincentral.azurecontainerapps.io` |
| `api.geovisionops.com` | `geovision-api` | CNAME `geovision-api.nicepebble-b3698140.spaincentral.azurecontainerapps.io` |

All three names have Azure-managed certificates with SNI bindings. Squarespace
owns the DNS configuration; authoritative DNS is Google Domains. Ownership TXT
records `asuid`, `asuid.www`, `asuid.api` were added. Mail, verification and the
unrelated `health.geovisionops.com` records were preserved. Previous routing had
four-hour TTLs; recursive caches may retain old destinations during that period.
Authoritative verification uses TCP because local UDP DNS requests returned a
cached recursive response even when addressed to the authoritative server.

## Data and source disposition

The downloaded Render archive was preserved privately with SHA-256
`8d21320590be502829590cef787b5d0c9cec03b0d23180167588cb0c6f3ac701`.
It contains zero tables and zero data entries for `geovision_n6bw`. The old API
actually referenced a different database, `geovision_62hw`; its Render resource
page reports that it no longer exists. This is not evidence that former customer
data was migrated. The user approved retaining the existing Azure data instead.

Read-only Azure inventory found one primary user, one internal role, 57 catalogue
items, 57 shop products and 49 KPI definitions, with no organizations, customer
orders or assets. The separate accounts database has its schema and no customer
or employee rows. Existing databases were neither cleared nor replaced.

The reviewed DigitalOcean team had no App Platform apps, managed databases or
Spaces buckets to move. Render resources and the former GitHub Pages source were
retained; no subscription cancellation or resource deletion was performed.
Any remaining paid Render resources can therefore continue to incur charges.
The former Render API was unhealthy, so restoring its old DNS is not a verified
working rollback.

## Deployed runtime

Resource group: `rg-geovision-pilot-weu`; environment:
`cae-geovision-pilot-hcwka3w`. The website has 0.25 CPU / 0.5 GiB; the public API
has 0.5 CPU / 1 GiB. Both scale from zero to one replica. This keeps the existing
pilot cost profile but allows cold starts and is not a high-availability setup.

Website digest:
`sha256:3db68f84637d368ecb9dc98ee5e175ea82458a696f495fa7fd7f3d3d3db614ab`.
API digest (unchanged reviewed backend image):
`sha256:b3b74c015f0b1a64bb4e1269f029e2c5d019cb08bf5d09f6687a22c0c3e83383`.

The API uses the existing Azure PostgreSQL, accounts database, Blob storage,
configuration, signing/encryption secrets and workers. Google OAuth credentials
were copied securely from the old Render environment into Azure secrets. The
canonical callback is `https://api.geovisionops.com/auth/google/callback`.
The API allows CORS only from the apex and www website origins. Anonymous
administration and customer data access remain denied.

The private pilot API, owner-only gateway and event worker were preserved. The
hourly intelligence job and verified GAIA/AEMET/Copernicus configuration remain
as documented in [the activation record](PROVIDER_ACTIVATION_20260923.md).
PostgreSQL currently has seven-day backup retention, without HA or geo-redundant
backup. No role grants or additional production foundation were created.

## Verification and operational limits

Sanitized live evidence is in [cutover-evidence/20260923](cutover-evidence/20260923).
It records the final bindings, authoritative DNS, HTTPS checks, static artifact
hashes, health/readiness, anonymous access protection, CORS and Google OAuth
redirect initiation. Actual Google account consent/login and authenticated
customer workflows still require an end-to-end session; redirect initiation
alone does not establish those work.

All 22 checks directed to Azure with the real domain names and normal TLS
verification passed. At 00:10 UTC on September 23, normal local DNS still reached
old destinations: the apex health path returned 404, www returned 301, and the
old API did not respond within the probe timeout. Authoritative DNS had all three
Azure targets. Thus the destination and DNS configuration are verified, while
global cache expiry is still pending; the browser's cached canonical homepage
alone was not used as proof of Azure routing.

Local validation passed: six public-site packager tests, static-handler smoke
checks, twelve security regression tests and five readiness/Google OAuth tests.
The security gate test was updated to recognize the existing provider routes'
InternalActor dependency; their integrations-capability authorization test is
now also in that gate. No backend application behavior changed.

Paid payments, email delivery, Maps search/routing, NodeODM, ERP, push and hardware
integrations are not made active merely by this hosting move. Their exact states
remain in [INTEGRATIONS.md](../INTEGRATIONS.md). FlutterFlow was not modified;
clients should use `https://api.geovisionops.com` for the migrated API.

For website releases, use the [public-web runbook](../infra/azure/public_web/README.md)
and preserve the current domain bindings. Do not use the separate production
foundation workflow to update these pilot-environment apps. Prefer a previous
known-good Azure image revision for application rollback while retaining Azure
DNS, data, secrets and certificate bindings. No database rollback was required.

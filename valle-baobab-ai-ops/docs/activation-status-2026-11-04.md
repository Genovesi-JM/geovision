# Activation status — 4 November 2026

This is a dated operational snapshot, not a claim of production readiness.

- The nine role definitions and shared operating contract are versioned in this kit. The GeoVision repository loads them through root `AGENTS.md` and `CLAUDE.md` after this branch is merged.
- A Codex daily progress heartbeat is active at 09:00 Europe/Madrid. It reviews Kasa, Kaya Saúde, GeoVision, Azure, and GitHub; it does not grant independent production access to nine separate runtimes.
- GeoVision's dedicated staging OIDC identity passed the Azure authentication check on [PR #26](https://github.com/Genovesi-JM/geovision/pull/26), and all delivery checks passed after dependency updates. The identity has read access only; it is not a deployment identity.
- The current staging Bicep parameters use `environmentName = staging`, which would name a new set of resources. The existing resources in the staging resource group use the `pilot` name token. Automatic staging deployment is held behind the unset `GEOVISION_STAGING_DEPLOY_ENABLED` variable until the deployment plan adopts the existing resources and passes a what-if review.
- Azure already has `geovision` and `geovision_accounts` on both GeoVision PostgreSQL servers, and `kaya` and `kaya_accounts` on both Kaya PostgreSQL servers. The staging servers were started on 4 November to verify this inventory.
- Kasa's Azure container app now has an external HTTPS URL. Its readiness route confirms a read-only synthetic demo without PostgreSQL support; the two tested write routes return 503. Do not call a newly provisioned server a working Kasa database until the application has a transactional persistence layer and migration path.
- Kaya's deployed public API is reachable, but the current local application has an explicit clinical launch hold. Its GitHub Pages deploy job is also disabled pending a reviewed release decision; the Pages URL returns 404.
- GeoVision's public web and API health URLs respond with HTTP 200. Public URL and service health checks remain separate from resource provisioning.

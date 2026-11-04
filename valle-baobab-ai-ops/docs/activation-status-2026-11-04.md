# Activation status — 4 November 2026

This is a dated operational snapshot, not a claim of production readiness.

- The nine role definitions and shared operating contract are versioned in this kit. The GeoVision repository loads them through root `AGENTS.md` and `CLAUDE.md` after this branch is merged.
- A Codex daily progress heartbeat is active at 09:00 Europe/Madrid. It reviews Kasa, Kaya Saúde, GeoVision, Azure, and GitHub; it does not grant independent production access to nine separate runtimes.
- GeoVision's dedicated staging OIDC identity passed the Azure authentication check on [PR #26](https://github.com/Genovesi-JM/geovision/pull/26). Its release gate remained blocked by dependency audits on the previous run; the dependency fix is being rechecked.
- Azure already has `geovision` and `geovision_accounts` on both GeoVision PostgreSQL servers, and `kaya` and `kaya_accounts` on both Kaya PostgreSQL servers. The staging servers were started on 4 November to verify this inventory.
- Kasa's Azure container app is private and its current pilot release is a read-only synthetic demo without PostgreSQL support. Do not call a newly provisioned server a working Kasa database until the application has a transactional persistence layer and migration path.
- Public URL and service health checks remain separate from resource provisioning. A deployed Azure resource alone does not prove its application route works.

# Opt-in disposable PostgreSQL/PostGIS image rehearsal

This is a local release gate, not an Azure deployment or a migration of existing
customer records. Run it explicitly from the GeoVision repository; it is not
part of the default offline unittest discovery.

```sh
docker build --platform linux/amd64 --tag geovision-backend:azure-pilot-20260912 backend
python3 infra/azure/tests/verify_postgres_container.py --image geovision-backend:azure-pilot-20260912
```

The PostgreSQL test image `postgis/postgis:16-3.5` must already exist locally.
The harness refuses non-amd64 images, resolves both image IDs once, and never
pulls an image. A new run-labelled internal Docker network and PostgreSQL tmpfs
are created. There are no host-data mounts, published ports, environment-file
reads, remote database URLs, real accounts, provider credentials or cloud calls.
Only resources created by this run are removed, after checking the run label.
Runtime and migration containers use the non-root image with a read-only root
filesystem; only temporary runtime directories are writable.

Every new PostgreSQL fixture password contains a fresh random prefix followed
by `% ! @ : /`, including spaces. The server receives the raw throwaway password;
both primary and accounts DSNs percent-encode it exactly once. This exercises
the Alembic/ConfigParser percent-interpolation boundary rather than relying on
URL-safe passwords. Failure output redacts raw, percent-encoded and
ConfigParser-escaped variants. No existing credentials are read or substituted.

The source-only `backend/.dockerignore` allowlist names **415 exact files**: runtime Python code,
both Alembic chains/configurations and runtime requirements/startup files.
There are no directory or wildcard inclusion exceptions: Docker ignores trailing
slashes in directory-negation patterns, which can unintentionally admit files.
The offline safety suite rejects those patterns and checks tracked runtime Python
files are represented in the manifest. Add each new runtime file deliberately.
Environment examples, RAG caches/corpora, logs, local databases, uploads, backups,
private keys and unrelated developer files are excluded. The current RAG runtime
is a placeholder and does not read those corpus/cache files; this change does
not implement retrieval. Both Docker stages pin the official Python manifest
observed during the 2026-09-12 build. Some Python dependencies still use ranges;
a future rebuild must repeat verification and is not guaranteed byte-identical.

Checks performed by the harness:

1. A fresh PostgreSQL server has the PostGIS extension; the runtime image contains
   only permitted source files, runs as UID10001, and passes `pip check`.
2. `start.py migrate` upgrades the primary and separate `geovision_accounts`
   databases and completes its compatibility bootstrap. Repeating the command
   preserves a synthetic account and the migration heads. No admin is silently
   seeded when no admin credentials were supplied.
3. The accounts database contains exactly the two directory tables plus its
   independent Alembic version table; both email uniqueness constraints work.
4. An unversioned legacy fixture is rejected with PostgreSQL duplicate-table
   SQLSTATE42P07, and its existing synthetic record remains unchanged.
5. The API starts with migrations/bootstrap delegated to the prior job. Strict
   `ENV=staging` HTTP readiness returns200 only with **both** schema heads current.
   Changing either head returns a sanitized503 while liveness remains200;
   restoring the head restores readiness. The API handles graceful shutdown.

The database role is a disposable local PostgreSQL superuser. This does **not**
prove Azure's extension allowlist, managed-server privileges, private DNS/TLS,
managed identity, Blob storage, App Configuration, provider connectivity,
background delivery, real-data backup/import/restore, authorisation or public
browser/mobile behaviour. Those remain separate deployment/release gates.

## Execution record — 2026-09-12

The first attempt reached only fresh PostGIS initialization and exceeded the
initial 90-second setup allowance during concurrent amd64 image builds. It did
not run application migrations; its labelled test resources were cleaned up.
The setup allowance was increased to 240 seconds for emulated PostGIS startup,
without weakening schema or application readiness checks. A subsequent package
inspection correctly stopped on `app/schema.sql`, exposing the directory-negation
issue. The manifest was replaced with exact paths and the image rebuilt.

The final local **linux/amd64** image `geovision-backend:azure-pilot-20260912`
passed the entire rehearsal, exit code 0:

`sha256:948228508fcc65459680f30de97288b241b4b24ff538d8c09a853f7b1536de55`

This is the local immutable manifest-list/image ID. The rehearsal itself performs
no upload. The release owner subsequently verified and uploaded only this image
to `geovisionpilothcwka3w.azurecr.io/geovision-backend:pilot-20260912`, confirming
the registry digest matches the value above. Earlier intermediate image IDs are
not the verified release. Cloud runtime/deployment readiness is still separate.

- Source-only filesystem inspection and non-root UID10001: passed.
- Installed dependency metadata (`pip check`): passed.
- Fresh PostgreSQL 16.9 / PostGIS 3.5 initialization: passed.
- Primary migration to `phase34_sector_taxonomy_v1` and separate accounts
  migration to `accounts_v1`, both executed twice: passed. The synthetic account
  was preserved and no administrator was seeded without supplied credentials.
- Both accounts unique-email constraints and independent schema readiness: passed.
- Unversioned legacy-table rejection with its synthetic record preserved: passed.
- Strict staging HTTP readiness for **each** database head: 200 → sanitized503 →
  200, with liveness remaining200: passed.
- Read-only/non-root API startup and graceful exit0: passed.
- Run-labelled disposable containers/network: cleaned up and removal verified.
- Seven offline harness/manifest safety tests and `git diff --check`: passed.

An independent Docker scratch-export canary check using this exact ignore policy
exported only synthetic `app/main.py` and `app/core/config.py`. Synthetic
`app/private.env`, `app/email_log.txt`, `app/private.py` and `app/schema.sql`
were all excluded. No real source/private file contents were placed in that
canary context. The actual runtime image inspection separately verified the
release image's permitted file types.

The existing phase34 migration emitted non-fatal SQLAlchemy warnings while
reflecting the PostGIS geometry column. No schema/readiness guard was relaxed,
and no application/business-flow code was changed in this packaging task.
Azure privileges/extensions, external services and existing-data restore/import
remain unverified as listed above; this successful local rehearsal does not
declare a complete production migration.

## Special-character regression gate — rebuilt image passed, 2026-09-12

The historical successful image rehearsal above used only a URL-safe password
and therefore did not test percent-encoded DSNs. A later Azure migration exposed
an Alembic ConfigParser failure before SQL execution. The strengthened harness
now tests `%`, spaces, `!`, `@`, `:` and `/` through both DSNs and adds offline
round-trip encoding and error-redaction assertions. The migration environment
fixes and startup-log hardening are maintained separately from this harness.

The rebuilt local tag `geovision-backend:azure-pilot-20260912-r2` was first
checked against the release owner's exact immutable image ID and linux/amd64
architecture. The complete rehearsal then ran against the immutable ID, not
the mutable tag, and completed with **exit code 0** at approximately 19:46 UTC:

`sha256:e552de137e293e92da8c613195ab610ad79197041118793316ed044c495a9794`

The independently pinned, already-local PostgreSQL/PostGIS image was:

`sha256:94146ac37bc61e2322f88016056c5920729cb8c64c8542ed590af8fc2abdac07`

The application image includes the Alembic interpolation correction `c4a0d57`
and migration diagnostic redaction `cfe10c8`; this run used the strengthened
harness committed as `17db784`.

- Source-only package, UID10001 and `pip check`: passed.
- Fresh PostGIS on the run-labelled internal network and tmpfs, without host
  mounts, published ports, external image pulls or cloud access: passed.
- Primary and separate accounts migrations, **twice with the same fresh
  URL-special password**: passed; synthetic account preserved; no administrator
  created without supplied administrator credentials.
- Accounts schema readiness and both email uniqueness constraints: passed.
- Unversioned legacy fixture rejected while its original synthetic row remained
  unchanged: passed.
- Strict staging HTTP readiness checked each database head independently:
  200 -> sanitized 503 -> 200; liveness remained 200: passed.
- Read-only, non-root API startup and graceful shutdown with exit code 0: passed.
- Label-checked disposable container/network cleanup: passed. An independent
  post-run listing found no remaining containers or networks carrying the
  rehearsal label. Existing user resources were not targeted.
- All nine offline harness/manifest safety regressions: passed again.

The older successful image and upload record above remain historical evidence,
not the current special-character test target. This new record proves the
isolated local migration/runtime regression gate only. It does not claim an
Azure migration, private-network connectivity, managed-service permissions,
provider integrations, production clinical/business readiness or a public release.

## Staff-session and synthetic-report release — 2026-09-12

The final source-only `geovision-backend:azure-pilot-20260912-r3` image passed
the complete disposable rehearsal with exit 0, including both migrations twice,
URL-special throwaway passwords, row preservation, accounts constraints,
legacy-table rejection, independent head-readiness 200/503/200 cycles, non-root
read-only startup and graceful shutdown:

`sha256:37e0280a688c9ae8915c4adec00c83b9ff2895f28c11a0a18d986f0f4dc1de00`

The nine offline harness/manifest safety regressions passed again. Independent
post-run checks found no remaining rehearsal-labelled containers or networks.
An earlier `a438f84b...` variant was interrupted before application migrations
and cleaned up after a report-pagination adjustment; it is not this release.

Additional standalone tests in the final immutable runtime passed: 15 staff
authentication/onboarding tests and 12 synthetic report tests. These use isolated
SQLite fixtures, exact read-only test-file mounts and no network or host dotenv.
The report QA PDF was rendered and visually checked after the pagination fix.
Frontend evidence is separate: 20 offline session tests, five mocked-browser
login tests and three mocked responsive tests (1280/390/360px) passed. These do
not prove authenticated Azure access, real customer flows or native devices.

The release owner pushed this exact image to the project's private ACR tag
`geovision-backend:pilot-20260912-r3`; Docker returned the same registry digest.
Private image-only deployment and live HTTP/browser evidence are tracked
separately and are not claimed by this rehearsal record.

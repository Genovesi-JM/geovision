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

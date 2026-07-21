# GeoVision mobile architecture

## System context

```
Devices · drones · external providers
        ↓  MQTT / webhooks / HTTPS / vendor SDKs
GeoVision FastAPI backend + background workers   (this repo: /backend)
        ↓  PostgreSQL/PostGIS + object storage
Alerts · reports · processing · notifications
        ↓  mobile-optimised JSON, tiles, previews, signed URLs
Flutter iOS + Android app                        (this repo: /mobile)
```

Heavy processing stays on the backend. The app consumes mobile-optimised
information only (KPI values, previews, tiles, signed report URLs, mission and
device status). It never processes full orthomosaics, raw LiDAR or large
multispectral datasets locally.

## Chosen stack (single, coherent)

| Concern | Choice | Why |
|---------|--------|-----|
| State + DI | **Riverpod** (`flutter_riverpod`) | One approach throughout; testable, no codegen required |
| Routing | **go_router** | Declarative, deep-link/universal-link ready |
| Networking | **dio** | Interceptors for bearer-token + transparent refresh |
| Secure storage | **flutter_secure_storage** | Keychain / Keystore for tokens (never passwords) |
| Local cache / queue | **shared_preferences** JSON envelopes | Offline-first without build_runner fragility |
| Charts | **fl_chart** | KPI sparklines / trends in brand style |
| i18n | **flutter gen-l10n** | EN + PT now, structured to add ES cleanly |

Models are plain immutable Dart with `fromJson`/`toJson` (no freezed/json_serializable
codegen) so the project analyses and tests without a code-generation step.

## Layering (feature-oriented)

```
lib/
├── app/            app widget, ProviderScope wiring, shell
├── core/           config, errors (Result/Failure), networking, storage,
│                   theme (design system), routing, shared widgets, demo data
├── features/<f>/   domain/ (models)  ·  data/ (repositories + providers)  ·
│                   presentation/ (screens/widgets)
└── integrations/   maps · payments · push · iot  (interface + mock + placeholder)
```

Every feature follows **domain → data (repository) → presentation**. Repositories
return a typed `Result<T>` / `DataEnvelope<T>` (value + `syncedAt` + `fromCache`)
so the UI can always show honest freshness and never imply offline data is live.

## Offline-first

- Reads: repository tries network (when online + not demo), writes a timestamped
  cache envelope, and falls back to the last cache when offline.
- Writes: service requests / evidence go through a durable `OfflineQueue`
  (FIFO, attempt-tracked, survives restart). Pending items surface with a
  "pending sync" badge — no silent data loss.
- Connectivity is a first-class stream (`connectivity_plus`) surfaced in the shell.

## Provider adapters (never block development)

Each external integration has: an **interface**, a **mock** implementation
(credential-free, always runnable), and a **placeholder** real implementation
selected by a feature flag / `--dart-define`. See `INTEGRATIONS.md`.

## Navigation (5 destinations)

Home · Sites · Alerts · Work · Account. Maps, Reports, Devices and Orders are
reached inside those flows, not from the nav bar.

## Security posture

Tokens only in the secure enclave; passwords never stored or logged; single-flight
transparent refresh on 401; explicit secure clear on logout; secrets only via
`--dart-define` / `.env` (git-ignored). HTTPS enforced for non-local endpoints.

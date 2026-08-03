# GeoVision IoT current-state audit

Audit date: 2026-08-03. Canonical repository: `/Users/genovesimaria/geovision`, branch `feature/erp-realtime-account`.

## Repository and history

The canonical copy is a clean Git repository before this work. `origin` is `https://github.com/Genovesi-JM/geovision.git`. GitHub `main` is at `6e514f9` (2026-02-20); the local feature branch contains 18 later commits through `aabe79e` (2026-07-22). Those commits are not present on GitHub. Desktop, Downloads and iCloud copies were left untouched.

## Existing architecture

- Static branded web frontend: HTML/CSS/JavaScript, customer dashboard, admin, store, authentication and GAIA.
- FastAPI backend: Python, SQLAlchemy 2, Alembic, JWT/OAuth, multi-tenant companies/sites, orders, payments, documents, risk, ERP outbox and drone mission contracts.
- Flutter mobile app: Riverpod, Dio, secure storage, offline queue, sites, devices, alerts, orders, reports, account and drone screens.
- Persistence: SQLite development default; PostgreSQL deployment support. The migration chain currently ends at `drone_automation_v1`.
- Deployment: DigitalOcean app configuration, GitHub Pages frontend, backend start script and GitHub Actions for backend/web and mobile.

## Baseline IoT findings

The mobile app already defined an `IotProvider`, transports, provisioning, diagnosis and safe-command outcomes. Its backend provider called `/iot/*`, but none of those routes existed. `backend/app/routers/hardware.py` only registered a name and location against a user and was not mounted. No durable device credentials, normalized sensor channels, telemetry table, broker bridge, real-time fan-out, commissioning, calibration, alerts or command acknowledgement existed.

The customer dashboard had a Hardware table but populated it from an empty in-memory portfolio. No live device view or history chart existed.

## Baseline quality and errors

- Existing backend `.venv` was incomplete and could not import `pydantic_settings`; `.venv-test` was healthy.
- Baseline backend suite: 15 tests passed using `.venv-test`.
- Mobile code already had offline-first foundations, but IoT live subscriptions were polling placeholders.
- No Docker Compose stack existed.
- No firmware or real-protocol simulator existed.
- Production secrets are ignored, but device secrets needed a lifecycle and encryption-at-rest policy.

## Implemented plan

1. Extend the existing SQLAlchemy/Alembic model with tenant-scoped assets, gateways, devices, channels, credentials, readings, alert rules/events, commands, calibration and commissioning.
2. Add one-time provisioning exchange and individually revocable credentials.
3. Normalize unit-safe telemetry through signed MQTT or device-authenticated REST, with duplicate/replay/timestamp/rate validation.
4. Fan out persisted readings over SSE and authenticated WebSocket.
5. Add alert evaluation, safe low-voltage command acknowledgement, CSV/PDF reporting and audit entries.
6. Connect the existing web/mobile surfaces rather than creating a replacement application.
7. Add a real MQTT/REST simulator, ESP32 PlatformIO firmware, Docker development stack, Mac launcher, tests and hardware-day documentation.

## Known architectural limits

- In-process live fan-out is correct for one backend instance. Multi-replica production needs the documented Redis pub/sub adapter.
- Development Mosquitto uses application-level HMAC device authentication. Production must add broker ACLs or mutual TLS.
- TimescaleDB is prepared in Compose; the generic SQLAlchemy table remains portable. Production can convert it to a hypertable after retention policy approval.
- Email, Telegram, push, SMS and WhatsApp are adapter boundaries; only the safe log/test channel works without external credentials.

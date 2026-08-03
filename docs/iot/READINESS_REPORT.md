# Hardware integration readiness report

Updated 2026-08-03 from executed evidence, not feature claims.

## Readiness score

- Software/simulator integration: **91%** — ready for an internal or guided customer demonstration.
- First ESP32 bench connection: **86%** — firmware and provisioning are ready; the physical board/pinout still has to be verified.
- Unattended production installation: **68%** — blocked by real-hardware burn-in, exact sensor calibration, external notification credentials, production certificates/domain, backup/restore drill and final security approval.
- Remote control: **55% for supervised low-voltage demonstrations only**. Mains, pumps, generators, medical equipment and safety-critical machinery remain prohibited until a qualified engineer designs and signs the external control circuit.

## Executed evidence

- GitHub `origin/main` was fetched and compared: the working branch is 18 commits ahead, so the local repository was preserved as the latest source.
- Full backend regression suite: **18 passed**.
- IoT tests cover one-time provisioning, credential exchange, tenant isolation, asset/gateway registries, REST telemetry, signed MQTT ingestion, freshness/replay controls, duplicate suppression, time-series queries, CSV/PDF, alert lifecycle, and guarded command acknowledgement.
- A real Mosquitto network smoke test stored signed MQTT telemetry and changed the device to online.
- Fresh Alembic migration from an empty database reached `iot_hardware_platform_v1`; an ORM/Alembic site-country drift discovered during the live test was repaired.
- ESP32 PlatformIO build for `esp32dev`: **success**, approximately 16% RAM and 82% flash.
- Flutter: `flutter analyze` reported no issues and **33 tests passed**.
- Existing web portal: browser-tested sign-in, hardware list, nine current measurements, chart and live refresh using the simulator.
- Docker Compose configuration validates. The first full Docker pull could not finish because the Mac reached 138 MiB free and Docker's internal content store returned an I/O error. Task-created Homebrew Docker/Flutter download caches were removed and APFS later reported about 6.9 GiB free, but Docker's VM still failed to restart cleanly; Docker Desktop needs user-level storage recovery before the full container stack can be rerun.

## Genuine remaining gates

1. Free several more gigabytes on the Mac and restart/repair Docker Desktop's internal storage; no user Docker data was deleted.
2. Connect the purchased ESP32, confirm the exact board revision and every sensor's voltage/pinout, then perform the checklist in `FIRST_HARDWARE_DAY.md`.
3. Supply production broker/domain/TLS and notification-provider credentials through the deployment secret manager.
4. Qualified controls/electrical approval for anything beyond isolated extra-low-voltage demonstration outputs.
5. Final penetration, load, backup/restore and production deployment approval.

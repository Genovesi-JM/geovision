# Local setup on Mac

Installed/required tools: Git, Node/npm, Python 3.12, Docker Desktop/Compose, PlatformIO, Arduino CLI and Mosquitto clients. Xcode/CocoaPods remain for the existing iOS project. ESP-IDF is supplied by PlatformIO for the selected ESP32 platform; a second standalone install is unnecessary.

1. Keep at least 8–10 GB free for initial container downloads/builds. Open Docker Desktop once and accept its terms.
2. From the repository, run `make setup` or double-click `start_geovision_iot.command`.
3. The launcher creates ignored `.env.iot`, development TLS certificates, TimescaleDB, Redis, Mosquitto, Mailpit, backend, frontend and simulator.
4. It prints a local demo login and opens `http://127.0.0.1:8001/login.html`.

Useful commands:

```bash
make dev
make simulator
make logs
make test
make stop
```

Data volumes are preserved by `make stop`. Do not use `docker compose down -v` unless intentionally deleting local development data.

If Docker reports `input/output error` after the Mac ran out of disk space, first free disk space and restart Docker Desktop. Do not use factory reset or volume deletion without reviewing whether other projects have data in Docker.

# Troubleshooting

- No dashboard devices: confirm the user is linked to the same company as the site/device.
- 401 REST ingestion: permanent secret/UID mismatch, revoked credential or quarantined device.
- 422 unknown channel/unit: commission the channel and use its canonical unit.
- MQTT rejected signature: confirm canonical JSON, device secret, UTC time and unique nonce.
- MQTT connects but no data: inspect `make logs`, topic tenant/site/UID and broker CA.
- Device stale/offline: verify Wi-Fi RSSI, NTP, sampling interval and signed last will.
- Firmware will not flash: use a data-capable cable, correct `/dev/cu.*` port and hold BOOT when required.
- ESP32 safe mode: inspect reset diagnostics, remove output loads, factory reset only after saving necessary commissioning information.
- Dashboard cannot live-connect: backend must be reachable at `window.API_BASE`; inspect WebSocket status and JWT session.

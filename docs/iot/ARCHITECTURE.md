# IoT architecture

```text
ESP32 / PLC / gateway
  ├─ MQTT TLS + HMAC, QoS 1 (primary)
  └─ HTTPS + per-device bearer secret (fallback)
                 ↓
Mosquitto → GeoVision MQTT bridge → validation/normalization
                                      ↓
                         PostgreSQL / TimescaleDB
                         ├─ sensor channels/readings
                         ├─ five-minute aggregates + retention
                         ├─ alerts and lifecycle
                         ├─ commands/results
                         └─ audit/commissioning/calibration
                                      ↓
                   WebSocket/SSE → existing web + Flutter app
```

Tenant identity is derived from the authenticated user for customer APIs and from the signed topic plus device identity for MQTT. A device must match its company and site in both the topic and database. Devices cannot choose another tenant in a payload.

Adapters in `backend/app/iot/adapters.py` reserve normalized boundaries for Modbus RTU/TCP, ChirpStack, The Things Stack and BLE sync. Vendor-specific register maps and payload decoders belong behind those boundaries.

The database is the durable source of truth. `event_hub` is a single-instance low-latency fan-out. Replace it with Redis Streams or pub/sub before horizontal scaling; consumers should keep the same event format.

Raw telemetry defaults to 30-day retention and portable five-minute aggregates to 730 days. The background maintenance worker implements this consistently on SQLite/PostgreSQL; a high-volume deployment can replace the worker with Timescale continuous aggregates while preserving the aggregate API contract.

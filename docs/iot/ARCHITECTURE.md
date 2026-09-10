# IoT architecture

```text
ESP32 / PLC / sensor
  ├─ direct MQTT TLS + HMAC or HTTPS device credential
  ├─ Raspberry Pi FieldBox → durable queue → HTTPS/MQTT
  └─ Azure IoT Hub → authenticated Event Grid webhook
                                      ↓
                         one GeoVision telemetry v1 boundary
                                      ↓
                         PostgreSQL / TimescaleDB
                         ├─ canonical asset assignment history
                         ├─ envelope receipts/streams/sequences
                         ├─ sensor channels/readings
                         ├─ five-minute aggregates + retention
                         ├─ alerts and lifecycle
                         ├─ commands/results
                         └─ audit/commissioning/calibration
                                      ↓
                   WebSocket/SSE → existing web + Flutter app
```

Tenant identity is derived from the authenticated user for customer APIs, from
the signed topic plus device identity for MQTT, and from the registered external
device identity for IoT Hub. A device must match its company/site or configured
provider mapping; payload tenant or asset values are never trusted. Every device
has a GeoVision UUID/public ID and may have a separate provider ID. Assignment
history links it to the canonical generic `Asset`; the old IoT asset ID remains
only as a compatibility field.

Adapters in `backend/app/iot/adapters.py` reserve normalized boundaries for Modbus RTU/TCP, ChirpStack, The Things Stack and BLE sync. Vendor-specific register maps and payload decoders belong behind those boundaries.

Azure-specific schemas end in `app/integrations/iot`; monitoring owns only the
cloud-telemetry port and normalized event. REST, MQTT, the FieldBox reference,
and the Azure simulator then call the same ingestion service. The database is
the durable source of truth. `event_hub` is a single-instance low-latency
fan-out. Replace it with distributed pub/sub before horizontal scaling;
consumers should keep the same event format.

Raw readings and their receipt audit default to 30-day retention and portable
five-minute aggregates to 730 days. The independent maintenance worker
implements this consistently on SQLite/PostgreSQL; a high-volume deployment can
replace aggregation with Timescale continuous aggregates while preserving the
API contract. See `docs/IOT_EDGE_CONTRACT.md` for reconnect and ordering rules.

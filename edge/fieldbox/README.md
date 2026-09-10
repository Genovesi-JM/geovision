# GeoVision Raspberry Pi FieldBox reference

This directory demonstrates the supported **ESP32 → Raspberry Pi FieldBox →
GeoVision** topology. It is deliberately standalone and contains no customer,
Wi-Fi, broker, or cloud credentials.

`geovision_fieldbox.py` provides:

- the same `geovision.telemetry.v1` envelope used by direct REST, MQTT, and
  Azure IoT Hub ingestion;
- a bounded SQLite/WAL queue with a persistent stream ID and monotonic sequence;
- ordered reconnect flushing with message IDs unchanged, so retries are
  idempotent at GeoVision;
- local leak and empty-tank rules that can close a valve without WAN access;
- a remote-command allowlist that rejects energizing/opening actuators by
  default and returns a command acknowledgement result;
- an HTTP sender that reads a device credential from its caller but never
  persists that credential with telemetry.

Typical integration embeds `FieldBox.capture()` in the GPIO/serial sensor loop
and calls `FieldBox.flush()` after connectivity checks. Production services
should obtain the API URL and device credential from a root-readable service
environment or hardware-backed store. The SQLite file should live on durable
storage and be monitored for queue depth, disk wear, clock synchronization, and
dropped-oldest events at the configured bound.

Direct ESP32 devices can skip this gateway and use the firmware under
`firmware/esp32`; both topologies reach the identical GeoVision ingestion
service and receipt ledger.

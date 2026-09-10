# Telemetry schema

```json
{
  "protocol_version": "geovision.telemetry.v1",
  "device_id": "gv-example",
  "message_id": "fieldbox-a:42",
  "timestamp": "2026-08-03T12:00:00Z",
  "stream_id": "fieldbox-a",
  "sequence": 42,
  "firmware_version": "1.2.0",
  "replayed_from_edge": false,
  "measurements": {
    "temperature": {"value": 24.8, "unit": "Cel", "quality": "good"},
    "water_leak": false,
    "battery": 87
  },
  "location": {"latitude": 40.4168, "longitude": -3.7038, "accuracy_meters": 8},
  "context": {"gateway": "raspberry_pi_fieldbox"},
  "metadata": {}
}
```

The envelope above is provider-neutral. Signed MQTT adds `device_uid`, a unique
`nonce`, and a 64-character HMAC `signature` around the same fields. REST uses a
per-device bearer credential. IoT Hub's Event Grid adapter obtains the external
device identity from `iothub-connection-device-id`, then passes the decoded body
through this schema and the same ingestion service.

Channels are commissioned with key, measurement type, data type, canonical unit, range and precision. Payload units must match the channel. Values are normalized into numeric, Boolean or text columns; new sensor types extend the registry rather than add a custom readings table.

Quality values are `good`, `uncertain`, `bad`, and `sensor_error`. The API
rejects unknown channels, mismatched units, incorrect types, malformed keys,
credential-like context fields, replayed MQTT nonces, stale live timestamps and
excessive rates.

`message_id` is idempotent per device. `(stream_id, sequence)` detects collisions
and ordering independently. Repeating the same message returns the original
receipt without creating readings or business events. A different message using
an occupied sequence is rejected. A lower sequence or older timestamp is stored
as `out_of_order` for history, but cannot regress the device health/location or
trigger alerts and actuator automation.

Offline replay sets `replayed_from_edge=true` and includes the original sample
time plus `queued_at`. It may exceed the live freshness window only within
`IOT_STORE_FORWARD_MAX_AGE_DAYS`; that limit cannot exceed raw retention. A
durable receipt records source, provider event ID, protocol/firmware, asset,
stream/sequence, replay and ordering state before channel rows are written.

Raw history is available from `/iot/devices/{id}/telemetry`, receipt metadata
from `/iot/devices/{id}/receipts`, and five-minute min/max/average/count buckets
from `/iot/devices/{id}/aggregates`. Retention defaults are controlled by
`IOT_RAW_RETENTION_DAYS` and `IOT_AGGREGATE_RETENTION_DAYS`.

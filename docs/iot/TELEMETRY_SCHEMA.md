# Telemetry schema

```json
{
  "device_uid": "gv-example",
  "message_id": "boot3-00042",
  "nonce": "unique-random-value",
  "timestamp": "2026-08-03T12:00:00Z",
  "measurements": {
    "temperature": {"value": 24.8, "unit": "Cel", "quality": "good"},
    "water_leak": false,
    "battery": 87
  },
  "metadata": {"firmware": "0.1.0"},
  "signature": "64-hex-character HMAC"
}
```

Channels are commissioned with key, measurement type, data type, canonical unit, range and precision. Payload units must match the channel. Values are normalized into numeric, Boolean or text columns; new sensor types extend the registry rather than add a custom readings table.

Quality values: `good`, `uncertain`, `bad`, `sensor_error`. The API rejects unknown channels, mismatched units, incorrect types, malformed keys, duplicate/replayed nonces, stale timestamps and excessive rates.

Raw history is available from `/iot/devices/{id}/telemetry`; five-minute min/max/average/count buckets are available from `/iot/devices/{id}/aggregates`. Retention defaults are controlled by `IOT_RAW_RETENTION_DAYS` and `IOT_AGGREGATE_RETENTION_DAYS`.

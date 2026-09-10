# MQTT topics

For tenant `T`, site `S`, device UID `D`:

```text
geovision/v1/T/S/D/telemetry
geovision/v1/T/S/D/state
geovision/v1/T/S/D/events
geovision/v1/T/S/D/commands
geovision/v1/T/S/D/command-results
geovision/v1/T/S/D/configuration
```

Devices publish telemetry/state/results and subscribe to commands/configuration. Use QoS 1. Retain state only; do not retain telemetry or commands. Configure the signed offline state as the MQTT last will. External devices connect with TLS 1.2+ on 8883. Development backend-to-broker traffic stays inside the Compose network.

Every device-originated envelope adds `device_uid`, a unique `nonce`, and an
HMAC-SHA256 `signature` over canonical JSON without `signature` to the common
`geovision.telemetry.v1` payload. Message IDs are idempotent per device;
persistent `stream_id` and monotonic `sequence` fields make buffered reconnect
ordering explicit.

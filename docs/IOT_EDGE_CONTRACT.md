# IoT, FieldBox, and offline edge contract

Phase 16 makes GeoVision-programmed ESP32 sensors and Raspberry Pi FieldBoxes
first-class monitoring devices without making Azure, a broker, or continuous
WAN access part of the domain model.

## Identities and assignments

- GeoVision owns the device UUID and public `gv-*` identity.
- `provider_code` plus `provider_device_id` records a separate external identity
  such as Azure IoT Hub's device ID. Provider IDs are never primary keys.
- `core_asset_id` points to the generic cross-sector Asset. Every reassignment
  ends the old row and creates an auditable `DeviceAssignment` row; the legacy
  IoT asset field remains for existing clients.
- The device snapshot stores hardware/firmware, capabilities, connectivity,
  last contact, bounded battery percentage, derived health, last location, and
  latest stream/sequence. Out-of-order data never regresses this snapshot.

## Supported topologies

1. **ESP32 direct:** signed MQTT/TLS with QoS 1 is primary; authenticated HTTPS
   is the fallback. LittleFS stores failed publications in original sequence.
2. **ESP32 through FieldBox:** local radio/serial/GPIO collection writes a
   bounded SQLite/WAL queue on a Raspberry Pi. The FieldBox forwards the same
   protocol over REST/MQTT and retains failed rows for ordered retry.
3. **Azure IoT Hub:** devices publish JSON to the configured hub. Event Grid
   sends `Microsoft.Devices.DeviceTelemetry` events to
   `/iot/providers/azure-iot-hub/events`; the adapter validates the configured
   hub/custom secret, extracts `iothub-connection-device-id`, decodes JSON or
   base64, and returns provider-neutral events.

Azure Event Grid subscription validation is handled synchronously by returning
`validationResponse`. The implementation follows Microsoft's published IoT Hub
Event Grid schema and webhook-validation contract:

- <https://learn.microsoft.com/azure/event-grid/event-schema-iot-hub>
- <https://learn.microsoft.com/azure/event-grid/end-point-validation-event-grid-events-schema>

## Delivery and ordering

The common `geovision.telemetry.v1` envelope is documented in
`docs/iot/TELEMETRY_SCHEMA.md`. Each accepted envelope first receives one durable
receipt. Device/message, device/stream/sequence, and provider/event identities
form independent replay controls.

- Same device and message ID: successful idempotent duplicate, zero new rows or
  events.
- Same stream/sequence with a different message: conflict and rejection.
- Lower sequence or older recorded time: stored and flagged out of order;
  alerts, automatic control, and current health/location updates are skipped.
- FieldBox replay: original `message_id`, sample timestamp, stream and sequence
  stay unchanged; `replayed_from_edge` and `queued_at` document the delay.
- Live messages use the short freshness window. Explicit replay can be accepted
  up to the configured store-forward age, never beyond raw retention.

## Offline behavior and local authority

Measurement capture, durable queuing, command-result creation, and fail-safe
rules do not depend on GeoVision or Azure being reachable. Reconnect flushing is
oldest-first and stops after the first failed delivery to preserve order. Queue
bounds protect local disk; operators must alert on depth and dropped-oldest
events for their hardware profile.

Local rules are deliberately allowlisted and fail-safe. Leak, empty tank,
maximum runtime, or lost control link may close a low-voltage valve or
de-energize an output. Remote control starts disabled. The FieldBox sample
rejects energizing/opening commands by default, while both samples acknowledge
the actual command result. Physical overrides and site engineering controls
remain authoritative.

Reference implementations:

- `firmware/esp32/src/main.cpp` — signed direct device with bounded LittleFS
  queue, persistent stream/sequence, reconnect replay, and local interlocks.
- `edge/fieldbox/geovision_fieldbox.py` — dependency-free Raspberry Pi queue,
  safe local rules, acknowledgements, and REST forwarder.
- `backend/scripts/simulate_azure_iot_hub.py` — representative telemetry through
  the real IoT Hub/Event Grid HTTP boundary without an Azure account.

## Operations and retention

Run `python -m app.workers.iot_worker` as one independent maintenance process in
deployed environments. It marks stale online devices offline, emits the durable
`device.offline_detected` event with canonical asset context, rolls up numeric
readings, and deletes raw readings/receipts and aggregates at their respective
retention limits. In-memory WebSocket fan-out remains single-process and is not
the durable event path.

Before live IoT Hub or physical actuator activation, complete Human Gate 13:
restrict the Event Grid destination and secret, register provider identities,
exercise duplicate/out-of-order/offline recovery, validate clock and queue/disk
behavior, test command acknowledgement and physical fail-safes, and monitor
ingress rejection, latency, receipt volume, device offline events, and queue
depth.

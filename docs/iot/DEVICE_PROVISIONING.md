# Device provisioning and commissioning

1. An owner/admin creates a device against their organisation and site, declares channels/capabilities, and receives a 30-minute one-time token.
2. The technician sends Wi-Fi, server addresses, UID, token and pin mapping by USB serial using `provision.example.json`. Secrets are not compiled into firmware.
3. ESP32 joins Wi-Fi, synchronizes time and exchanges the token at `/iot/provision/exchange`.
4. GeoVision invalidates the token and returns one permanent device secret once.
5. The secret is stored in ESP32 NVS and encrypted at rest in GeoVision. The device publishes its signed online state.
6. The technician checks sensor values, local override, fail-safe outputs, connectivity and enclosure, then records commissioning.

Disable or quarantine through `/iot/devices/{id}/status`; this revokes active credentials. Generate a new one-time token with `/iot/devices/{id}/provision`. Never send a permanent secret in email, screenshots or source control.

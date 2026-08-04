# Sensor driver guide

Firmware pin assignments are provisioned, never permanently hardcoded. Add a driver by:

1. Add its channel and canonical unit to the backend registry.
2. Add a configurable pin/bus/address field to `DeviceConfig` and NVS loading.
3. Initialize only when configured; absent devices must not block boot.
4. Return a typed value and quality. Disconnected/invalid values report `sensor_error`, not a plausible zero.
5. Keep readings in engineering units after documented calibration.
6. Test normal, disconnected, range error and recovery states.

Prepared demonstrations: SHT31, DS18B20, leak input, door contact, analogue tank level, relay, LED and buzzer. Ultrasonic and Modbus energy-meter physical drivers require the exact purchased part/register map before final wiring code is enabled.

## GPS driver (GPS Asset Tracker)

The firmware supports a u-blox NEO-6M/M8N GPS module over UART (TinyGPSPlus).
Provision pins via the setup JSON: `"pins": { "gps_rx": <gpio>, "gps_tx": <gpio> }`.
When a valid fix exists, the device adds `latitude`/`longitude` to telemetry (inserted in
lexicographic order so the HMAC signature stays valid). Build verified: `pio run -e esp32dev`
→ SUCCESS (RAM ~16%, Flash ~82%). Flashing/runtime requires the physical board.

**Firmware/kit compatibility:** `makeTelemetry()` emits a fixed base set (`battery`, `safety_ok`,
`signal`) plus configured sensors. To keep the stock firmware compatible with every catalogue
kit, `app/iot/kits.py` now appends a `safety_ok` (generic boolean) channel to every kit, so the
base payload is always accepted. A future refinement is to make `makeTelemetry()` fully
channel-aware (send only the device's provisioned channels); needs hardware to validate.

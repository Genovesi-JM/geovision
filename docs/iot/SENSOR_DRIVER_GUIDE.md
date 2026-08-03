# Sensor driver guide

Firmware pin assignments are provisioned, never permanently hardcoded. Add a driver by:

1. Add its channel and canonical unit to the backend registry.
2. Add a configurable pin/bus/address field to `DeviceConfig` and NVS loading.
3. Initialize only when configured; absent devices must not block boot.
4. Return a typed value and quality. Disconnected/invalid values report `sensor_error`, not a plausible zero.
5. Keep readings in engineering units after documented calibration.
6. Test normal, disconnected, range error and recovery states.

Prepared demonstrations: SHT31, DS18B20, leak input, door contact, analogue tank level, relay, LED and buzzer. Ultrasonic and Modbus energy-meter physical drivers require the exact purchased part/register map before final wiring code is enabled.

# ESP32 flashing

```bash
cd firmware/esp32
pio run
pio device list
pio run --target upload --upload-port /dev/cu.usbserial-XXXX
cp ../../.iot/certs/ca.crt data/ca.crt
pio run --target uploadfs --upload-port /dev/cu.usbserial-XXXX
pio device monitor --baud 115200
```

Send a single-line JSON derived from `provision.example.json` over the serial monitor. Insert Wi-Fi password and one-time token only at provisioning time. Never save a completed provisioning JSON in Git.

`CONFIG_SAVED_RESTARTING`, then `PROVISIONED`, then `GEOVISION_READY` are the expected milestones. `factory_reset:true` erases NVS and the local telemetry queue.

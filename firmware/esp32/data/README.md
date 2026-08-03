Place the development or production MQTT CA certificate here as `ca.crt`, then run:

    pio run --target uploadfs

Never place Wi-Fi passwords or device credentials in this directory. They are delivered through the one-time serial provisioning flow and stored in ESP32 NVS.

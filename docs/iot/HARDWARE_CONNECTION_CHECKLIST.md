# Hardware connection checklist

## Buy for the first demonstrator

| Quantity | Component | Required detail |
|---:|---|---|
| 1 | ESP32 DevKitC / ESP32-WROOM-32 | Genuine board, 3.3 V logic, micro-USB/USB-C as fitted |
| 1 | USB data cable | Must carry data, not charge-only |
| 1 | 5 V supply | Regulated, at least 1 A, reputable/approved supply |
| 1 | SHT31-D breakout | 3.3 V-compatible I2C board |
| 1 | Waterproof DS18B20 probe | Three-wire version; verify conductor colours with its datasheet |
| 1 | 4.7 kΩ resistor | DS18B20 data pull-up |
| 1 | Leak probe/module | Dry-contact or output explicitly safe at 3.3 V |
| 1 | Magnetic reed switch | Normally-open dry contact for door state |
| 1 | 10 kΩ resistor | Reed/contact pull-up if internal pull-up is unsuitable |
| 1 | Analogue 0–3.3 V source/sensor | Demonstration tank level; never connect 5/10 V directly to ESP32 ADC |
| 1 | Opto-isolated relay module | Input must trigger reliably from 3.3 V; isolated low-voltage demo load only |
| 1 each | LED and 220–330 Ω resistor | Visible beacon output |
| optional | Active buzzer | 3.3 V low-current type; use a transistor driver if current exceeds GPIO rating |
| 1 | Breadboard and jumper set | Male/male and male/female |
| 1 | Digital multimeter | Voltage, resistance and continuity |
| final | IP65 enclosure, standoffs, glands, terminals, ferrules, fuse | Required before unattended field use |

## Exact demonstration wiring

Disconnect USB power while wiring. The following is the default provisioned map; firmware reads it from device configuration.

| Function | ESP32 pin | Connection |
|---|---:|---|
| Common ground | GND | Every low-voltage sensor/module ground |
| SHT31 power | 3V3/GND | VIN to 3V3, GND to GND |
| SHT31 data | GPIO21/GPIO22 | SDA to 21, SCL to 22 |
| DS18B20 data | GPIO4 | Probe data to 4; 4.7 kΩ between data and 3V3 |
| Leak digital output | GPIO27 | Contact/output to 27 and GND; confirm active polarity |
| Door reed contact | GPIO26 | Contact between 26 and GND; firmware pull-up enabled |
| Tank analogue signal | GPIO34 | 0–3.3 V only; GPIO34 is input-only |
| Isolated demo relay input | GPIO25 | Relay IN to 25; relay logic supply per module datasheet |
| Beacon LED | GPIO2 | GPIO2 → resistor → LED anode; LED cathode → GND |
| Buzzer control | GPIO33 | Direct only for a confirmed low-current active buzzer; otherwise transistor driver |

## Meter checks before USB power

- No continuity between 3V3 and GND.
- All low-voltage grounds are common unless a module's isolation instructions explicitly say otherwise.
- No sensor output can exceed 3.3 V at an ESP32 pin.
- DS18B20 pull-up measures approximately 4.7 kΩ from data to 3V3.
- Relay input polarity and active-high/active-low behaviour match configuration.
- No mains conductor, industrial 24 V line, pump, generator, valve actuator or medical device is connected.

## Industrial alternatives

- 4–20 mA sensors require a correctly sized precision shunt/isolated input module, surge protection and calibration; do not wire them directly to ESP32.
- 0–10 V sensors require a protected divider or isolated analogue input that guarantees 0–3.3 V at the ESP32.
- RS-485/Modbus requires an isolated 3.3 V transceiver, termination/biasing appropriate to the bus and the vendor's register map.
- LoRaWAN requires the correct regional frequency plan, gateway credentials and antenna.
- Powerful loads require a PLC/safety relay/contactor system designed by a qualified controls electrician. GeoVision sends an authorised request; the local interlocks retain final authority.

Record manufacturer, part number, supply voltage, signal range, calibration reference and a wiring photograph for every installed channel in the commissioning record.

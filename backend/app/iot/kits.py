"""DIY solution-kit catalogue.

Each kit is a complete, homemade ("DIY") GeoVision node: an ESP32-based bill of
materials plus the sensor-channel template, starter alert rules and headline KPIs
for one industry. Provisioning a kit creates a real device with the right channels
and rules in one step, so a customer goes from "pick a kit" to "live data" without
hand-defining channels.

Channel measurement types and units are validated against
``app.iot.registry.SENSOR_UNITS`` — keep them in sync.
"""
from __future__ import annotations

# Each channel: key, label, measurement_type, unit (None for boolean), data_type
# Each alert rule: name, channel, operator, threshold, severity
# BOM entries are illustrative DIY components; prices are USD estimates.

SOLUTION_KITS: list[dict] = [
    {
        "id": "cold_chain_starter",
        "name": "Cold Chain Monitor",
        "industry": "cold_chain",
        "summary": "Fridge/freezer and cold-room monitoring: temperature, humidity, "
                   "door and compressor run-status with excursion alerts.",
        "price_usd": 120,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["buzzer_on", "buzzer_off", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "SHT31 temp/humidity probe", "role": "temperature+humidity", "est_usd": 12},
            {"part": "Reed switch", "role": "door contact", "est_usd": 3},
            {"part": "SCT-013 current clamp", "role": "compressor run-status", "est_usd": 10},
            {"part": "IP65 enclosure + glands", "role": "protection", "est_usd": 15},
            {"part": "5V PSU + wiring", "role": "power", "est_usd": 10},
        ],
        "channels": [
            {"key": "temperature", "label": "Temperature", "measurement_type": "temperature", "unit": "Cel", "data_type": "number", "minimum": -40, "maximum": 60},
            {"key": "humidity", "label": "Humidity", "measurement_type": "humidity", "unit": "%RH", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "door_open", "label": "Door", "measurement_type": "door_contact", "unit": None, "data_type": "boolean"},
            {"key": "compressor_run", "label": "Compressor run", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Fridge over-temperature", "channel": "temperature", "operator": "gt", "threshold": 8, "severity": "critical"},
            {"name": "Low battery", "channel": "battery", "operator": "lt", "threshold": 15, "severity": "warning"},
        ],
        "kpis": ["time-in-range %", "excursion count/duration", "door-open events", "compressor run-hours"],
    },
    {
        "id": "water_tank_starter",
        "name": "Water Tank & Pump Monitor",
        "industry": "water",
        "summary": "Tank level, flow and pump run-status with dry-run and low-level "
                   "alerts. Optional safe relay to signal the pump.",
        "price_usd": 130,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["relay_on", "relay_off", "beacon_on", "beacon_off", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "HC-SR04 / JSN-SR04T ultrasonic", "role": "tank level", "est_usd": 8},
            {"part": "YF-S201 flow sensor", "role": "flow", "est_usd": 6},
            {"part": "SCT-013 current clamp", "role": "pump run-status", "est_usd": 10},
            {"part": "Low-voltage relay module", "role": "safe pump signal", "est_usd": 5},
            {"part": "IP65 enclosure + glands", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "tank_level", "label": "Tank level", "measurement_type": "tank_level", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "flow", "label": "Flow", "measurement_type": "flow", "unit": "L/min", "data_type": "number", "minimum": 0, "maximum": 1000},
            {"key": "pump_run", "label": "Pump run", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Low tank level", "channel": "tank_level", "operator": "lt", "threshold": 15, "severity": "warning"},
            {"name": "Tank critically low", "channel": "tank_level", "operator": "lt", "threshold": 5, "severity": "critical"},
        ],
        "kpis": ["days-of-supply", "pump run-hours & starts", "flow (m³/day)", "leak/dry-run events"],
    },
    {
        "id": "energy_meter_starter",
        "name": "Energy & Power Monitor",
        "industry": "energy",
        "availability": "standby",
        "summary": "Single-phase voltage, current, power and energy with genset "
                   "run-status and high-load alerts.",
        "price_usd": 90,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "PZEM-004T v3 module", "role": "voltage/current/power/energy", "est_usd": 12},
            {"part": "Split-core CT (100A)", "role": "current sensing", "est_usd": 10},
            {"part": "DIN/IP65 enclosure", "role": "protection", "est_usd": 15},
            {"part": "Isolated PSU + wiring", "role": "power", "est_usd": 12},
        ],
        "channels": [
            {"key": "voltage", "label": "Voltage", "measurement_type": "voltage", "unit": "V", "data_type": "number", "minimum": 0, "maximum": 500},
            {"key": "current", "label": "Current", "measurement_type": "current", "unit": "A", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "power", "label": "Power", "measurement_type": "power", "unit": "W", "data_type": "number", "minimum": 0, "maximum": 30000},
            {"key": "energy", "label": "Energy", "measurement_type": "energy", "unit": "kWh", "data_type": "number", "minimum": 0},
            {"key": "genset_run", "label": "Genset run", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "High load", "channel": "power", "operator": "gt", "threshold": 5000, "severity": "warning"},
            {"name": "Voltage sag", "channel": "voltage", "operator": "lt", "threshold": 200, "severity": "warning"},
        ],
        "kpis": ["kWh consumed", "peak demand (kW)", "genset run-hours", "outage count/duration"],
    },
    {
        "id": "agri_field_node",
        "name": "Agriculture Field Node (Solar)",
        "industry": "agriculture",
        "summary": "Solar-powered soil and micro-climate node: soil moisture/temp, "
                   "air temp/humidity and rainfall, with frost and dry-soil alerts. "
                   "Optional irrigation valve control.",
        "price_usd": 160,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["low_voltage_valve_open", "low_voltage_valve_close", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "Capacitive soil-moisture probe", "role": "soil moisture", "est_usd": 6},
            {"part": "DS18B20 probe", "role": "soil temperature", "est_usd": 4},
            {"part": "SHT31 probe", "role": "air temp/humidity", "est_usd": 12},
            {"part": "Tipping-bucket rain gauge", "role": "rainfall", "est_usd": 18},
            {"part": "6V solar panel + 18650 + charger", "role": "off-grid power", "est_usd": 30},
            {"part": "12V solenoid valve + driver", "role": "irrigation control", "est_usd": 20},
            {"part": "IP65 enclosure + mast bracket", "role": "protection", "est_usd": 20},
        ],
        "channels": [
            {"key": "soil_moisture", "label": "Soil moisture", "measurement_type": "soil_moisture", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "soil_temperature", "label": "Soil temperature", "measurement_type": "soil_temperature", "unit": "Cel", "data_type": "number", "minimum": -20, "maximum": 80},
            {"key": "temperature", "label": "Air temperature", "measurement_type": "temperature", "unit": "Cel", "data_type": "number", "minimum": -40, "maximum": 60},
            {"key": "humidity", "label": "Air humidity", "measurement_type": "humidity", "unit": "%RH", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "rainfall", "label": "Rainfall", "measurement_type": "rainfall", "unit": "mm", "data_type": "number", "minimum": 0},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Dry soil", "channel": "soil_moisture", "operator": "lt", "threshold": 20, "severity": "warning"},
            {"name": "Frost risk", "channel": "temperature", "operator": "lt", "threshold": 2, "severity": "critical"},
        ],
        "kpis": ["soil-moisture time-in-range", "water used", "rainfall vs irrigation", "frost/heat alerts"],
    },
    {
        "id": "facility_guard",
        "name": "Property & Leak Guard",
        "industry": "facilities",
        "summary": "Small-property protection: door, motion and water-leak sensing "
                   "with after-hours and leak alerts.",
        "price_usd": 90,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["beacon_on", "beacon_off", "buzzer_on", "buzzer_off"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "Reed switch", "role": "door contact", "est_usd": 3},
            {"part": "PIR sensor", "role": "motion", "est_usd": 3},
            {"part": "Leak rope sensor", "role": "water leak", "est_usd": 8},
            {"part": "IP65 enclosure + wiring", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "door_open", "label": "Door", "measurement_type": "door_contact", "unit": None, "data_type": "boolean"},
            {"key": "motion", "label": "Motion", "measurement_type": "motion", "unit": None, "data_type": "boolean"},
            {"key": "water_leak", "label": "Water leak", "measurement_type": "water_leak", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Water leak detected", "channel": "water_leak", "operator": "eq", "threshold": 1, "severity": "critical"},
            {"name": "After-hours motion", "channel": "motion", "operator": "eq", "threshold": 1, "severity": "warning"},
        ],
        "kpis": ["after-hours events", "leak incidents", "door events", "device health"],
    },
    {
        "id": "environment_air",
        "name": "Environment & Air Quality Monitor",
        "industry": "environment",
        "summary": "Indoor/outdoor air and comfort: CO₂, PM2.5, temperature, humidity "
                   "and noise with exposure alerts.",
        "price_usd": 140,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "SCD40 CO₂ sensor", "role": "co2", "est_usd": 25},
            {"part": "PMS5003 particulate sensor", "role": "pm2.5", "est_usd": 20},
            {"part": "SHT31 probe", "role": "temp/humidity", "est_usd": 12},
            {"part": "MEMS mic module", "role": "noise", "est_usd": 5},
            {"part": "Vented enclosure + wiring", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "co2", "label": "CO₂", "measurement_type": "co2", "unit": "ppm", "data_type": "number", "minimum": 0, "maximum": 40000},
            {"key": "pm2_5", "label": "PM2.5", "measurement_type": "pm2_5", "unit": "ug/m3", "data_type": "number", "minimum": 0, "maximum": 1000},
            {"key": "temperature", "label": "Temperature", "measurement_type": "temperature", "unit": "Cel", "data_type": "number", "minimum": -40, "maximum": 60},
            {"key": "humidity", "label": "Humidity", "measurement_type": "humidity", "unit": "%RH", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "noise", "label": "Noise", "measurement_type": "noise", "unit": "dBA", "data_type": "number", "minimum": 0, "maximum": 140},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "High CO₂", "channel": "co2", "operator": "gt", "threshold": 1000, "severity": "warning"},
            {"name": "High PM2.5", "channel": "pm2_5", "operator": "gt", "threshold": 35, "severity": "warning"},
        ],
        "kpis": ["AQI/CO₂/PM2.5 exposure hours", "noise dose", "comfort in-range %", "threshold breaches"],
    },
    {
        "id": "gps_asset_tracker",
        "name": "GPS Asset Tracker",
        "industry": "fleet",
        "summary": "Real-time location of vehicles and mobile assets: GPS position, "
                   "movement, battery and signal — plottable on the map and openable in Google Maps.",
        "price_usd": 110,
        "device_type": "tracker",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 15},
            {"part": "u-blox NEO-6M / NEO-M8N GPS module", "role": "gps", "est_usd": 12},
            {"part": "MPU-6050 accelerometer", "role": "movement", "est_usd": 4},
            {"part": "18650 battery + charger", "role": "power", "est_usd": 12},
            {"part": "IP65 enclosure + active GPS antenna", "role": "protection", "est_usd": 18},
        ],
        "channels": [
            {"key": "latitude", "label": "Latitude", "measurement_type": "latitude", "unit": "deg", "data_type": "number", "minimum": -90, "maximum": 90},
            {"key": "longitude", "label": "Longitude", "measurement_type": "longitude", "unit": "deg", "data_type": "number", "minimum": -180, "maximum": 180},
            {"key": "motion", "label": "Movement", "measurement_type": "motion", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Low battery", "channel": "battery", "operator": "lt", "threshold": 15, "severity": "warning"},
        ],
        "kpis": ["location / geofence", "distance travelled", "moving vs idle time", "battery"],
    },
    {
        "id": "soil_control",
        "name": "SoilControl — Smart Irrigation",
        "industry": "agriculture",
        "summary": "Closed-loop irrigation: soil moisture, soil temperature, tank level "
                   "and flow with a low-voltage valve. Dry soil triggers an alert and "
                   "(optionally) opens the valve; flow confirms water is really moving.",
        "price_usd": 150,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["low_voltage_valve_open", "low_voltage_valve_close", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "Capacitive soil-moisture probe", "role": "soil moisture", "est_usd": 8},
            {"part": "DS18B20 waterproof probe", "role": "soil temperature", "est_usd": 5},
            {"part": "YF-S201 flow sensor", "role": "flow confirmation", "est_usd": 6},
            {"part": "JSN-SR04T ultrasonic", "role": "tank level", "est_usd": 8},
            {"part": "12V solenoid valve + MOSFET driver", "role": "irrigation control", "est_usd": 20},
            {"part": "12V PSU + buck converter", "role": "power", "est_usd": 12},
            {"part": "IP65 enclosure + glands", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "soil_moisture", "label": "Soil moisture", "measurement_type": "soil_moisture", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "soil_temperature", "label": "Soil temperature", "measurement_type": "soil_temperature", "unit": "Cel", "data_type": "number", "minimum": -20, "maximum": 80},
            {"key": "flow", "label": "Water flow", "measurement_type": "flow", "unit": "L/min", "data_type": "number", "minimum": 0, "maximum": 200},
            {"key": "tank_level", "label": "Tank level", "measurement_type": "tank_level", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "valve_open", "label": "Valve open", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Dry soil", "channel": "soil_moisture", "operator": "lt", "threshold": 25, "severity": "warning"},
            {"name": "Tank critically low", "channel": "tank_level", "operator": "lt", "threshold": 5, "severity": "critical"},
        ],
        "kpis": ["soil-moisture time-in-range", "water used (L)", "irrigation cycles", "detect→irrigate→recover time"],
    },
    {
        "id": "agro_weather",
        "name": "AgroWeather — Weather Station",
        "industry": "agriculture",
        "summary": "Solar farm weather station: air temperature, humidity, pressure, "
                   "rainfall, wind and solar radiation — frost, strong-wind (spray "
                   "window) and extreme-heat alerts.",
        "price_usd": 190,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "BME280 module", "role": "temp/humidity/pressure", "est_usd": 10},
            {"part": "Tipping-bucket rain gauge", "role": "rainfall", "est_usd": 18},
            {"part": "Anemometer + wind vane", "role": "wind", "est_usd": 35},
            {"part": "Solar radiation / light sensor", "role": "irradiance", "est_usd": 15},
            {"part": "6V solar panel + 18650 + charger", "role": "off-grid power", "est_usd": 30},
            {"part": "IP65 enclosure + mast", "role": "protection", "est_usd": 25},
        ],
        "channels": [
            {"key": "temperature", "label": "Air temperature", "measurement_type": "temperature", "unit": "Cel", "data_type": "number", "minimum": -40, "maximum": 60},
            {"key": "humidity", "label": "Air humidity", "measurement_type": "humidity", "unit": "%RH", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "pressure", "label": "Pressure", "measurement_type": "pressure", "unit": "kPa", "data_type": "number", "minimum": 80, "maximum": 110},
            {"key": "rainfall", "label": "Rainfall", "measurement_type": "rainfall", "unit": "mm", "data_type": "number", "minimum": 0},
            {"key": "wind_speed", "label": "Wind speed", "measurement_type": "wind_speed", "unit": "m/s", "data_type": "number", "minimum": 0, "maximum": 80},
            {"key": "solar_irradiance", "label": "Solar radiation", "measurement_type": "solar_irradiance", "unit": "W/m2", "data_type": "number", "minimum": 0, "maximum": 1500},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Frost risk", "channel": "temperature", "operator": "lt", "threshold": 2, "severity": "critical"},
            {"name": "Strong wind (suspend spraying)", "channel": "wind_speed", "operator": "gt", "threshold": 12, "severity": "warning"},
            {"name": "Extreme heat", "channel": "temperature", "operator": "gt", "threshold": 38, "severity": "warning"},
        ],
        "kpis": ["growing-degree days", "rain vs irrigation", "safe spray-window hours", "frost/heat alerts"],
    },
    {
        "id": "greenhouse_control",
        "name": "GreenhouseControl — Climate Controller",
        "industry": "agriculture",
        "summary": "Greenhouse climate: temperature, humidity, soil moisture, CO₂ and "
                   "light with a low-voltage vent/fan relay and irrigation valve.",
        "price_usd": 210,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["relay_on", "relay_off", "low_voltage_valve_open", "low_voltage_valve_close", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "SHT31 probe", "role": "temp/humidity", "est_usd": 12},
            {"part": "Capacitive soil-moisture probe", "role": "substrate moisture", "est_usd": 8},
            {"part": "SCD40 CO₂ sensor", "role": "co2", "est_usd": 25},
            {"part": "Light / PAR sensor", "role": "light", "est_usd": 12},
            {"part": "Low-voltage relay module", "role": "vent/fan signal", "est_usd": 5},
            {"part": "IP65 enclosure + wiring", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "temperature", "label": "Temperature", "measurement_type": "temperature", "unit": "Cel", "data_type": "number", "minimum": -10, "maximum": 70},
            {"key": "humidity", "label": "Humidity", "measurement_type": "humidity", "unit": "%RH", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "soil_moisture", "label": "Substrate moisture", "measurement_type": "soil_moisture", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "co2", "label": "CO₂", "measurement_type": "co2", "unit": "ppm", "data_type": "number", "minimum": 0, "maximum": 5000},
            {"key": "light", "label": "Light", "measurement_type": "solar_irradiance", "unit": "W/m2", "data_type": "number", "minimum": 0, "maximum": 1500},
            {"key": "vent_open", "label": "Vent/fan on", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Greenhouse over-temperature", "channel": "temperature", "operator": "gt", "threshold": 35, "severity": "warning"},
            {"name": "Low humidity", "channel": "humidity", "operator": "lt", "threshold": 40, "severity": "warning"},
            {"name": "High CO₂", "channel": "co2", "operator": "gt", "threshold": 1500, "severity": "warning"},
        ],
        "kpis": ["climate in-range %", "vent/fan run-hours", "water used", "CO₂ enrichment hours"],
    },
    {
        "id": "spray_control",
        "name": "SprayControl — Precision Spray Monitor",
        "industry": "agriculture",
        "summary": "Precision application (advanced tier): spray flow, line pressure and "
                   "chemical-tank level with low-tank and over-pressure alerts. Handling "
                   "of chemicals requires trained operators and local safety controls.",
        "price_usd": 175,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": True,
        "capabilities": ["relay_on", "relay_off", "request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "YF-S201 flow sensor", "role": "spray flow", "est_usd": 6},
            {"part": "Pressure transducer (0–10 bar)", "role": "line pressure", "est_usd": 18},
            {"part": "Ultrasonic level sensor", "role": "tank level", "est_usd": 8},
            {"part": "Low-voltage relay module", "role": "pump/section signal", "est_usd": 5},
            {"part": "Chemical-safe IP67 enclosure", "role": "protection", "est_usd": 20},
        ],
        "channels": [
            {"key": "flow", "label": "Spray flow", "measurement_type": "flow", "unit": "L/min", "data_type": "number", "minimum": 0, "maximum": 200},
            {"key": "pressure", "label": "Line pressure", "measurement_type": "pressure", "unit": "bar", "data_type": "number", "minimum": 0, "maximum": 10},
            {"key": "tank_level", "label": "Chemical tank", "measurement_type": "tank_level", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "pump_run", "label": "Pump run", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Low chemical tank", "channel": "tank_level", "operator": "lt", "threshold": 10, "severity": "warning"},
            {"name": "Over-pressure", "channel": "pressure", "operator": "gt", "threshold": 8, "severity": "warning"},
        ],
        "kpis": ["litres applied / ha", "pressure stability", "coverage %", "refill events"],
    },
    {
        "id": "seed_flow",
        "name": "SeedFlow — Seeder Monitor",
        "industry": "agriculture",
        "summary": "Planting monitor (advanced tier): hopper weight, seeding run-status "
                   "and blockage detection with low-hopper and blockage alerts.",
        "price_usd": 165,
        "device_type": "multi_sensor",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "Load cell + HX711", "role": "hopper weight", "est_usd": 12},
            {"part": "Optical seed-flow sensor", "role": "seed flow / blockage", "est_usd": 15},
            {"part": "Hall run-status sensor", "role": "seeding active", "est_usd": 5},
            {"part": "IP65 enclosure + wiring", "role": "protection", "est_usd": 15},
        ],
        "channels": [
            {"key": "hopper_weight", "label": "Hopper weight", "measurement_type": "load", "unit": "kg", "data_type": "number", "minimum": 0, "maximum": 2000},
            {"key": "seeding_run", "label": "Seeding active", "measurement_type": "run_status", "unit": None, "data_type": "boolean"},
            {"key": "blockage", "label": "Blockage", "measurement_type": "generic", "unit": None, "data_type": "boolean"},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Hopper low", "channel": "hopper_weight", "operator": "lt", "threshold": 10, "severity": "warning"},
            {"name": "Seed-line blockage", "channel": "blockage", "operator": "eq", "threshold": 1, "severity": "critical"},
        ],
        "kpis": ["area seeded", "rate uniformity", "blockage events", "hopper refills"],
    },
    {
        "id": "input_track",
        "name": "InputTrack — Input & Asset Tracker",
        "industry": "agriculture",
        "summary": "Track inputs and mobile assets: GPS location plus input-stock weight, "
                   "with low-stock alerts. Pairs with NFC/QR tags for equipment history "
                   "and refill dates.",
        "price_usd": 130,
        "device_type": "tracker",
        "transport": "mqtt",
        "allow_remote_control": False,
        "capabilities": ["request_diagnostics"],
        "diy_bom": [
            {"part": "ESP32 dev board", "role": "controller", "est_usd": 12},
            {"part": "u-blox NEO-M8N GPS module", "role": "gps", "est_usd": 14},
            {"part": "Load cell + HX711", "role": "input-stock weight", "est_usd": 12},
            {"part": "PN532 NFC reader", "role": "tag scan", "est_usd": 10},
            {"part": "18650 battery + charger", "role": "power", "est_usd": 12},
            {"part": "IP65 enclosure + antenna", "role": "protection", "est_usd": 18},
        ],
        "channels": [
            {"key": "latitude", "label": "Latitude", "measurement_type": "latitude", "unit": "deg", "data_type": "number", "minimum": -90, "maximum": 90},
            {"key": "longitude", "label": "Longitude", "measurement_type": "longitude", "unit": "deg", "data_type": "number", "minimum": -180, "maximum": 180},
            {"key": "stock_weight", "label": "Input stock", "measurement_type": "load", "unit": "kg", "data_type": "number", "minimum": 0, "maximum": 5000},
            {"key": "battery", "label": "Battery", "measurement_type": "battery", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
            {"key": "signal", "label": "Signal", "measurement_type": "signal", "unit": "%", "data_type": "number", "minimum": 0, "maximum": 100},
        ],
        "alert_rules": [
            {"name": "Low input stock", "channel": "stock_weight", "operator": "lt", "threshold": 10, "severity": "warning"},
        ],
        "kpis": ["input stock levels", "consumption rate", "asset location", "refill / movement events"],
    },
]

# The stock ESP32 firmware always reports a local safety-interlock channel, so every
# kit-provisioned device must accept it (unknown channels are rejected on ingest).
_SAFETY_CHANNEL = {"key": "safety_ok", "label": "Local safety interlock", "measurement_type": "generic", "unit": None, "data_type": "boolean"}
for _kit in SOLUTION_KITS:
    if not any(c["key"] == "safety_ok" for c in _kit["channels"]):
        _kit["channels"].append(dict(_SAFETY_CHANNEL))

_KITS_BY_ID = {kit["id"]: kit for kit in SOLUTION_KITS}


def list_kits(*, include_standby: bool = False) -> list[dict]:
    if include_standby:
        return SOLUTION_KITS
    return [kit for kit in SOLUTION_KITS if kit.get("availability", "active") == "active"]


def get_kit(kit_id: str) -> dict | None:
    return _KITS_BY_ID.get(kit_id)


def kit_bom_total(kit: dict) -> int:
    return sum(int(item.get("est_usd", 0)) for item in kit.get("diy_bom", []))

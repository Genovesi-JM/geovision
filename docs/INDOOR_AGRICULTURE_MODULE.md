# GeoVision Indoor Agriculture

Indoor agriculture belongs in the same GeoVision product as a sector-aware
module. It reuses organisations, sites, alerts, work, devices, reports, stock,
orders, permissions and audit history instead of creating a disconnected app.

Development should happen on a temporary Git branch such as
`feature/indoor-agriculture` and merge into `autodev/mobile-build` after its
acceptance checks pass. A Git branch is an implementation boundary, not a
separate commercial product or permanent database.

## Customer model

```text
Organisation
└── Indoor site / facility
    ├── Building
    │   └── Grow room
    │       └── Zone / rack
    │           └── Crop batch / cycle
    ├── Devices and gateways
    ├── Crop recipes and targets
    ├── Alerts and tasks
    ├── Inputs and inventory
    └── Yield, quality, energy and water reports
```

An existing GeoVision customer can therefore see outdoor fields and indoor
facilities in the same Sites area, with screens and KPIs selected by site type.

## Sensors and controlled outcomes

- Air temperature and relative humidity
- CO₂
- Light intensity, DLI and photoperiod
- Nutrient pH and electrical conductivity (EC)
- Water temperature, level and flow
- Substrate moisture
- HVAC, pump, fan and lighting state
- Energy and water consumption
- Door, leak and equipment-health events

The mobile app reads durable state from the GeoVision backend. MQTT, Modbus,
BACnet, LoRaWAN or vendor APIs terminate at a secure gateway/backend adapter,
not directly in normal customer screens.

Commands use explicit outcomes (`pending`, `accepted`, `rejected`, `timeout`,
`offline`, `permissionRequired`, `credentialsRequired`, `error`) and require
role checks, audit records and customer confirmation. GAIA may explain a
condition or propose a task, but it must never freely operate pumps, lights,
dosing, ventilation or other physical equipment.

## First commercial slice

1. Indoor facility and grow-zone site types.
2. Demo facility with rooms, racks, one crop cycle and simulated sensors.
3. Indoor dashboard: climate, irrigation, crop cycle, energy and active alerts.
4. Threshold alerts and response tasks.
5. Device mapping to rooms/zones.
6. Consumables and seed inventory linked to Store.
7. Cycle report with yield, resource efficiency and incident history.
8. Offline read access and queued field observations.

## Later provider gates

Real HVAC, fertigation, lighting and access-control providers require hardware
selection, staging credentials, safety review, physical testing and agreed
fallback behaviour. No production actuator is enabled by default.

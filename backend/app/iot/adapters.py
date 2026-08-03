"""Protocol boundaries for field gateways.

These adapters intentionally contain no vendor SDK. They define the normalized
contract that Modbus, LoRaWAN and BLE implementations must produce, preventing
vendor-specific payloads from leaking into the GeoVision domain model.
"""

from __future__ import annotations

from typing import Protocol


class TelemetryAdapter(Protocol):
    id: str

    def normalize(self, payload: dict) -> dict: ...


class ModbusRtuAdapter:
    id = "modbus_rtu"

    def normalize(self, payload: dict) -> dict:
        return payload


class ModbusTcpAdapter(ModbusRtuAdapter):
    id = "modbus_tcp"


class ChirpStackAdapter(ModbusRtuAdapter):
    id = "chirpstack"


class ThingsStackAdapter(ModbusRtuAdapter):
    id = "the_things_stack"


class BleSyncAdapter(ModbusRtuAdapter):
    id = "ble_sync"

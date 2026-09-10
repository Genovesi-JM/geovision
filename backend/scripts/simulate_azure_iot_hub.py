#!/usr/bin/env python3
"""Send representative IoT Hub Event Grid telemetry to GeoVision.

No Azure account or SDK is required. The delivery uses the exact HTTP adapter
boundary used by a real Event Grid subscription.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from urllib import request
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:8010")
    parser.add_argument("--hub-name", required=True)
    parser.add_argument("--provider-device-id", required=True)
    parser.add_argument("--geovision-device-id", required=True)
    parser.add_argument("--sequence", type=int, default=0)
    args = parser.parse_args()
    secret = os.environ.get("AZURE_IOT_HUB_WEBHOOK_SECRET", "")
    if not secret:
        parser.error("AZURE_IOT_HUB_WEBHOOK_SECRET must be set in the environment")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    event_id = str(uuid.uuid4())
    envelope = {
        "protocol_version": "geovision.telemetry.v1",
        "device_id": args.geovision_device_id,
        "message_id": f"sim-{event_id}",
        "timestamp": now,
        "stream_id": "azure-simulator",
        "sequence": args.sequence,
        "firmware_version": "simulator-1.0.0",
        "measurements": {
            "temperature": {"value": 22.5, "unit": "Cel", "quality": "good"},
            "battery": {"value": 91, "unit": "%", "quality": "good"},
        },
        "location": {"latitude": 40.4168, "longitude": -3.7038},
        "context": {"simulation": True},
    }
    payload = [
        {
            "id": event_id,
            "topic": (
                "/subscriptions/local/resourceGroups/geovision/providers/"
                f"Microsoft.Devices/IotHubs/{args.hub_name}"
            ),
            "subject": f"devices/{args.provider_device_id}",
            "eventType": "Microsoft.Devices.DeviceTelemetry",
            "eventTime": now,
            "data": {
                "body": envelope,
                "properties": {},
                "systemProperties": {
                    "iothub-content-type": "application/json",
                    "iothub-content-encoding": "utf-8",
                    "iothub-connection-device-id": args.provider_device_id,
                },
            },
            "dataVersion": "",
            "metadataVersion": "1",
        }
    ]
    call = request.Request(
        args.api_base.rstrip("/") + "/iot/providers/azure-iot-hub/events",
        data=json.dumps(payload, separators=(",", ":")).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-GeoVision-IoT-Hub-Secret": secret,
        },
    )
    with request.urlopen(call, timeout=30) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()

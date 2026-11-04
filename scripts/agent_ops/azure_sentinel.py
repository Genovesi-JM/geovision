"""Read-only GeoVision staging and public-route check for Azure Sentinel."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request


GROUP = "rg-geovision-staging-weu"
DATABASE_ARM_URL = (
    "https://management.azure.com/subscriptions/50874a30-a81d-4c8a-aac7-13564bd1641d/"
    "resourceGroups/rg-geovision-staging-weu/providers/Microsoft.DBforPostgreSQL/"
    "flexibleServers/psql-geovision-pilot-bcjrgnh?api-version=2024-08-01"
)
API = "geovision-pilot-bcjrgnh-api"
PUBLIC_URLS = (
    "https://geovisionops.com/",
    "https://api.geovisionops.com/ready",
)


def url_status(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "GeoVision-Azure-Sentinel/1"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        except (urllib.error.URLError, TimeoutError):
            if attempt == 0:
                time.sleep(2)
    return 0


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    try:
        result = subprocess.run(
            ["az", "rest", "--method", "get", "--url", DATABASE_ARM_URL,
             "--query", "properties.state", "--output", "tsv"],
            text=True, capture_output=True, timeout=35, check=False,
        )
        if result.returncode:
            raise RuntimeError("Azure PostgreSQL read failed")
        state = result.stdout.strip()
        checks.append(("Staging PostgreSQL", state == "Ready", state or "unknown"))
    except (RuntimeError, subprocess.TimeoutExpired):
        checks.append(("Staging PostgreSQL", False, "read failed"))

    try:
        result = subprocess.run(
            ["az", "resource", "show", "--resource-group", GROUP, "--name", API,
             "--resource-type", "Microsoft.App/containerApps",
             "--query", "properties.provisioningState", "--output", "tsv"],
            text=True, capture_output=True, timeout=35, check=False,
        )
        if result.returncode:
            raise RuntimeError("Azure Container App read failed")
        state = result.stdout.strip()
        checks.append(("Staging API resource", state == "Succeeded", state or "unknown"))
    except (RuntimeError, subprocess.TimeoutExpired):
        checks.append(("Staging API resource", False, "read failed"))

    for url in PUBLIC_URLS:
        status = url_status(url)
        checks.append((url, status == 200, f"HTTP {status}" if status else "unreachable"))

    lines = ["## Azure Sentinel: GeoVision read-only check", "",
             "| Check | Result | Observation |", "|---|---|---|"]
    for name, passed, observation in checks:
        lines.append(f"| {name} | {'PASS' if passed else 'FAIL'} | {observation} |")
    lines.extend(("", "The staging API is internal. This check confirms its Azure resource state; it does not claim an application-level staging smoke test.",
                  "No deployment or resource mutation was attempted."))
    report = "\n".join(lines) + "\n"
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write(report)
    print(json.dumps({"passed": sum(passed for _, passed, _ in checks), "total": len(checks)}))
    return 0 if all(passed for _, passed, _ in checks) else 1


if __name__ == "__main__":
    sys.exit(main())

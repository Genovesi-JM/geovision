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
DATABASE = "psql-geovision-pilot-bcjrgnh"
API = "geovision-pilot-bcjrgnh-api"
PUBLIC_URLS = (
    "https://geovisionops.com/",
    "https://api.geovisionops.com/health",
)


def azure_value(*args: str) -> str:
    command = ["az", *args, "--output", "tsv"]
    result = subprocess.run(command, text=True, capture_output=True, timeout=35, check=False)
    if result.returncode:
        # Azure CLI errors can include account details. Keep the report generic.
        raise RuntimeError(f"Azure read failed for {args[0]} {args[1]}")
    return result.stdout.strip()


def url_status(url: str) -> int:
    request = urllib.request.Request(url, headers={"User-Agent": "GeoVision-Azure-Sentinel/1"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.status
        except (urllib.error.URLError, TimeoutError):
            if attempt == 0:
                time.sleep(2)
    return 0


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    try:
        state = azure_value("postgres", "flexible-server", "show", "--resource-group", GROUP,
                            "--name", DATABASE, "--query", "state")
        checks.append(("Staging PostgreSQL", state == "Ready", state or "unknown"))
    except (RuntimeError, subprocess.TimeoutExpired):
        checks.append(("Staging PostgreSQL", False, "read failed"))

    try:
        state = azure_value("resource", "show", "--resource-group", GROUP, "--name", API,
                            "--resource-type", "Microsoft.App/containerApps",
                            "--query", "properties.provisioningState")
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

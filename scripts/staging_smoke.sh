#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${GEOVISION_STAGING_API_URL:-}" ]]; then
  printf 'GEOVISION_STAGING_API_URL is required.\n' >&2
  exit 2
fi

api_base="${GEOVISION_STAGING_API_URL%/}"
if [[ "${api_base}" != https://* && "${GEOVISION_ALLOW_HTTP_SMOKE:-0}" != "1" ]]; then
  printf 'The staging smoke requires HTTPS. Set GEOVISION_ALLOW_HTTP_SMOKE=1 only for a local rehearsal.\n' >&2
  exit 2
fi

smoke_dir="$(mktemp -d /tmp/geovision-staging-smoke.XXXXXX)"
trap 'rm -rf "${smoke_dir}"' EXIT

request() {
  local label="$1"
  local path="$2"
  local expected="$3"
  local output="$4"
  shift 4
  local code
  code="$(
    curl --silent --show-error --location --max-time 20 \
      --output "${output}" --write-out '%{http_code}' \
      "$@" "${api_base}${path}" || true
  )"
  if [[ "${code}" != "${expected}" ]]; then
    printf 'BLOCK %s returned HTTP %s; expected %s.\n' \
      "${label}" "${code:-unreachable}" "${expected}" >&2
    exit 1
  fi
  printf 'PASS  %s returned HTTP %s.\n' "${label}" "${code}"
}

request_denied() {
  local label="$1"
  local path="$2"
  local output="$3"
  local code
  code="$(
    curl --silent --show-error --location --max-time 20 \
      --output "${output}" --write-out '%{http_code}' \
      -H "${auth_header}" \
      -H "X-Workspace-ID: ${GEOVISION_STAGING_FOREIGN_WORKSPACE_ID}" \
      "${api_base}${path}" || true
  )"
  case "${code}" in
    403|404)
      printf 'PASS  %s was denied with HTTP %s.\n' "${label}" "${code}"
      ;;
    *)
      printf 'BLOCK %s returned HTTP %s; expected 403 or 404.\n' \
        "${label}" "${code:-unreachable}" >&2
      exit 1
      ;;
  esac
}

request 'health' '/health' '200' "${smoke_dir}/health.json"
request 'readiness' '/ready' '200' "${smoke_dir}/ready.json"
request 'unauthenticated protection' '/notifications' '401' \
  "${smoke_dir}/unauthorized.json"

if [[ -z "${GEOVISION_STAGING_ACCESS_TOKEN:-}" || -z "${GEOVISION_STAGING_WORKSPACE_ID:-}" ]]; then
  printf 'PARTIAL Public and unauthenticated smokes passed. Set a short-lived GEOVISION_STAGING_ACCESS_TOKEN and GEOVISION_STAGING_WORKSPACE_ID for the required customer smoke.\n' >&2
  exit 2
fi

auth_header="Authorization: Bearer ${GEOVISION_STAGING_ACCESS_TOKEN}"
workspace_header="X-Workspace-ID: ${GEOVISION_STAGING_WORKSPACE_ID}"
request 'portal experience' '/portal/experience' '200' \
  "${smoke_dir}/experience.json" -H "${auth_header}" -H "${workspace_header}"
request 'asset summary' '/portal/assets/summary' '200' \
  "${smoke_dir}/assets.json" -H "${auth_header}" -H "${workspace_header}"
request 'notification inbox' '/notifications' '200' \
  "${smoke_dir}/notifications.json" -H "${auth_header}" -H "${workspace_header}"
request 'service-request history' '/mobile/service-requests' '200' \
  "${smoke_dir}/services.json" -H "${auth_header}" -H "${workspace_header}"
request 'order history' '/orders' '200' \
  "${smoke_dir}/orders.json" -H "${auth_header}" -H "${workspace_header}"

if [[ -n "${GEOVISION_STAGING_FOREIGN_WORKSPACE_ID:-}" ]]; then
  request_denied 'foreign portal selection' '/portal/experience' \
    "${smoke_dir}/foreign-experience.json"
  request_denied 'foreign asset summary' '/portal/assets/summary' \
    "${smoke_dir}/foreign-assets.json"
  request_denied 'foreign notification inbox' '/notifications' \
    "${smoke_dir}/foreign-notifications.json"
  request_denied 'foreign service-request history' '/mobile/service-requests' \
    "${smoke_dir}/foreign-services.json"
  request_denied 'foreign order history' '/orders' \
    "${smoke_dir}/foreign-orders.json"
else
  printf 'WARN  GEOVISION_STAGING_FOREIGN_WORKSPACE_ID is unset; customer-surface cross-workspace denial was not exercised.\n'
fi

python_bin="${GEOVISION_SMOKE_PYTHON:-$(command -v python3 2>/dev/null || true)}"
if [[ -z "${python_bin}" || ! -x "${python_bin}" ]]; then
  printf 'BLOCK Python 3 is required for response-shape and leakage checks.\n' >&2
  exit 1
fi

"${python_bin}" - "${smoke_dir}" "${GEOVISION_STAGING_WORKSPACE_ID}" <<'PY'
from __future__ import annotations

import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
workspace_id = sys.argv[2]
authenticated_names = {"experience", "assets", "notifications", "services", "orders"}
documents = {
    name: json.loads((root / f"{name}.json").read_text(encoding="utf-8"))
    for name in authenticated_names
}
if not isinstance(documents["experience"], dict):
    raise SystemExit("BLOCK portal experience had an unexpected response shape")
if not isinstance(documents["assets"], dict):
    raise SystemExit("BLOCK asset summary had an unexpected response shape")
if documents["experience"].get("active_workspace_id") != workspace_id:
    raise SystemExit("BLOCK portal experience did not return the selected workspace")
if documents["assets"].get("workspace_id") != workspace_id:
    raise SystemExit("BLOCK asset summary did not return the selected workspace")

services = documents["services"]
if not isinstance(services, list):
    raise SystemExit("BLOCK service-request history was not a list")
for item in services:
    if not isinstance(item, dict) or item.get("workspace_id") != workspace_id:
        raise SystemExit("BLOCK service-request history crossed the selected workspace")

notifications = documents["notifications"]
if not isinstance(notifications, dict) or not isinstance(notifications.get("items"), list):
    raise SystemExit("BLOCK notification inbox had an unexpected response shape")
organization_id = documents["experience"].get("active_organization_id")
for item in notifications["items"]:
    if not isinstance(item, dict) or item.get("organization_id") != organization_id:
        raise SystemExit("BLOCK notification inbox crossed the selected organization")
    if item.get("workspace_id") not in (None, workspace_id):
        raise SystemExit("BLOCK notification inbox crossed the selected workspace")

if not isinstance(documents["orders"], list):
    raise SystemExit("BLOCK order history was not a list")

forbidden = {
    "api_key",
    "client_secret",
    "connection_string",
    "encryption_key",
    "internal_cost",
    "margin",
    "private_key",
    "provider_cost",
}
secret_parts = {
    "authorization",
    "connectionstring",
    "credential",
    "password",
    "secret",
    "signature",
    "token",
}

def walk(value, location="response"):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            key_parts = {
                part
                for part in normalized.replace("-", "_").split("_")
                if part
            }
            if normalized in forbidden or key_parts.intersection(secret_parts):
                raise SystemExit(f"BLOCK forbidden field {location}.{key}")
            walk(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            walk(child, f"{location}[{index}]")

for name, document in documents.items():
    walk(document, name)
print("PASS  authenticated responses contain no forbidden field names.")
PY

printf 'COMPLETE Staging smoke passed for %s.\n' "${api_base}"

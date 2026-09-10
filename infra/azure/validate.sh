#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
output_dir="$(mktemp -d)"
trap 'rm -rf "${output_dir}"' EXIT

if [[ -n "${BICEP_BIN:-}" ]]; then
  "${BICEP_BIN}" build "${script_dir}/main.bicep" --outfile "${output_dir}/main.json"
elif command -v bicep >/dev/null 2>&1; then
  bicep build "${script_dir}/main.bicep" --outfile "${output_dir}/main.json"
elif command -v az >/dev/null 2>&1; then
  az bicep build --file "${script_dir}/main.bicep" --outfile "${output_dir}/main.json"
else
  echo 'Bicep CLI not found. Install Bicep or Azure CLI, or set BICEP_BIN.' >&2
  exit 1
fi

PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s "${script_dir}/tests" \
  -p 'test_*.py'

echo "Azure infrastructure validation passed for ${repo_root}."

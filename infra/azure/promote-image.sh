#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo 'Usage: infra/azure/promote-image.sh SOURCE_ACR DESTINATION_ACR SHA256_DIGEST DESTINATION_TAG' >&2
  exit 2
fi

source_registry="$1"
destination_registry="$2"
source_digest="$3"
destination_tag="$4"
repository='geovision-backend'

for registry_name in "${source_registry}" "${destination_registry}"; do
  if [[ ! "${registry_name}" =~ ^[a-z0-9]{5,50}$ ]]; then
    echo 'ACR names must contain 5-50 lowercase alphanumeric characters.' >&2
    exit 2
  fi
done
if [[ ! "${source_digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo 'The source digest must be sha256 followed by 64 lowercase hexadecimal characters.' >&2
  exit 2
fi
if [[ ! "${destination_tag}" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo 'The destination image tag is invalid.' >&2
  exit 2
fi
for command_name in az docker; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "${command_name} is required." >&2
    exit 2
  fi
done

source_login_server="$(az acr show --name "${source_registry}" --query loginServer --output tsv)"
destination_login_server="$(az acr show --name "${destination_registry}" --query loginServer --output tsv)"
source_reference="${source_login_server}/${repository}@${source_digest}"
destination_reference="${destination_login_server}/${repository}:${destination_tag}"

az acr login --name "${source_registry}" --output none >&2
az acr login --name "${destination_registry}" --output none >&2
docker pull "${source_reference}" >&2
docker tag "${source_reference}" "${destination_reference}"
docker push "${destination_reference}" >&2

destination_digest="$(
  az acr manifest show-metadata \
    --registry "${destination_registry}" \
    --name "${repository}:${destination_tag}" \
    --query digest \
    --output tsv
)"
if [[ "${destination_digest}" != "${source_digest}" ]]; then
  echo 'The promoted manifest digest differs from the approved staging digest.' >&2
  exit 1
fi

printf '%s\n' "${destination_digest}"

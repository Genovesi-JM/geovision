#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
template_file="${script_dir}/main.bicep"
parameters_file="${AZURE_PARAMETERS_FILE:-${script_dir}/dev.bicepparam}"
location="${AZURE_LOCATION:-westeurope}"
resource_group="${AZURE_RESOURCE_GROUP:-rg-geovision-dev-weu}"
deployment_prefix="${AZURE_DEPLOYMENT_PREFIX:-geovision-dev}"
image_tag="${GEOVISION_IMAGE_TAG:-$(git -C "${repo_root}" rev-parse --short HEAD)}"
mode="release"

usage() {
  echo 'Usage: infra/azure/deploy.sh [--what-if|--foundation-only|--runtime-only]'
  echo
  echo 'The default guarded release provisions the foundation, builds the image,'
  echo 'updates and runs the migration job, waits for success, then updates apps.'
}

if [[ $# -gt 1 ]]; then
  usage >&2
  exit 2
fi
if [[ $# -eq 1 ]]; then
  case "$1" in
    --what-if) mode="what-if" ;;
    --foundation-only) mode="foundation" ;;
    --runtime-only) mode="runtime" ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
fi

for variable_name in \
  GEOVISION_POSTGRES_ADMIN_PASSWORD \
  GEOVISION_SECRET_KEY \
  GEOVISION_ENCRYPTION_KEY; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "Required environment variable ${variable_name} is not set." >&2
    exit 2
  fi
done

if ! command -v az >/dev/null 2>&1; then
  echo 'Azure CLI is required.' >&2
  exit 2
fi

providers=(
  Microsoft.App
  Microsoft.AppConfiguration
  Microsoft.Authorization
  Microsoft.ContainerRegistry
  Microsoft.DBforPostgreSQL
  Microsoft.Insights
  Microsoft.KeyVault
  Microsoft.ManagedIdentity
  Microsoft.Network
  Microsoft.OperationalInsights
  Microsoft.ServiceBus
  Microsoft.Storage
)
for provider in "${providers[@]}"; do
  az provider register --namespace "${provider}" --wait --output none
done

deployment_parameters=(
  "${parameters_file}"
  "location=${location}"
  "resourceGroupName=${resource_group}"
  "imageTag=${image_tag}"
)

deploy_stage() {
  local stage="$1"
  local deploy_apps="$2"
  local deploy_migration="$3"
  az deployment sub create \
    --name "${deployment_prefix}-${stage}" \
    --location "${location}" \
    --template-file "${template_file}" \
    --parameters "${deployment_parameters[@]}" \
      "deployApplications=${deploy_apps}" \
      "deployMigrationJob=${deploy_migration}" \
    --output none
}

deployment_output() {
  local deployment_name="$1"
  local output_name="$2"
  az deployment sub show \
    --name "${deployment_name}" \
    --query "properties.outputs.${output_name}.value" \
    --output tsv
}

smoke_test() {
  local deployment_name="$1"
  local api_url
  api_url="$(deployment_output "${deployment_name}" apiUrl)"
  curl --fail --show-error --silent --retry 12 --retry-delay 5 \
    "${api_url}/health" >/dev/null
  curl --fail --show-error --silent --retry 12 --retry-delay 5 \
    "${api_url}/ready" >/dev/null
  echo "GeoVision API is healthy and ready at ${api_url}."
}

if [[ "${mode}" == "what-if" ]]; then
  az deployment sub what-if \
    --name "${deployment_prefix}-what-if" \
    --location "${location}" \
    --template-file "${template_file}" \
    --parameters "${deployment_parameters[@]}" \
      deployApplications=true \
      deployMigrationJob=true
  exit 0
fi

if [[ "${mode}" == "runtime" ]]; then
  # Rollback path: switch runtime revisions to an already-pushed compatible
  # image without executing an older migration set against a newer database.
  deploy_stage runtime true false
  smoke_test "${deployment_prefix}-runtime"
  exit 0
fi

deploy_stage foundation false false
if [[ "${mode}" == "foundation" ]]; then
  echo "Foundation provisioned. ACR: $(deployment_output "${deployment_prefix}-foundation" acrName)"
  exit 0
fi

acr_name="$(deployment_output "${deployment_prefix}-foundation" acrName)"
az acr build \
  --registry "${acr_name}" \
  --image "geovision-backend:${image_tag}" \
  --file "${repo_root}/backend/Dockerfile" \
  "${repo_root}/backend"

# Updating only the job first leaves existing API/worker revisions untouched.
deploy_stage migration false true
migration_job="$(deployment_output "${deployment_prefix}-migration" migrationJobName)"
execution_name="$(
  az containerapp job start \
    --name "${migration_job}" \
    --resource-group "${resource_group}" \
    --query name \
    --output tsv
)"

echo "Waiting for migration execution ${execution_name}."
for _ in $(seq 1 180); do
  execution_status="$(
    az containerapp job execution show \
      --name "${migration_job}" \
      --resource-group "${resource_group}" \
      --job-execution-name "${execution_name}" \
      --query properties.status \
      --output tsv
  )"
  case "${execution_status}" in
    Succeeded)
      echo 'Database migration succeeded.'
      break
      ;;
    Failed|Stopped|Degraded)
      echo "Database migration ended with status ${execution_status}; runtime apps were not updated." >&2
      exit 1
      ;;
  esac
  sleep 10
done
if [[ "${execution_status:-}" != "Succeeded" ]]; then
  echo 'Database migration did not finish within 30 minutes; runtime apps were not updated.' >&2
  exit 1
fi

deploy_stage runtime true true
smoke_test "${deployment_prefix}-runtime"

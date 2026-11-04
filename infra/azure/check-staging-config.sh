#!/usr/bin/env bash
# Report missing names only. Never print credentials or connection strings.
set -euo pipefail
missing=0
for name in AZURE_CLIENT_ID AZURE_TENANT_ID AZURE_SUBSCRIPTION_ID \
  AZURE_LOCATION AZURE_RESOURCE_GROUP GEOVISION_FRONTEND_BASE_URL \
  GEOVISION_CORS_ORIGINS GEOVISION_POSTGRES_ADMIN_PASSWORD \
  GEOVISION_SECRET_KEY GEOVISION_ENCRYPTION_KEY; do
  if [[ -z "${!name:-}" ]]; then
    echo "::error::Required staging setting ${name} is missing. Configure the staging environment before deployment."
    missing=1
  fi
done
if [[ "${AZURE_RESOURCE_GROUP:-}" == 'rg-geovision-pilot-weu' ]]; then
  echo '::error::The pilot resource group contains live GeoVision apps and shared database references. Staging must use an isolated resource group.'
  missing=1
fi
exit "${missing}"

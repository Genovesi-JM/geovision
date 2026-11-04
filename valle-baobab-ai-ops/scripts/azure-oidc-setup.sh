#!/usr/bin/env bash
#
# azure-oidc-setup.sh — Configure GitHub Actions -> Azure OIDC federation for GeoVision staging.
# Fixes the staging login blocker WITHOUT storing any client secret.
#
# Read docs/azure-oidc-setup.md first. Set the variables below, then run:
#   ./scripts/azure-oidc-setup.sh
#
# Prereqs: `az login` and `gh auth login` already done, with rights to create an
# app registration in the tenant and assign a role on the staging resource group.

set -euo pipefail

# ---- EDIT THESE ------------------------------------------------------------
REPO="valle-baobab/geovision"          # owner/name of the GeoVision repo
APP_NAME="geovision-staging-github-oidc"
STAGING_RG="geovision-staging"         # your existing staging resource group
ENVIRONMENT="staging"                   # GitHub environment the deploy runs in
ROLE="Contributor"                      # least privilege that still lets the deploy work
# ---------------------------------------------------------------------------

echo "==> Reading subscription + tenant from current az context"
SUB_ID="$(az account show --query id -o tsv)"
TENANT_ID="$(az account show --query tenantId -o tsv)"
echo "    subscription: $SUB_ID"
echo "    tenant:       $TENANT_ID"

echo "==> Ensuring app registration '$APP_NAME' exists"
APP_ID="$(az ad app list --display-name "$APP_NAME" --query "[0].appId" -o tsv)"
if [ -z "${APP_ID:-}" ]; then
  APP_ID="$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)"
  echo "    created app: $APP_ID"
else
  echo "    reusing app: $APP_ID"
fi

echo "==> Ensuring service principal exists"
az ad sp show --id "$APP_ID" >/dev/null 2>&1 || az ad sp create --id "$APP_ID" >/dev/null
echo "    service principal ready"

echo "==> Creating federated credential for environment:$ENVIRONMENT"
SUBJECT="repo:${REPO}:environment:${ENVIRONMENT}"
if az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$SUBJECT']" -o tsv | grep -q .; then
  echo "    federated credential already present for subject: $SUBJECT"
else
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"geovision-${ENVIRONMENT}-env\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"${SUBJECT}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }"
  echo "    created federated credential: $SUBJECT"
fi

echo "==> Assigning least-privilege role '$ROLE' on staging RG '$STAGING_RG'"
SCOPE="/subscriptions/${SUB_ID}/resourceGroups/${STAGING_RG}"
az role assignment create --assignee "$APP_ID" --role "$ROLE" --scope "$SCOPE" >/dev/null 2>&1 \
  && echo "    role assigned on $SCOPE" \
  || echo "    role assignment already present (or insufficient rights — check your admin role)"

echo "==> Storing identifiers as GitHub Actions variables (not secrets — these are IDs)"
gh variable set AZURE_CLIENT_ID       --body "$APP_ID"     --repo "$REPO"
gh variable set AZURE_TENANT_ID       --body "$TENANT_ID"  --repo "$REPO"
gh variable set AZURE_SUBSCRIPTION_ID --body "$SUB_ID"     --repo "$REPO"
echo "    variables set on $REPO"

cat <<EOF

==> Done. Now TEST the login before creating any further resources:

  1. Add .github/workflows/azure-login-test.yml (see docs/azure-oidc-setup.md section 5).
     It MUST include:  permissions: { id-token: write, contents: read }
     and:              environment: ${ENVIRONMENT}
  2. Run it:    gh workflow run "Azure login test" --repo ${REPO}
  3. Watch it:  gh run watch --repo ${REPO}

A green 'az account show' step = blocker cleared. If it fails with
AADSTS70021, the workflow's subject does not match '${SUBJECT}' — fix that, don't loop.
EOF

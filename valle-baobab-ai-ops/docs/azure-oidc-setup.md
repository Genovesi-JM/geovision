# Step 1 — Azure OIDC Setup (GeoVision staging auth fix)

**Goal:** Fix the GeoVision staging authentication blocker so GitHub Actions can log in to Azure **without any stored secret**, using OIDC federation (short-lived tokens). This is the first technical objective — nothing else deploys until auth works.

> Your previous GeoVision staging run failed on Azure login, *before* deployment. The fix is a properly scoped Microsoft Entra identity + GitHub OIDC federation, the right client/tenant/subscription IDs, and staging permissions. **Test the login before creating any further resources.**

---

## Why OIDC (not a stored secret)

With OIDC federation, GitHub Actions requests a short-lived token from Entra at run time. There is **no client secret** to store in GitHub, rotate, or leak. This directly satisfies AGENTS.md golden rule #4 (no long-lived cloud secrets).

---

## Prerequisites (you do these — they need your admin rights)

- Azure CLI (`az`) and GitHub CLI (`gh`) installed and logged in:
  ```bash
  az login
  gh auth login
  ```
- Rights to create an App Registration in your Entra tenant and to assign a role on the **staging** resource group.
- The GitHub repo for GeoVision (e.g. `valle-baobab/geovision`).

---

## Values you need to collect first

| Value | How to get it | Goes into |
|---|---|---|
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` | GitHub secret/variable |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` | GitHub secret/variable |
| `AZURE_CLIENT_ID` | created below (app registration) | GitHub secret/variable |
| Staging resource group | your existing GeoVision staging RG name | role assignment scope |
| Repo `owner/name` | e.g. `valle-baobab/geovision` | federated credential subject |

> These three IDs are **not secrets** in the OIDC model — they are identifiers. There is no password to store. Still, set them as GitHub Actions **variables** or **secrets** for tidiness, never commit them to the repo.

---

## Run it

The scripted version of everything below is in [`../scripts/azure-oidc-setup.sh`](../scripts/azure-oidc-setup.sh). Read it, set the variables at the top, then run it. Manual steps follow if you prefer to go line by line.

### 1. Create the app registration (the identity Actions will use)
```bash
az ad app create --display-name "geovision-staging-github-oidc"
APP_ID=$(az ad app list --display-name "geovision-staging-github-oidc" --query "[0].appId" -o tsv)
az ad sp create --id "$APP_ID"           # service principal for the app
```

### 2. Add the federated credential (the trust between GitHub and Entra)
Pick the subject that matches how the workflow runs. For a deploy that runs on pushes to a `staging` **environment** (recommended — it lets you add required reviewers):
```bash
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "geovision-staging-env",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:valle-baobab/geovision:environment:staging",
  "audiences": ["api://AzureADTokenExchange"]
}'
```
Other common subjects (add as separate credentials only if you need them):
- Branch: `repo:valle-baobab/geovision:ref:refs/heads/main`
- PR: `repo:valle-baobab/geovision:pull_request`

> The subject must match the workflow **exactly**, or login fails with `AADSTS70021: No matching federated identity record found`. That mismatch is the single most common cause of this blocker.

### 3. Give the identity least-privilege access to **staging only**
```bash
SUB_ID=$(az account show --query id -o tsv)
RG="geovision-staging"     # your staging resource group
az role assignment create \
  --assignee "$APP_ID" \
  --role "Contributor" \
  --scope "/subscriptions/$SUB_ID/resourceGroups/$RG"
```
Scope is the **staging resource group**, not the subscription. Never grant Owner. Tighten `Contributor` to a narrower built-in role later if the deploy only needs specific resources.

### 4. Store the identifiers in GitHub
```bash
gh variable set AZURE_CLIENT_ID       --body "$APP_ID"        --repo valle-baobab/geovision
gh variable set AZURE_TENANT_ID       --body "$(az account show --query tenantId -o tsv)" --repo valle-baobab/geovision
gh variable set AZURE_SUBSCRIPTION_ID --body "$SUB_ID"        --repo valle-baobab/geovision
```

### 5. Minimal workflow to TEST login (do this before anything else)
Create `.github/workflows/azure-login-test.yml` in the GeoVision repo:
```yaml
name: Azure login test
on: workflow_dispatch
permissions:
  id-token: write   # REQUIRED for OIDC — without this, login fails
  contents: read
jobs:
  login:
    runs-on: ubuntu-latest
    environment: staging    # must match the federated-credential subject
    steps:
      - uses: azure/login@v2
        with:
          client-id: ${{ vars.AZURE_CLIENT_ID }}
          tenant-id: ${{ vars.AZURE_TENANT_ID }}
          subscription-id: ${{ vars.AZURE_SUBSCRIPTION_ID }}
      - run: az account show
```
Then run it: `gh workflow run "Azure login test" --repo valle-baobab/geovision` and watch:
`gh run watch --repo valle-baobab/geovision`.

A green `az account show` means the blocker is cleared. Only then move on to a real staging deploy.

---

## If it fails — diagnosis, then stop (don't loop)

| Error | Cause | Fix |
|---|---|---|
| `AADSTS70021: No matching federated identity record found` | Subject mismatch | Make the federated-credential `subject` exactly match the workflow (environment/branch/PR). |
| `Unable to get ACTIONS_ID_TOKEN_REQUEST_URL` | Missing `id-token: write` | Add the `permissions:` block to the job. |
| `AuthorizationFailed` on a resource | Role/scope too narrow | Confirm the role assignment scope covers what the deploy touches (staging RG). |
| Login OK but deploy denied | Least-privilege working as intended | Grant the specific additional role on the specific resource, in staging. |

Per AGENTS.md: if login still fails after the scoped fix, **report which admin action is missing and stop** — do not generate new infrastructure or retry the broken deploy in a loop.

---

## Definition of done for Step 1
- [ ] App registration + service principal created.
- [ ] Federated credential subject matches the workflow.
- [ ] Least-privilege role assigned on the **staging** resource group only.
- [ ] `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` set in the repo.
- [ ] `azure-login-test` workflow runs green (`az account show` succeeds).
- [ ] No client secret stored anywhere.

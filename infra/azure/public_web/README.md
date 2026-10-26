# Public GeoVision website on Azure

This static-only Container App serves `geovisionops.com` and
`www.geovisionops.com` in the existing Spain Central environment. The separate
`geovision-api` app serves `api.geovisionops.com`. The private pilot and its
owner-only gateway remain separate. See the
[cutover record](../../../docs/AZURE_CUTOVER_20260923.md).

`build_site.py` accepts only tracked root HTML and public assets, applies the
existing packager's private-material/path/symlink guards, and writes a new
artifact outside the repository. It fixes the artifact's API origin to
`https://api.geovisionops.com`; source assets are unchanged. The manifest belongs
outside the deployable directory. `staticwebapp.config.json` is compatibility
metadata for static hosting; the Container App uses `site.py` for headers and
serving instead.

Build an empty context containing only `Dockerfile`, `site.py` and a `public/`
directory populated from the validated artifact (omit `staticwebapp.config.json`).
Use ACR build in `geovisionpilothcwka3w`, and deploy the returned immutable digest.
Never build this image with the repository root as the context. The fixed base
image supplies the reviewed Python runtime; the entrypoint imports only the
static server. Its managed identity is available for image pulls only.

`live.parameters.json` records the September 23 image and domain certificate
bindings. The template requires `customDomains` explicitly so a casual update
cannot silently omit the binding configuration. Before redeployment, refresh
the bindings from the current live app and update only the intended image digest:

```sh
az containerapp show -n geovision-public-web -g rg-geovision-pilot-weu \
  --subscription 50874a30-a81d-4c8a-aac7-13564bd1641d \
  --query properties.configuration.ingress.customDomains -o json
az deployment group what-if -g rg-geovision-pilot-weu \
  --subscription 50874a30-a81d-4c8a-aac7-13564bd1641d \
  --template-file infra/azure/public_web/public_web.bicep \
  --parameters @infra/azure/public_web/live.parameters.json
```

After reviewing the diff, deploy with `az deployment group create` using the same
template and parameters. Do not run the separate production-foundation workflow
as an update to these apps: it provisions a different topology and budget.
Do not recreate `geovision-api` from scratch to update it; preserve its existing
secret references, identity, environment, custom-domain binding and data sources.

Verify the homepage and login page against the artifact manifest, static private
paths return 404, and the API health/readiness and anonymous access checks pass.
For a DNS-cache-independent check, use curl's `--resolve HOST:443:68.221.208.37`
with normal TLS verification. Never disable certificate verification. DNS changes
must retain Google Workspace mail records and the separate `health` subdomain.

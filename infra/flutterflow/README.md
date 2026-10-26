# GeoVision FlutterFlow starter

Prepared 2026-09-23. The owner restored access using project [`geo-vision-ops-4y0pen`](https://app.flutterflow.io/project/geo-vision-ops-4y0pen?tab=apiConfig). **The 16-call starter is imported and saved** under `GeoVision FlutterFlow customer journey`. Chrome file access was enabled by the owner. The older project link `geo-vision-ops-ptj790` was restricted.

One call, `AzureHealth`, was added manually and saved in FlutterFlow. Its direct test returned HTTP 200 and `{"status":"ok"}` in the editor. It uses `https://geovision-api.nicepebble-b3698140.spaincentral.azurecontainerapps.io/health` with both proxy switches off. The computer's resolver still returned the old Render address for `api.geovisionops.com`, while authoritative DNS returned the new Azure CNAME, so the health check uses the Azure hostname. FlutterFlow's default proxy also failed. This verifies backend connectivity, not the complete customer journey.

`geovision-full.openapi.json` describes 408 operations exposed by the current backend's registered routers. The earlier source inventory counted 418 route declarations; declarations and registered operations are different inventories. This export does not mean every provider is activated.

`geovision-customer-journey.openapi.json` is the 16-operation starter, with only its 37 referenced schemas. Both are OpenAPI 3.1 generated from the application without starting its lifecycle or querying the database. The starter supplements runtime workspace/client headers that FastAPI cannot infer from direct request reads. No credentials or customer IDs are embedded. OpenAPI 3.1 import succeeded in the accessible project; the full 408-operation file has not been imported.

## Saved editor configuration

The group currently uses the verified Azure hostname `https://geovision-api.nicepebble-b3698140.spaincentral.azurecontainerapps.io`, with **Use Proxy for Test** and **Use Proxy for Run/Test Mode** disabled. Private/Firebase proxying is disabled. Switch to the canonical API domain after normal resolver connectivity is verified.

| Calls | Saved configuration | Verification limit |
|---|---|---|
| Login | Dynamic String `email` and `password`; `X-GeoVision-Client` default `web` | Editor sent deliberately invalid credentials to Azure and received expected 401; no successful FlutterFlow session yet |
| Registration | JSON variable `payload` replaces empty imported fields; client default `web` | Preview correctly substituted a JSON object; preview-only sample was discarded and no registration submitted |
| Site creation, dataset creation, GAIA | JSON variable `payload` supplies the complete body, preserving object/array types and omitted optional fields | Saved; not yet connected to screens |
| Refresh | Dynamic String `refreshToken` maps to `refresh_token` | Native session support only; secure storage and serialized rotation still need implementation |
| Logout | JSON variable `payload` replaces the invalid imported empty string | Pass JSON null for browser sessions, or `{ "refresh_token": token }` for native; imported `Authorization` variable takes the complete header value |
| Upload | Multipart `file` bound From Variable to `uploadedFile` of type Uploaded File | Saved; no file upload executed from FlutterFlow yet |
| Authenticated GETs, download, GAIA and creation/upload | Imported bearer and workspace headers retained; path variables retained | Inspected `/auth/me`, upload and download header/path settings; screen bindings remain pending |

`HTTPBearer` is the raw access token: the imported header already adds `Bearer `. `X-Workspace-ID` must come from the active authenticated workspace. No fixed customer IDs or credentials are saved as defaults. For the browser prototype, a 401 requires login again; web login deliberately does not issue a refresh token. Response field mappings and custom authentication are not yet configured in the editor.

## Wire the first journey

1. Use the saved starter group; do not import duplicates. Keep all tokens dynamic; never put server/provider keys in FlutterFlow. Use the canonical `https://api.geovisionops.com` once normal DNS connectivity is verified.
2. Enable Custom Authentication. For the browser prototype send `X-GeoVision-Client: web` on login/register. Map `$.access_token` to the authenticated token and `$.user.id` to the user ID; fetch `/auth/me` on session restoration. A 401 returns to login. For native builds, implement secure refresh-token storage and serialized refresh-token rotation before persisting sessions; each refresh invalidates its predecessor. Logout should call the backend then clear authentication and workspace state even if the network fails.
3. After login call `/portal/experience`, store `$.active_workspace_id` and `$.active_organization_id`, and bind `Authorization: Bearer <current token>` plus `X-Workspace-ID: <active workspace>` to authenticated customer calls. Render available actions from the returned permissions/capabilities. Do not ship a fixed workspace ID.
4. Sites page: list `/assets`; create via POST `/assets` with a name, supported sector, `asset_type: SITE`, and GeoJSON Point coordinates `[longitude, latitude]`. Validate longitude −180…180 and latitude −90…90. Show the returned site only after 201. Prevent double-submit; do not blindly retry POST requests.
5. Upload page: choose the site, create a dataset through POST `/datasets/` with `asset_id`, `name`, a suitable `dataset_type`, and `source_tool: manual`. Retain the returned dataset ID if uploading fails, so retry does not create another dataset. Upload the local file as multipart field `file` to `/datasets/{dataset_id}/upload`; let the client generate the multipart boundary. Record the returned file ID. Obtain a fresh signed download URL only when needed; do not persist or log signed URLs.
6. Map page: `/portal/map-layers` returns the authorized map content. The existing web journey already passed real site, upload, exact download and workspace isolation checks on Azure (see `docs/CUSTOMER_JOURNEY_20260923.md`). FlutterFlow screens still need their own end-to-end run.
7. GAIA: POST `/ai/chat` with the same authentication/workspace headers; display the real reply and handle timeouts visibly. This call has already reached the configured model from the existing website.

The canonical Azure API now allows CORS from `https://app.flutterflow.io` in addition to the GeoVision domain and www (revision `geovision-api--ffcors0923`). Preflight checks passed for the editor and website; an unrelated origin was rejected; readiness returned 200 and unauthenticated `/auth/me` returned 401. See `docs/flutterflow-evidence/20260923/azure-cors-checks.json`. For a browser preview or FlutterFlow-hosted build, add its exact origin after the actual project/preview origin is known. Do not use a wildcard to make an unknown preview work.

## Completion checks in FlutterFlow

Login → workspace → create site → create dataset → upload → download the same bytes → sign out → sign back in. Verify unauthenticated access fails and one account cannot read another workspace. Run on the intended web/mobile targets. The 16-call import and request-body repairs are saved; response mappings, screen wiring, session handling and this end-to-end journey remain unverified.

References: [API import](https://docs.flutterflow.io/resources/backend-logic/create-test-api/), [custom authentication](https://docs.flutterflow.io/integrations/authentication/custom-authentication/), [file uploads](https://docs.flutterflow.io/concepts/file-handling/uploading-files/).

# Construction reporting + QR asset inspections

A low-capital service that uses only existing GeoVision software + a phone: tag assets with
QR codes, a technician scans → logs a field inspection → GeoVision produces a PDF report.

## Design
Reuses the existing **`IotAsset`** as the QR-taggable, inspectable asset (company/site/location/
external_reference already there). One new model **`AssetInspection`** stores each inspection.
No new app, no new auth — rides on existing tenants/sites/assets.

- Model: `backend/app/models.py::AssetInspection`
- Migration: `alembic/versions/construction_inspections_v1.py` (adds `asset_inspections`)
- Router: `backend/app/routers/construction.py`
- Scan page: `inspect.html` (mobile-friendly form the QR points to)
- Dependency: `qrcode` (pure-python SVG QR, added to requirements)
- Tests: `backend/tests/test_construction.py`

## API
- `GET /construction/assets/{id}/qr.svg` — QR (SVG) encoding `…/inspect.html?asset={id}&site={site}`.
- `POST /construction/inspections` — `{asset_id, category, result(pass|attention|fail), notes, checklist{}, photos[], latitude?, longitude?}`. Missing coords inherit the asset's.
- `GET /construction/inspections` — tenant-scoped list.
- `GET /construction/assets/{id}/inspections` — per-asset history.
- `GET /construction/assets/{id}/report.pdf` — inspection report (customer, site, asset, pass/attention/fail counts, timeline).

## Verified (executed)
- 24 backend tests pass (incl. `test_construction_qr_inspection_and_report`, `test_construction_tenant_isolation`).
- Migration applies cleanly on a fresh DB → `construction_inspections_v1 (head)`.
- Live in the app: created asset "Pilar Norte B3", opened `inspect.html?asset=…`, submitted a
  `structural/attention` inspection → "✔ Inspeção registada", persisted, report PDF generated.

## Notes
- `inspect.html` requires a logged-in GeoVision user (redirects to `login.html?next=…`). The QR
  therefore assumes the technician has an account; a public/token-based scan flow can be added later.
- Photos are stored as references/URLs (no binary upload in this MVP).

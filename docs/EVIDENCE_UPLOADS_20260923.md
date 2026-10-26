# Real service-request evidence — 2026-09-23

The existing Flutter screens now upload real evidence to the Azure dataset API before submitting a service request. The FlutterFlow project was not overwritten. The previous journey fixes remain in place.

## Customer behavior

- Choose the asset, describe the request, and optionally select files from Files or Photos. Supported formats: JPG/JPEG, PNG, PDF and CSV. Maximum five files, 10 MiB each and 25 MiB combined.
- The asset is locked while files are selected. Remove the selections before changing asset. The form states that leaving it clears selections; binary files are not queued offline.
- Submission creates an asset-scoped evidence dataset and uploads each file. No request is submitted or queued if an upload fails. Selections remain in the open form for retry; cancel stops the upload operation.
- A retry checks confirmed server files by filename, byte length and SHA-256 before uploading again, including when the original upload response was lost. A lost dataset-creation response may leave an empty dataset.
- After uploads finish, the existing durable request queue handles connectivity loss. Pending requests explain that the server has not confirmed them; attached files become openable after confirmation.
- Request details show actual file names and sizes. Open/save downloads authenticated bytes and validates the checksum. Historical references without a confirmed file show unavailable, rather than pretending a file exists.
- Removing a file from an unsubmitted request removes only the selection. Already uploaded objects remain in their asset dataset; this feature does not delete stored evidence.

## Server contract

The existing `POST /datasets/`, `GET /datasets/{id}` and multipart `POST /datasets/{id}/upload` are reused. Requests persist `dataset-file:<id>` references. Only confirmed, uploaded, undeleted files in a nonarchived dataset belonging to the exact organization, workspace and asset are accepted. Duplicate, fabricated, oversized and wrong-asset references return 400. Existing idempotent request replays remain valid when a file later becomes unavailable.

Request responses add `attachment_files` with safe metadata. The new authenticated `GET /mobile/service-requests/{request_id}/attachments/{file_id}` verifies request access, attachment membership, current file scope, storage provider, byte length and checksum. Responses use controlled content types, attachment disposition, `nosniff` and private/no-store caching. No database migration is needed.

## Validation

- Backend: 39 service-journey, security and provider-readiness tests passed. Evidence-specific cases use actual multipart uploads and storage, including cross-workspace denial, incomplete/deleted files, idempotent replay and changed stored bytes.
- Flutter: 106 tests passed, two existing opt-in skips; static analysis clean. Added upload/authentication, retry reconciliation, corrupt content, permission denial, cancellation, workspace changes and file-limit checks.
- iPhone 15 simulator debug build and native acceptance passed: real Azure login, selected-asset request screen, attachment selection, multipart upload, submitted-request detail, authenticated byte retrieval and logout. The picker alone is injected with a labelled synthetic CSV; subsequent API calls are real.
- The normal Azure-connected app was rebuilt, installed and relaunched at the Spanish login screen after acceptance.
- Existing owner changes to `mobile/ios/Podfile.lock` (44 deletions) are preserved. Native compilation uses an isolated copy.

## Azure rollout

- Healthy revision `geovision-api--evidence0923`, 100% traffic. Prior `geovision-api--journey0923` retained for rollback.
- Image digest `sha256:dba2e8c8e3e68899042143ab7a8c086ee3ff833da11533e16ad5e01977cd3396`. Existing nine secrets preserved; image-only application update.
- Live synthetic CSV upload → request → authenticated download succeeded; exact bytes/checksum match, canonical asset preserved, idempotent replay 200, anonymous download 401, fabricated reference 400. Evidence: [live results](mobile-evidence/20260923/evidence-live-validation.json).
- Acceptance uses the configured Azure FQDN; it makes no claim about universal custom-domain DNS propagation.

## Remaining gates

This is source/API/simulator delivery, not an App Store or Play Store release. Native acceptance injects a synthetic CSV selection; it does not claim a complete real-device Files/Photos permission matrix. Offline binary uploads are not implemented.

The synthetic Azure QA account has only `report:read`; its workspace has no published report. A reviewer must supply a properly approved/published report for customer PDF acceptance. No administrative access or approval was fabricated.

One authorized transactional email was SMTP-accepted, then Azure reported SMTP 550 failure at 04:04 UTC. The owner reported non-receipt. Domain/SPF/DKIM verification remains successful. Detailed delivery logging is now enabled; a second diagnostic test was explicitly authorized and SMTP-accepted at 04:20 UTC, then also failed with SMTP 550 at 04:24 UTC. Detailed log queries have not yet returned the rejection text. Email delivery and password-reset inbox acceptance remain unresolved. See `infra/azure/email/README.md`.

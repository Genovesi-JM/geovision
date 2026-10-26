# Azure transactional email

Provisioned on 2026-09-23 in `rg-geovision-pilot-weu`, Europe data geography:

- Email service: `geovision-email-hcwka3w`
- Sending domain: `notify.geovisionops.com`
- Communication service: `geovision-comm-hcwka3w`
- Dedicated Entra application: `20911d9e-5a82-4bc2-bc1d-b66b00a69cf3`
- Service principal: `9a2847da-8cd5-4d19-a392-cd2796f446f9`
- SMTP username resource: `geovision-app`, username `geovision-app-hcwka3w`
- Custom `GeoVision SMTP Sender` role, assigned only at the communication-service resource scope. Contains the three documented ACS SMTP permissions. No subscription-wide role grant.

**SMTP is configured in the canonical application**, ready revision `geovision-api--smtp0923`. Azure reports Domain, SPF, DKIM and DKIM2 as Verified. The sending domain is linked to the communication service, and sender `no-reply@notify.geovisionops.com` (display name GeoVision) exists. SMTP authentication returned 235 over STARTTLS both locally and from the running API container. One owner-authorized delivery test was SMTP-accepted at 04:01 UTC, then failed at 04:04 UTC with SMTP 550. The owner confirmed non-receipt. Inbox delivery is not working for this test. Google Workspace MX records were preserved.

## Saved DNS records

Names below are relative to `geovisionops.com`. All four records were saved in Squarespace after the owner's security verification, with TTL 4 hours. Do not add duplicates or replace existing Google Workspace records.

| Type | Name | Value |
|---|---|---|
| TXT | notify | ms-domain-verification=b87f7e75-823f-45e2-baf2-3a108550f45f |
| TXT | notify | v=spf1 include:spf.protection.outlook.com -all |
| CNAME | selector1-azurecomm-prod-net._domainkey.notify | selector1-azurecomm-prod-net._domainkey.azurecomm.net |
| CNAME | selector2-azurecomm-prod-net._domainkey.notify | selector2-azurecomm-prod-net._domainkey.azurecomm.net |

Domain, SPF, DKIM and DKIM2 verification, domain linking and `no-reply` sender creation are complete. `foundation.bicep` requires explicit `linkedDomainIds` so a later deployment cannot silently assume an empty list. Initial deployment used an empty link list; future deployments must include the linked domain resource ID.

The canonical `geovision-api` now uses `NOTIFICATION_PROVIDER=smtp`, host `smtp.azurecomm.net`, port 587, STARTTLS, sender `no-reply@notify.geovisionops.com`, and username `geovision-app-hcwka3w`. `SMTP_PASSWORD` refers to Container Apps secret `provider-azure-smtp-password`. All eight existing secrets, domain bindings, identity, image, scaling and unrelated environment values were preserved. Readiness returned 200 after deployment.

The app credential expires **2027-09-23 00:00 UTC**. It is stored in the production Container Apps secret configuration and the owner's private migration directory with mode 0600; no credential is in the repository or this document. Rotate before expiry.

Backend synchronous email and the durable notification delivery worker are separate paths. The read-only runtime audit found zero rows in `notification_deliveries`. A dedicated delivery worker has not been activated. Provider configuration alone does not establish successful invite/alert delivery. [Runtime evidence](../../../docs/activation-evidence/20260923/email-runtime-evidence.json) records the selected real SMTP provider, complete configuration, expected sender, successful authentication and empty queue without credentials or recipient data.

The first authorized test was sent. A second test with the same recipient, subject and body was separately authorized and SMTP-accepted at 04:20 UTC; it also failed with SMTP 550 at 04:24 UTC. No detailed rejection text was available from the newly enabled logs at the last check. Do not send further messages automatically. Aggregate Azure `DeliveryStatusUpdate` metrics report Failed / Failure / SMTP 550, without an enhanced code or rejection text. Domain/SPF/DKIM/DKIM2 remain Verified. Detailed EmailSendMailOperational and EmailStatusUpdateOperational diagnostics are now enabled into the existing Log Analytics workspace; these were enabled after the failed message and cannot guarantee retrospective details. The recipient domain uses IONOS MX. This evidence does not identify whether the cause is recipient validity, filtering/reputation or another receiving policy. A further test requires an authorized recipient/message; do not mark password-reset delivery validated.

[Microsoft SMTP authentication and permissions](https://learn.microsoft.com/en-us/azure/communication-services/quickstarts/email/send-email-smtp/smtp-authentication)

Diagnostic schema: [Microsoft email delivery log fields](https://learn.microsoft.com/en-us/azure/azure-monitor/reference/tables/acsemailstatusupdateoperational). `FailureReason` and `FailureMessage` are the relevant fields once a delivery record is available. Saved query: `delivery-status.kql`.

# IoT security

- One-time provisioning tokens expire in 30 minutes and are consumed once.
- Permanent secrets are returned once, hashed for REST verification and encrypted for MQTT HMAC verification.
- `ENCRYPTION_KEY` is mandatory with MQTT in production; real keys remain outside Git.
- MQTT envelopes use TLS, HMAC, timestamp validation, nonce replay protection and tenant/site/topic matching.
- REST uses per-device credentials, typed schemas, rate limits and durable
  message/stream idempotency receipts.
- Azure IoT Hub Event Grid ingress is disabled by default and requires the
  selected provider, exact configured hub, and constant-time comparison of a
  backend-only custom delivery secret. External device IDs resolve only through
  registered provider mappings.
- Context and measurement metadata reject credential-like fields; webhook and
  device secrets are redacted from configuration representations.
- User APIs enforce customer ownership; unauthorized tenant resources return 404.
- Commands are allowlisted, signed, expiring, confirmed, audited and constrained to low voltage.

Production gates: unique broker accounts/ACLs or mutual TLS, managed CA/key
rotation, restricted Event Grid routing/secret rotation, distributed
multi-instance rate/fan-out, physical fail-safe tests, penetration test, backup
restore test, retention approval, monitoring, incident response and privacy
review.

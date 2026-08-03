# IoT security

- One-time provisioning tokens expire in 30 minutes and are consumed once.
- Permanent secrets are returned once, hashed for REST verification and encrypted for MQTT HMAC verification.
- `ENCRYPTION_KEY` is mandatory with MQTT in production; real keys remain outside Git.
- MQTT envelopes use TLS, HMAC, timestamp validation, nonce replay protection and tenant/site/topic matching.
- REST uses per-device credentials, typed schemas, rate limits and idempotent message IDs.
- User APIs enforce customer ownership; unauthorized tenant resources return 404.
- Commands are allowlisted, signed, expiring, confirmed, audited and constrained to low voltage.

Production gates: unique broker accounts/ACLs or mutual TLS, managed CA/key rotation, Redis multi-instance rate/fan-out, penetration test, backup restore test, retention approval, monitoring, incident response and privacy review.

# Safe controls

Phase-one allowed controls are beacon, buzzer, demonstration fan, small low-voltage valve, low-voltage relay, reporting interval, restart and diagnostics. Mains, industrial pumps/generators and medical treatment equipment are explicitly excluded.

GeoVision requires an operator role, explicit confirmation, declared device capability, reason, expiry, correlation ID and audit entry. Output commands additionally require remote control enabled and a fresh `safety_ok=true` channel. Devices validate the server HMAC, apply a local safe-mode/interlock, acknowledge actual state and retain a physical override. The declared fail-safe state is `off` unless engineering review specifies otherwise.

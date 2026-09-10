# Safe controls

Phase-one allowed controls are beacon, buzzer, demonstration fan, small low-voltage valve, low-voltage relay, reporting interval, restart and diagnostics. Mains, industrial pumps/generators and medical treatment equipment are explicitly excluded.

GeoVision requires an operator role, explicit confirmation, declared device capability, reason, expiry, correlation ID and audit entry. Output commands additionally require remote control enabled and a fresh `safety_ok=true` channel. Devices validate the server HMAC, apply a local safe-mode/interlock, acknowledge actual state and retain a physical override. The declared fail-safe state is `off` unless engineering review specifies otherwise.

Remote control is disabled on every newly registered device unless a human
explicitly enables it. The Raspberry Pi FieldBox reference accepts only
diagnostic/configuration or de-energizing commands by default; opening a valve,
turning on a relay, or energizing equipment is rejected. Local leak, empty-tank,
link-loss and maximum-run rules can always close/de-energize outputs without
cloud availability. Delayed/out-of-order telemetry is historical evidence only
and cannot trigger cloud automation.

# Alerts

Rules are tenant scoped and can target a site, device and channel. Implemented comparisons include above/below/equal/not-equal and rapid rise/fall. Boolean leak/door state uses normalized 1/0 values. Offline state comes from signed last will or heartbeat watchdog.

Lifecycle states are `pending → triggered → notified → acknowledged → assigned → resolved → closed`. `pending` enforces the rule's sustained-condition time; cooldown suppresses immediate retriggering. Automatic evaluation notifies and resolves; authenticated operators acknowledge, assign and close. The log adapter is safe and functional locally. Email, Telegram, push, SMS and WhatsApp adapters refuse operation until credentials are configured.

Do not treat an alert as a safety instrument. Local controllers must enforce physical interlocks independently of cloud availability.

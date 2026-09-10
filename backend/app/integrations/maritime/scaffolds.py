"""Named maritime integrations that deliberately perform no network I/O."""

from __future__ import annotations

from app.core.integration import TimeoutPolicy

from .unavailable import UnavailableMaritimeProvider


PUERTOS_OCEANOGRAPHY_TERMS_URL = "https://www.puertos.es/servicios/oceanografia/faqs"


class MarineTrafficMaritimeScaffold(UnavailableMaritimeProvider):
    provider_name = "marinetraffic"

    def __init__(self, *, timeout_policy: TimeoutPolicy) -> None:
        super().__init__(
            self.provider_name,
            (
                "MarineTraffic AIS API entitlement, customer scope, and sandbox "
                "approval are not configured; AIS is context only and is not a "
                "collision-avoidance or safety authority"
            ),
            failure_code="provider_not_configured",
            timeout_policy=timeout_policy,
        )


class KplerMaritimeScaffold(UnavailableMaritimeProvider):
    provider_name = "kpler"

    def __init__(self, *, timeout_policy: TimeoutPolicy) -> None:
        super().__init__(
            self.provider_name,
            (
                "Kpler maritime-data entitlement, customer scope, and sandbox "
                "approval are not configured; maritime context is not a "
                "collision-avoidance or safety authority"
            ),
            failure_code="provider_not_configured",
            timeout_policy=timeout_policy,
        )


class PuertosDelEstadoMaritimeScaffold(UnavailableMaritimeProvider):
    provider_name = "puertos_del_estado"
    terms_url = PUERTOS_OCEANOGRAPHY_TERMS_URL

    def __init__(self, *, timeout_policy: TimeoutPolicy) -> None:
        super().__init__(
            self.provider_name,
            (
                "Puertos del Estado authorization for third-party SaaS display, "
                "redistribution, caching, and derived alerts has not been approved; "
                "written permission and a reviewed HTTPS access contract are required"
            ),
            failure_code="authorization_terms_not_approved",
            timeout_policy=timeout_policy,
        )


__all__ = [
    "KplerMaritimeScaffold",
    "MarineTrafficMaritimeScaffold",
    "PUERTOS_OCEANOGRAPHY_TERMS_URL",
    "PuertosDelEstadoMaritimeScaffold",
]

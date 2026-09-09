"""Lazy construction of the configured payment gateway adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from app.core.config import Settings, settings

if TYPE_CHECKING:
    from app.modules.billing.ports import PaymentProvider as BillingPaymentProvider
    from app.services.payments import PaymentAdapter, PaymentProvider


def create_payment_adapters(
    config: Optional[Settings] = None,
) -> Dict["PaymentProvider", "PaymentAdapter"]:
    """Build the legacy-compatible adapter map without global SDK imports."""

    from app.services.payments import PaymentProvider

    from .adapters import (
        IBANTransferAdapter,
        MulticaixaExpressAdapter,
        PayPalAdapter,
        VisaMastercardAdapter,
    )

    runtime_config = config or settings
    return {
        PaymentProvider.MULTICAIXA_EXPRESS: MulticaixaExpressAdapter(runtime_config),
        PaymentProvider.VISA_MASTERCARD: VisaMastercardAdapter(runtime_config),
        PaymentProvider.IBAN_TRANSFER: IBANTransferAdapter(runtime_config),
        PaymentProvider.PAYPAL: PayPalAdapter(runtime_config),
    }


def create_billing_payment_providers(
    config: Optional[Settings] = None,
) -> Dict[str, "BillingPaymentProvider"]:
    """Build adapters that implement the module-owned normalized port."""

    from .normalized import as_billing_payment_provider

    adapters = create_payment_adapters(config)
    return {
        provider.value: as_billing_payment_provider(adapter)
        for provider, adapter in adapters.items()
    }


__all__ = ["create_billing_payment_providers", "create_payment_adapters"]

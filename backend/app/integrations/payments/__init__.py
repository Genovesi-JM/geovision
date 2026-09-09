"""Payment gateway adapters, loaded only when a concrete provider is requested."""

from importlib import import_module


_ADAPTER_EXPORTS = {
    "IBANTransferAdapter",
    "MulticaixaExpressAdapter",
    "PayPalAdapter",
    "VisaMastercardAdapter",
}


def __getattr__(name: str):
    if name in {"create_billing_payment_providers", "create_payment_adapters"}:
        value = getattr(import_module("app.integrations.payments.factory"), name)
    elif name in {"NormalizedPaymentProviderAdapter", "as_billing_payment_provider"}:
        value = getattr(import_module("app.integrations.payments.normalized"), name)
    elif name in _ADAPTER_EXPORTS:
        value = getattr(import_module("app.integrations.payments.adapters"), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    return sorted(
        set(globals())
        | _ADAPTER_EXPORTS
        | {
            "NormalizedPaymentProviderAdapter",
            "as_billing_payment_provider",
            "create_billing_payment_providers",
            "create_payment_adapters",
        }
    )


__all__ = [
    "IBANTransferAdapter",
    "MulticaixaExpressAdapter",
    "NormalizedPaymentProviderAdapter",
    "PayPalAdapter",
    "VisaMastercardAdapter",
    "as_billing_payment_provider",
    "create_billing_payment_providers",
    "create_payment_adapters",
]

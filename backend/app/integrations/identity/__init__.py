"""Identity-provider adapters and composition helpers."""

from .entra_external_id import (
    EntraExternalIdProvider,
    JsonDocumentFetcher,
    RequestsJsonDocumentFetcher,
)
from .factory import (
    TransitionIdentityProvider,
    clear_identity_provider_cache,
    create_entra_external_id_provider,
    create_identity_provider,
    get_identity_provider,
)
from .internal import InternalIdentityProvider

__all__ = [
    "EntraExternalIdProvider",
    "InternalIdentityProvider",
    "JsonDocumentFetcher",
    "RequestsJsonDocumentFetcher",
    "TransitionIdentityProvider",
    "clear_identity_provider_cache",
    "create_entra_external_id_provider",
    "create_identity_provider",
    "get_identity_provider",
]

"""External text-generation port owned by the analytics domain."""

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable

from app.core.integration import IntegrationResult


@runtime_checkable
class TextGenerationProvider(Protocol):
    """Generate narrative text without making the provider numerical truth."""

    provider_name: str

    async def generate(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        context: Mapping[str, Any],
    ) -> IntegrationResult[str]: ...


__all__ = ["TextGenerationProvider"]

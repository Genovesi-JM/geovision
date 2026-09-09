"""Notification provider port owned by the notifications domain."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Protocol, runtime_checkable

from app.core.integration import IntegrationResult


@dataclass(frozen=True, slots=True)
class NotificationMessage:
    recipient: str
    subject: str
    plain_text: str
    html: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@runtime_checkable
class NotificationProvider(Protocol):
    provider_name: str

    def send(self, message: NotificationMessage) -> IntegrationResult[None]: ...


__all__ = ["NotificationMessage", "NotificationProvider"]

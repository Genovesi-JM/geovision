"""Registry-only validation responses that never echo rejected request values."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse, Response
from starlette.status import HTTP_422_UNPROCESSABLE_CONTENT


_REQUEST_LOCATION_ROOTS = frozenset({"body", "cookie", "header", "path", "query"})


def _safe_location(error: dict[str, Any]) -> list[str]:
    """Retain only the framework-controlled request source from an error path."""

    location = error.get("loc")
    if isinstance(location, (list, tuple)) and location:
        root = location[0]
        if isinstance(root, str) and root in _REQUEST_LOCATION_ROOTS:
            return [root]
    return ["request"]


def _safe_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Keep safe validation metadata without reflecting attacker-controlled text."""

    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        errors.append(
            {
                "type": str(error.get("type") or "value_error"),
                "loc": _safe_location(error),
                "msg": "Request validation failed",
            }
        )
    return errors


class RedactedValidationRoute(APIRoute):
    """Apply secret-free request-validation responses to registry routes only."""

    def get_route_handler(self) -> Callable[[Request], Any]:
        original_handler = super().get_route_handler()

        async def secret_safe_handler(request: Request) -> Response:
            try:
                return await original_handler(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                    content={"detail": _safe_errors(exc)},
                )

        return secret_safe_handler


__all__ = ["RedactedValidationRoute"]

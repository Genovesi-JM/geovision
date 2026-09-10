"""NodeODM/OpenDroneMap adapter behind the GeoVision processing port."""

from __future__ import annotations

from io import BytesIO
import json
import mimetypes
from pathlib import PurePosixPath
import re
import uuid
from zipfile import BadZipFile, ZipFile

import httpx

from app.core.config import Settings, settings
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    sanitize_integration_message,
)
from app.modules.processing.ports import (
    NormalizedProcessingOutput,
    ProcessingRequest,
    ProcessingStatus,
    ProcessingSubmission,
    ProviderArtifact,
)

from .normalization import classify_output_path, normalize_provider_artifacts


_REFERENCE = re.compile(r"^[A-Za-z0-9_-]{1,240}$")
_OPTION_NAME = re.compile(r"^[a-z][a-z0-9-]{0,79}$")
_ALLOWED_OPTIONS = frozenset(
    {
        "auto-boundary",
        "cog",
        "crop",
        "dem-resolution",
        "dsm",
        "dtm",
        "fast-orthophoto",
        "feature-quality",
        "matcher-neighbors",
        "mesh-octree-depth",
        "min-num-features",
        "orthophoto-resolution",
        "pc-quality",
        "radiometric-calibration",
        "skip-3dmodel",
        "use-3dmesh",
    }
)
_STATUS_CODES = {
    10: "SUBMITTED",
    20: "RUNNING",
    30: "FAILED",
    40: "COMPLETED",
    50: "CANCELLED",
}


class NodeODMProcessingProvider:
    provider_name = "nodeodm"

    def __init__(
        self,
        config: Settings = settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.base_url = (config.nodeodm_base_url or "").rstrip("/")
        self.token = config.nodeodm_token
        timeout = httpx.Timeout(
            connect=config.integration_connect_timeout_seconds,
            read=config.processing_provider_read_timeout_seconds,
            write=config.processing_provider_write_timeout_seconds,
            pool=config.integration_connect_timeout_seconds,
        )
        self.client = client or httpx.Client(timeout=timeout, follow_redirects=False)

    def _params(self) -> dict[str, str]:
        return {"token": self.token} if self.token else {}

    def _failure(
        self,
        operation: str,
        *,
        code: str,
        message: object,
        retryable: bool,
    ):
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=(
                IntegrationStatus.RETRYING if retryable else IntegrationStatus.FAILED
            ),
            failure=IntegrationFailure(
                code=code,
                message=sanitize_integration_message(
                    message, secret_values=((self.token or ""),)
                ),
                retryable=retryable,
            ),
        )

    def _http_failure(self, operation: str, exc: Exception):
        if isinstance(exc, httpx.TimeoutException):
            return self._failure(
                operation,
                code="timeout",
                message="NodeODM request timed out",
                retryable=True,
            )
        return self._failure(
            operation,
            code="provider_unavailable",
            message="NodeODM could not be reached",
            retryable=True,
        )

    def _response_failure(self, operation: str, response: httpx.Response):
        status = response.status_code
        if status in {401, 403}:
            code, message, retryable = (
                "authentication_failed",
                "NodeODM rejected its configured credential",
                False,
            )
        elif status == 429:
            code, message, retryable = (
                "rate_limited",
                "NodeODM temporarily rate limited the request",
                True,
            )
        elif status >= 500:
            code, message, retryable = (
                "provider_unavailable",
                "NodeODM temporarily rejected the request",
                True,
            )
        else:
            code, message, retryable = (
                "provider_rejected",
                f"NodeODM rejected the request with HTTP {status}",
                False,
            )
        return self._failure(
            operation,
            code=code,
            message=message,
            retryable=retryable,
        )

    @staticmethod
    def _reference(value: str) -> str:
        normalized = str(value or "").strip()
        if not _REFERENCE.fullmatch(normalized):
            raise ValueError("NodeODM returned an invalid task reference")
        return normalized

    @staticmethod
    def _options(request: ProcessingRequest) -> list[dict[str, object]]:
        values: dict[str, object] = {}
        for raw_name, value in request.options.items():
            name = str(raw_name).strip().lower().replace("_", "-")
            if name not in _ALLOWED_OPTIONS or not _OPTION_NAME.fullmatch(name):
                raise ValueError(f"NodeODM option is not allowlisted: {name}")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"NodeODM option must be scalar: {name}")
            values[name] = value
        if "DSM" in request.requested_outputs:
            values["dsm"] = True
        if "DTM" in request.requested_outputs:
            values["dtm"] = True
        if "MESH_3D" not in request.requested_outputs:
            values.setdefault("skip-3dmodel", True)
        values.setdefault("cog", True)
        return [{"name": name, "value": value} for name, value in sorted(values.items())]

    def _server_identity(self) -> tuple[str, str | None]:
        try:
            response = self.client.get(f"{self.base_url}/info", params=self._params())
            if response.status_code != 200:
                return "OpenDroneMap", None
            payload = response.json()
            if not isinstance(payload, dict):
                return "OpenDroneMap", None
            engine = str(payload.get("engine") or "OpenDroneMap")[:120]
            version = str(
                payload.get("engineVersion") or payload.get("version") or ""
            )[:120]
            return engine, version or None
        except (httpx.HTTPError, TypeError, ValueError):
            return "OpenDroneMap", None

    def submit(
        self,
        request: ProcessingRequest,
        *,
        idempotency_key: str,
    ) -> IntegrationResult[ProcessingSubmission]:
        operation = "submit"
        if not self.base_url:
            return self._failure(
                operation,
                code="not_configured",
                message="NodeODM base URL is not configured",
                retryable=False,
            )
        try:
            options = self._options(request)
            task_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:{idempotency_key}")
            )
            files = [
                (
                    "images",
                    (item.filename, item.content, item.content_type),
                )
                for item in request.inputs
            ]
            response = self.client.post(
                f"{self.base_url}/task/new",
                params=self._params(),
                headers={"set-uuid": task_uuid},
                data={"name": request.name, "options": json.dumps(options)},
                files=files,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            return self._http_failure(operation, exc)
        except ValueError as exc:
            return self._failure(
                operation,
                code="invalid_request",
                message=exc,
                retryable=False,
            )
        if response.status_code == 409:
            reference = task_uuid
        elif response.status_code != 200:
            return self._response_failure(operation, response)
        else:
            try:
                payload = response.json()
                reference = self._reference(
                    payload.get("uuid") if isinstance(payload, dict) else ""
                )
            except (TypeError, ValueError) as exc:
                return self._failure(
                    operation,
                    code="invalid_response",
                    message=exc,
                    retryable=False,
                )
        processor_name, processor_version = self._server_identity()
        return IntegrationResult.accepted(
            provider=self.provider_name,
            operation=operation,
            value=ProcessingSubmission(
                external_reference=reference,
                state="SUBMITTED",
                processor_name=processor_name,
                processor_version=processor_version,
            ),
        )

    def status(self, external_reference: str) -> IntegrationResult[ProcessingStatus]:
        operation = "status"
        try:
            reference = self._reference(external_reference)
            response = self.client.get(
                f"{self.base_url}/task/{reference}/info", params=self._params()
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            return self._http_failure(operation, exc)
        except ValueError as exc:
            return self._failure(
                operation, code="invalid_reference", message=exc, retryable=False
            )
        if response.status_code != 200:
            return self._response_failure(operation, response)
        try:
            payload = response.json()
            raw_status = payload.get("status") if isinstance(payload, dict) else None
            code = int(raw_status.get("code")) if isinstance(raw_status, dict) else -1
            state = _STATUS_CODES[code]
            progress = min(max(float(payload.get("progress") or 0.0), 0.0), 100.0)
        except (KeyError, TypeError, ValueError) as exc:
            return self._failure(
                operation,
                code="invalid_response",
                message=exc,
                retryable=False,
            )
        result = ProcessingStatus(
            state=state,
            progress_percent=progress,
            stage=f"nodeodm_{state.lower()}",
            error_code="processing_failed" if state == "FAILED" else None,
            error_message=(
                "NodeODM reported that processing failed" if state == "FAILED" else None
            ),
        )
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation=operation,
            value=result,
        )

    def cancel(self, external_reference: str) -> IntegrationResult[bool]:
        operation = "cancel"
        try:
            reference = self._reference(external_reference)
            response = self.client.post(
                f"{self.base_url}/task/cancel",
                params=self._params(),
                json=reference,
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            return self._http_failure(operation, exc)
        except ValueError as exc:
            return self._failure(
                operation, code="invalid_reference", message=exc, retryable=False
            )
        if response.status_code != 200:
            return self._response_failure(operation, response)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation=operation,
            value=True,
        )

    def retrieve_outputs(
        self, external_reference: str
    ) -> IntegrationResult[tuple[ProviderArtifact, ...]]:
        operation = "retrieve_outputs"
        try:
            reference = self._reference(external_reference)
            response = self.client.get(
                f"{self.base_url}/task/{reference}/download/all.zip",
                params=self._params(),
            )
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            return self._http_failure(operation, exc)
        except ValueError as exc:
            return self._failure(
                operation, code="invalid_reference", message=exc, retryable=False
            )
        if response.status_code != 200:
            return self._response_failure(operation, response)
        if len(response.content) > self.config.processing_max_output_archive_bytes:
            return self._failure(
                operation,
                code="output_archive_too_large",
                message="NodeODM output archive exceeds the configured safety limit",
                retryable=False,
            )
        try:
            with ZipFile(BytesIO(response.content)) as archive:
                members = archive.infolist()
                if len(members) > self.config.processing_max_output_files:
                    raise ValueError("NodeODM output archive contains too many files")
                total_size = sum(member.file_size for member in members)
                if total_size > self.config.processing_max_output_unpacked_bytes:
                    raise ValueError("NodeODM output archive expands beyond the safety limit")
                artifacts: list[ProviderArtifact] = []
                for member in members:
                    path = PurePosixPath(member.filename.replace("\\", "/"))
                    if (
                        member.is_dir()
                        or path.is_absolute()
                        or ".." in path.parts
                        or classify_output_path(str(path)) is None
                    ):
                        continue
                    if member.file_size <= 0:
                        continue
                    if member.compress_size and member.file_size / member.compress_size > 500:
                        raise ValueError("NodeODM output archive has an unsafe compression ratio")
                    artifacts.append(
                        ProviderArtifact(
                            relative_path=str(path),
                            content=archive.read(member),
                            content_type=(
                                mimetypes.guess_type(path.name)[0]
                                or "application/octet-stream"
                            ),
                        )
                    )
        except (BadZipFile, KeyError, OSError, ValueError) as exc:
            return self._failure(
                operation,
                code="invalid_output_archive",
                message=exc,
                retryable=False,
            )
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation=operation,
            value=tuple(artifacts),
        )

    def normalize_outputs(
        self,
        outputs: tuple[ProviderArtifact, ...],
        *,
        requested_outputs: tuple[str, ...],
    ) -> IntegrationResult[tuple[NormalizedProcessingOutput, ...]]:
        return normalize_provider_artifacts(
            self.provider_name,
            outputs,
            requested_outputs=requested_outputs,
        )


__all__ = ["NodeODMProcessingProvider"]

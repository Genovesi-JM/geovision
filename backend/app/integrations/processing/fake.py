"""Deterministic, dependency-free processor for tests and local demos."""

from __future__ import annotations

import uuid

from app.core.integration import IntegrationResult
from app.modules.processing.ports import (
    NormalizedProcessingOutput,
    ProcessingRequest,
    ProcessingStatus,
    ProcessingSubmission,
    ProviderArtifact,
)

from .normalization import normalize_provider_artifacts


_FAKE_ARTIFACTS = (
    ProviderArtifact(
        "odm_orthophoto/odm_orthophoto.tif",
        b"II*\x00GEOVISION-DETERMINISTIC-ORTHOMOSAIC",
        "image/tiff",
    ),
    ProviderArtifact("odm_dem/dsm.tif", b"II*\x00GEOVISION-DSM", "image/tiff"),
    ProviderArtifact("odm_dem/dtm.tif", b"II*\x00GEOVISION-DTM", "image/tiff"),
    ProviderArtifact(
        "odm_georeferencing/odm_georeferenced_model.laz",
        b"LASFGEOVISION-POINT-CLOUD",
        "application/octet-stream",
    ),
    ProviderArtifact(
        "odm_texturing/odm_textured_model_geo.obj",
        b"# GeoVision deterministic mesh\no mesh\nv 0 0 0\n",
        "text/plain",
    ),
    ProviderArtifact(
        "odm_orthophoto/odm_orthophoto_NDVI.tif",
        b"II*\x00GEOVISION-NDVI",
        "image/tiff",
    ),
    ProviderArtifact(
        "odm_orthophoto/odm_orthophoto_NDRE.tif",
        b"II*\x00GEOVISION-NDRE",
        "image/tiff",
    ),
    ProviderArtifact(
        "odm_orthophoto/odm_orthophoto_GNDVI.tif",
        b"II*\x00GEOVISION-GNDVI",
        "image/tiff",
    ),
)


class DeterministicProcessingProvider:
    provider_name = "fake"

    def submit(
        self,
        request: ProcessingRequest,
        *,
        idempotency_key: str,
    ) -> IntegrationResult[ProcessingSubmission]:
        del request
        reference = str(uuid.uuid5(uuid.NAMESPACE_URL, f"geovision:{idempotency_key}"))
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="submit",
            value=ProcessingSubmission(
                external_reference=reference,
                state="SUBMITTED",
                processor_name="GeoVision deterministic processor",
                processor_version="1",
                estimated_cost_amount=0,
            ),
        )

    def status(self, external_reference: str) -> IntegrationResult[ProcessingStatus]:
        del external_reference
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="status",
            value=ProcessingStatus(
                state="COMPLETED",
                progress_percent=100.0,
                stage="outputs_ready",
                actual_cost_amount=0,
            ),
        )

    def cancel(self, external_reference: str) -> IntegrationResult[bool]:
        del external_reference
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="cancel",
            value=True,
        )

    def retrieve_outputs(
        self, external_reference: str
    ) -> IntegrationResult[tuple[ProviderArtifact, ...]]:
        del external_reference
        return IntegrationResult.simulated(
            provider=self.provider_name,
            operation="retrieve_outputs",
            value=_FAKE_ARTIFACTS,
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


__all__ = ["DeterministicProcessingProvider"]

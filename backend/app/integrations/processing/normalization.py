"""Provider-output classification shared by processing adapters."""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from app.core.integration import IntegrationFailure, IntegrationResult
from app.modules.processing.ports import (
    NormalizedProcessingOutput,
    ProviderArtifact,
)


def classify_output_path(path: str) -> str | None:
    normalized = path.replace("\\", "/").lower()
    filename = PurePosixPath(normalized).name
    if "gndvi" in normalized and filename.endswith((".tif", ".tiff")):
        return "GNDVI"
    if "ndvi" in normalized and filename.endswith((".tif", ".tiff")):
        return "NDVI"
    if "ndre" in normalized and filename.endswith((".tif", ".tiff")):
        return "NDRE"
    if "orthophoto" in normalized and filename.endswith((".tif", ".tiff")):
        return "ORTHOMOSAIC"
    if (filename.startswith("dsm") or "/dsm" in normalized) and filename.endswith(
        (".tif", ".tiff")
    ):
        return "DSM"
    if (filename.startswith("dtm") or "/dtm" in normalized) and filename.endswith(
        (".tif", ".tiff")
    ):
        return "DTM"
    if filename.endswith((".las", ".laz", ".ply", ".e57")) and any(
        marker in normalized for marker in ("georefer", "point", "cloud", "odm_")
    ):
        return "POINT_CLOUD"
    if filename.endswith((".obj", ".glb", ".gltf", ".fbx")) and any(
        marker in normalized for marker in ("mesh", "textur", "model", "odm_")
    ):
        return "MESH_3D"
    return None


def normalize_provider_artifacts(
    provider_name: str,
    outputs: tuple[ProviderArtifact, ...],
    *,
    requested_outputs: tuple[str, ...],
) -> IntegrationResult[tuple[NormalizedProcessingOutput, ...]]:
    requested = set(requested_outputs)
    selected: dict[str, ProviderArtifact] = {}
    for artifact in outputs:
        output_type = classify_output_path(artifact.relative_path)
        if output_type in requested and output_type not in selected:
            selected[output_type] = artifact
    normalized = tuple(
        NormalizedProcessingOutput(
            dataset_type=output_type,
            filename=PurePosixPath(artifact.relative_path).name,
            content=artifact.content,
            content_type=(
                artifact.content_type
                or mimetypes.guess_type(artifact.relative_path)[0]
                or "application/octet-stream"
            ),
            metadata={"provider_path": artifact.relative_path},
        )
        for output_type, artifact in sorted(selected.items())
    )
    if not normalized:
        return IntegrationResult.failed(
            provider=provider_name,
            operation="normalize_outputs",
            failure=IntegrationFailure(
                code="outputs_unrecognized",
                message="Processor archive did not contain a recognized requested output",
            ),
        )
    return IntegrationResult.succeeded(
        provider=provider_name,
        operation="normalize_outputs",
        value=normalized,
    )


__all__ = ["classify_output_path", "normalize_provider_artifacts"]

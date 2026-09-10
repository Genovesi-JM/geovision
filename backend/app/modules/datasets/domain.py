"""Dataset vocabulary, lifecycle, metadata, and upload validation rules."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import re
from typing import Any


class DatasetStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    ARCHIVED = "archived"


class ProcessingLevel(str, Enum):
    RAW = "RAW"
    PROCESSED = "PROCESSED"
    DERIVED = "DERIVED"
    REPORT = "REPORT"


class QualityStatus(str, Enum):
    UNREVIEWED = "UNREVIEWED"
    PASSED = "PASSED"
    WARNING = "WARNING"
    FAILED = "FAILED"


class ObjectArea(str, Enum):
    RAW = "raw"
    PROCESSED = "processed"
    DERIVED = "derived"
    REPORTS = "reports"


KNOWN_DATASET_TYPES = frozenset(
    {
        "RGB_IMAGES",
        "MULTISPECTRAL_IMAGES",
        "THERMAL_IMAGES",
        "ORTHOMOSAIC",
        "DSM",
        "DTM",
        "POINT_CLOUD",
        "MESH_3D",
        "NDVI",
        "NDRE",
        "GNDVI",
        "SATELLITE_IMAGE",
        "WEATHER_DATA",
        "TELEMETRY",
        "AIS_DATA",
        "BIM_MODEL",
    }
)

_TYPE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")
_SENSITIVE_KEY = re.compile(
    r"(^|_)(password|passwd|secret|token|api_key|authorization|credential|private_key)($|_)",
    re.IGNORECASE,
)
_ALLOWED_EXTENSIONS = frozenset(
    {
        ".csv",
        ".doc",
        ".docx",
        ".dsm",
        ".dtm",
        ".dwg",
        ".dxf",
        ".e57",
        ".fbx",
        ".geojson",
        ".geotiff",
        ".glb",
        ".gltf",
        ".gml",
        ".gpkg",
        ".grb",
        ".grib",
        ".grib2",
        ".h5",
        ".hdf5",
        ".ifc",
        ".j2k",
        ".jpeg",
        ".jpg",
        ".jp2",
        ".json",
        ".kml",
        ".kmz",
        ".las",
        ".laz",
        ".nc",
        ".nc4",
        ".obj",
        ".parquet",
        ".pdf",
        ".ply",
        ".png",
        ".rvt",
        ".shp",
        ".tif",
        ".tiff",
        ".txt",
        ".xls",
        ".xlsx",
        ".xml",
        ".xyz",
        ".zip",
    }
)
_DANGEROUS_MIME_TYPES = frozenset(
    {
        "application/x-dosexec",
        "application/x-executable",
        "application/x-msdownload",
        "application/x-sh",
        "text/html",
        "text/javascript",
    }
)

_TRANSITIONS = {
    DatasetStatus.UPLOADING: frozenset(
        {DatasetStatus.PROCESSING, DatasetStatus.ERROR, DatasetStatus.ARCHIVED}
    ),
    DatasetStatus.PROCESSING: frozenset(
        {DatasetStatus.READY, DatasetStatus.ERROR, DatasetStatus.ARCHIVED}
    ),
    DatasetStatus.READY: frozenset(
        {DatasetStatus.PROCESSING, DatasetStatus.ARCHIVED}
    ),
    DatasetStatus.ERROR: frozenset(
        {
            DatasetStatus.UPLOADING,
            DatasetStatus.PROCESSING,
            DatasetStatus.ARCHIVED,
        }
    ),
    DatasetStatus.ARCHIVED: frozenset(),
}


class DatasetError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_dataset_type(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    normalized = normalized.strip("_").upper()
    if not _TYPE_PATTERN.fullmatch(normalized):
        raise ValueError("dataset_type must be a stable uppercase identifier")
    return normalized


def normalize_provider_code(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not normalized or len(normalized) > 80:
        raise ValueError("provider must be a stable identifier")
    return normalized


def reject_sensitive_metadata(value: Any, path: str = "metadata") -> Any:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(key)).strip("_")
            if _SENSITIVE_KEY.search(normalized):
                raise ValueError(f"{path} cannot contain credentials or secrets")
            reject_sensitive_metadata(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_sensitive_metadata(nested, f"{path}[{index}]")
    return value


def require_transition(current: str, target: str) -> None:
    try:
        current_status = DatasetStatus(current)
        target_status = DatasetStatus(target)
    except ValueError as exc:
        raise DatasetError("invalid_status", "Dataset status is not supported") from exc
    if current_status == target_status:
        return
    if target_status not in _TRANSITIONS[current_status]:
        raise DatasetError(
            "invalid_transition",
            f"Dataset cannot move from {current_status.value} to {target_status.value}",
        )


def object_area_for(level: ProcessingLevel | str) -> ObjectArea:
    value = ProcessingLevel(level)
    return {
        ProcessingLevel.RAW: ObjectArea.RAW,
        ProcessingLevel.PROCESSED: ObjectArea.PROCESSED,
        ProcessingLevel.DERIVED: ObjectArea.DERIVED,
        ProcessingLevel.REPORT: ObjectArea.REPORTS,
    }[value]


def validate_upload(
    *,
    filename: str,
    content_type: str | None,
    size_bytes: int,
    max_size_bytes: int,
) -> str:
    if not filename or filename != Path(filename).name or any(
        character in filename for character in ("\x00", "\r", "\n")
    ):
        raise DatasetError("invalid_filename", "Upload filename is invalid")
    if len(filename.encode("utf-8")) > 240:
        raise DatasetError("invalid_filename", "Upload filename is too long")
    if Path(filename).suffix.lower() not in _ALLOWED_EXTENSIONS:
        raise DatasetError("file_type_not_allowed", "Dataset file type is not allowed")
    normalized_mime = (content_type or "application/octet-stream").split(";", 1)[0].lower()
    if normalized_mime in _DANGEROUS_MIME_TYPES:
        raise DatasetError("file_type_not_allowed", "Dataset content type is not allowed")
    if size_bytes <= 0:
        raise DatasetError("invalid_file_size", "Dataset files cannot be empty")
    if size_bytes > max_size_bytes:
        raise DatasetError(
            "file_too_large",
            f"File exceeds the {max_size_bytes}-byte upload limit",
        )
    return filename


__all__ = [
    "DatasetError",
    "DatasetStatus",
    "KNOWN_DATASET_TYPES",
    "ObjectArea",
    "ProcessingLevel",
    "QualityStatus",
    "normalize_dataset_type",
    "normalize_provider_code",
    "object_area_for",
    "reject_sensitive_metadata",
    "require_transition",
    "validate_upload",
]

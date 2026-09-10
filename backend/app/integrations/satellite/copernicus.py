"""Copernicus Data Space STAC 1.1 catalogue adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any, Callable, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit

import httpx

from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
    sanitize_integration_message,
)
from app.modules.datasets.ports import (
    SatelliteAssetDescriptor,
    SatelliteDownloadedAsset,
    SatelliteSceneDescriptor,
    SatelliteSearchRequest,
)


_COLLECTION = re.compile(r"^[a-z0-9][a-z0-9._-]{1,119}$")
_MEDIA_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tif",
    "image/jp2": ".jp2",
    "application/geo+json": ".geojson",
    "application/json": ".json",
}


def _utc_naive(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _rfc3339(value: datetime) -> str:
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat(timespec="seconds").replace("+00:00", "Z")


def _float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _safe_https_url(value: Any) -> str | None:
    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


class CopernicusStacProvider:
    provider_name = "copernicus"

    def __init__(
        self,
        *,
        base_url: str,
        access_token: str | None = None,
        allowed_download_hosts: tuple[str, ...] = (
            "download.dataspace.copernicus.eu",
            "datahub.creodias.eu",
        ),
        connect_timeout_seconds: float = 5.0,
        read_timeout_seconds: float = 30.0,
        retry_attempts: int = 3,
        retry_initial_seconds: float = 0.5,
        retry_max_seconds: float = 8.0,
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.allowed_download_hosts = tuple(host.lower().strip(".") for host in allowed_download_hosts)
        self.retry_attempts = retry_attempts
        self.retry_initial_seconds = retry_initial_seconds
        self.retry_max_seconds = retry_max_seconds
        self.sleeper = sleeper
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout_seconds,
                read=read_timeout_seconds,
                write=read_timeout_seconds,
                pool=connect_timeout_seconds,
            ),
            follow_redirects=False,
            headers={"Accept": "application/geo+json, application/json"},
        )

    @staticmethod
    def _request(value: SatelliteSearchRequest | Mapping[str, Any]) -> SatelliteSearchRequest:
        if isinstance(value, SatelliteSearchRequest):
            return value
        starts = value.get("starts_at") or value.get("start")
        ends = value.get("ends_at") or value.get("end")
        starts_at = starts if isinstance(starts, datetime) else _utc_naive(starts)
        ends_at = ends if isinstance(ends, datetime) else _utc_naive(ends)
        if starts_at is None or ends_at is None:
            raise ValueError("satellite date range is required")
        return SatelliteSearchRequest(
            geometry=dict(value.get("geometry") or {}),
            starts_at=starts_at,
            ends_at=ends_at,
            collection=str(value.get("collection") or "sentinel-2-l2a"),
            max_cloud_cover_percent=float(value.get("max_cloud_cover_percent", 60.0)),
            limit=int(value.get("limit", 10)),
        )

    def _post_search(self, payload: Mapping[str, Any]) -> tuple[httpx.Response | None, int, Exception | None]:
        last_response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.retry_attempts + 1):
            try:
                last_response = self.client.post(f"{self.base_url}/search", json=dict(payload))
                if last_response.status_code < 500 and last_response.status_code != 429:
                    return last_response, attempt, None
            except httpx.HTTPError as exc:
                last_error = exc
            if attempt < self.retry_attempts:
                delay = min(
                    self.retry_initial_seconds * (2 ** (attempt - 1)),
                    self.retry_max_seconds,
                )
                if last_response is not None and last_response.status_code == 429:
                    try:
                        delay = min(float(last_response.headers.get("Retry-After", delay)), self.retry_max_seconds)
                    except ValueError:
                        pass
                self.sleeper(max(0.0, delay))
        return last_response, self.retry_attempts, last_error

    @staticmethod
    def _asset(key: str, raw: Mapping[str, Any]) -> SatelliteAssetDescriptor | None:
        href = str(raw.get("href") or "").strip()
        auth_refs = raw.get("auth:refs") or []
        alternate = raw.get("alternate")
        if urlsplit(href).scheme.lower() != "https" and isinstance(alternate, Mapping):
            https_value = alternate.get("https")
            if isinstance(https_value, Mapping):
                href = str(https_value.get("href") or "").strip()
                auth_refs = https_value.get("auth:refs") or auth_refs
        safe_href = _safe_https_url(href)
        if safe_href is None:
            return None
        # Catalogue links are persisted as provenance. Drop queries/fragments so
        # a provider cannot accidentally persist a signed URL or bearer value.
        href = safe_href
        raw_bands = raw.get("bands") or raw.get("eo:bands") or []
        bands: list[str] = []
        if isinstance(raw_bands, list):
            for band in raw_bands:
                if not isinstance(band, Mapping):
                    continue
                name = band.get("name") or band.get("eo:common_name") or band.get("common_name")
                if name:
                    bands.append(str(name)[:80])
        roles = tuple(
            str(role)[:80]
            for role in (raw.get("roles") or [])
            if isinstance(role, str) and role.strip()
        )
        size = raw.get("file:size")
        try:
            size_bytes = int(size) if size is not None else None
        except (TypeError, ValueError):
            size_bytes = None
        return SatelliteAssetDescriptor(
            key=key[:120],
            href=href,
            media_type=str(raw.get("type"))[:150] if raw.get("type") else None,
            title=str(raw.get("title"))[:240] if raw.get("title") else None,
            roles=roles,
            bands=tuple(dict.fromkeys(bands)),
            size_bytes=size_bytes if size_bytes is None or size_bytes >= 0 else None,
            requires_authentication=bool(auth_refs),
        )

    @classmethod
    def _scene(cls, raw: Mapping[str, Any]) -> SatelliteSceneDescriptor | None:
        reference = str(raw.get("id") or "").strip()
        collection = str(raw.get("collection") or "").strip().lower()
        properties = raw.get("properties")
        if not reference or not _COLLECTION.fullmatch(collection) or not isinstance(properties, Mapping):
            return None
        acquired_at = _utc_naive(properties.get("datetime") or properties.get("start_datetime"))
        if acquired_at is None:
            return None
        assets: list[SatelliteAssetDescriptor] = []
        raw_assets = raw.get("assets")
        if isinstance(raw_assets, Mapping):
            for key, value in raw_assets.items():
                if isinstance(value, Mapping):
                    normalized = cls._asset(str(key), value)
                    if normalized is not None:
                        assets.append(normalized)
        bands = tuple(dict.fromkeys(band for asset in assets for band in asset.bands))
        bbox: tuple[float, float, float, float] | tuple[()] = ()
        raw_bbox = raw.get("bbox")
        if isinstance(raw_bbox, list) and len(raw_bbox) >= 4:
            values = tuple(_float(item) for item in raw_bbox[:4])
            if all(item is not None for item in values):
                bbox = values  # type: ignore[assignment]
        geometry = raw.get("geometry")
        geometry_value = dict(geometry) if isinstance(geometry, Mapping) else None
        links = raw.get("links") or []
        source_link = next(
            (
                safe
                for link in links
                if isinstance(link, Mapping)
                and link.get("rel") in {"self", "canonical"}
                for safe in [_safe_https_url(link.get("href"))]
                if safe is not None
            ),
            None,
        )
        cloud_cover = _float(properties.get("eo:cloud_cover"))
        resolution = _float(properties.get("gsd"))
        if resolution is None:
            role_resolutions: list[float] = []
            for asset in assets:
                for role in asset.roles:
                    match = re.fullmatch(r"gsd:(\d+(?:\.\d+)?)m", role.lower())
                    if match:
                        role_resolutions.append(float(match.group(1)))
            resolution = min(role_resolutions) if role_resolutions else None
        return SatelliteSceneDescriptor(
            provider_reference=reference[:240],
            collection=collection,
            acquired_at=acquired_at,
            published_at=_utc_naive(properties.get("published") or properties.get("created")),
            cloud_cover_percent=(
                min(100.0, max(0.0, cloud_cover)) if cloud_cover is not None else None
            ),
            resolution_meters=resolution if resolution and resolution > 0 else None,
            crs=str(properties.get("proj:code"))[:100] if properties.get("proj:code") else None,
            bands=bands,
            bbox=bbox,
            geometry=geometry_value,
            assets=tuple(assets),
            source_link=source_link,
            provenance={
                "provider": "Copernicus Data Space Ecosystem",
                "catalog_standard": "STAC 1.1.0",
                "collection": collection,
                "platform": properties.get("platform"),
                "constellation": properties.get("constellation"),
                "processing_level": properties.get("processing:level"),
                "license": properties.get("license"),
            },
        )

    def search(
        self,
        request: SatelliteSearchRequest | Mapping[str, Any],
    ) -> IntegrationResult[tuple[SatelliteSceneDescriptor, ...]]:
        try:
            normalized = self._request(request)
            if not _COLLECTION.fullmatch(normalized.collection):
                raise ValueError("satellite collection is invalid")
            if normalized.starts_at > normalized.ends_at:
                raise ValueError("satellite start must not be after end")
            if not isinstance(normalized.geometry, Mapping) or not normalized.geometry.get("type"):
                raise ValueError("satellite geometry is required")
            if not 1 <= normalized.limit <= 100:
                raise ValueError("satellite result limit must be between 1 and 100")
            payload = {
                "collections": [normalized.collection],
                "intersects": dict(normalized.geometry),
                "datetime": f"{_rfc3339(normalized.starts_at)}/{_rfc3339(normalized.ends_at)}",
                "limit": normalized.limit,
                "query": {"eo:cloud_cover": {"lte": normalized.max_cloud_cover_percent}},
                "sortby": [{"field": "properties.datetime", "direction": "desc"}],
            }
            response, attempts, error = self._post_search(payload)
            if response is None:
                message = sanitize_integration_message(error or "Copernicus request failed")
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation="search",
                    failure=IntegrationFailure("provider_unreachable", message, retryable=True),
                    attempts=attempts,
                )
            if response.status_code != 200:
                retryable = response.status_code == 429 or response.status_code >= 500
                return IntegrationResult.failed(
                    provider=self.provider_name,
                    operation="search",
                    failure=IntegrationFailure(
                        f"provider_http_{response.status_code}",
                        "Copernicus catalogue rejected the scene search",
                        retryable=retryable,
                    ),
                    attempts=attempts,
                )
            body = response.json()
            features = body.get("features") if isinstance(body, Mapping) else None
            if not isinstance(features, list):
                raise ValueError("Copernicus returned an invalid STAC FeatureCollection")
            scenes = tuple(
                scene
                for feature in features[: normalized.limit]
                if isinstance(feature, Mapping)
                for scene in [self._scene(feature)]
                if scene is not None
            )
            return IntegrationResult.succeeded(
                provider=self.provider_name,
                operation="search",
                value=scenes,
                attempts=attempts,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="search",
                failure=IntegrationFailure(
                    "invalid_provider_response",
                    sanitize_integration_message(exc, secret_values=(self.access_token or "",)),
                    retryable=False,
                ),
            )

    def _host_allowed(self, host: str | None) -> bool:
        candidate = (host or "").lower().rstrip(".")
        return any(candidate == allowed or candidate.endswith(f".{allowed}") for allowed in self.allowed_download_hosts)

    def download_asset(
        self,
        scene: SatelliteSceneDescriptor,
        asset_key: str,
        *,
        max_bytes: int,
    ) -> IntegrationResult[SatelliteDownloadedAsset]:
        asset = next((item for item in scene.assets if item.key == asset_key), None)
        if asset is None:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="download_asset",
                failure=IntegrationFailure("asset_not_found", "Satellite asset was not advertised"),
            )
        parsed = urlsplit(asset.href)
        if parsed.scheme.lower() != "https" or not self._host_allowed(parsed.hostname):
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="download_asset",
                failure=IntegrationFailure("asset_url_rejected", "Satellite asset host is not allowlisted"),
            )
        if asset.requires_authentication and not self.access_token:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="download_asset",
                status=IntegrationStatus.NOT_CONFIGURED,
                failure=IntegrationFailure(
                    "access_token_required",
                    "This Copernicus asset requires a configured access token",
                ),
            )
        headers = {"Accept": asset.media_type or "application/octet-stream"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        try:
            with self.client.stream("GET", asset.href, headers=headers) as response:
                if response.status_code != 200:
                    return IntegrationResult.failed(
                        provider=self.provider_name,
                        operation="download_asset",
                        failure=IntegrationFailure(
                            f"provider_http_{response.status_code}",
                            "Copernicus asset download failed",
                            retryable=response.status_code == 429 or response.status_code >= 500,
                        ),
                    )
                claimed = response.headers.get("Content-Length")
                if claimed and int(claimed) > max_bytes:
                    return IntegrationResult.failed(
                        provider=self.provider_name,
                        operation="download_asset",
                        failure=IntegrationFailure("asset_too_large", "Satellite asset exceeds the download limit"),
                    )
                chunks: list[bytes] = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        return IntegrationResult.failed(
                            provider=self.provider_name,
                            operation="download_asset",
                            failure=IntegrationFailure("asset_too_large", "Satellite asset exceeds the download limit"),
                        )
                    chunks.append(chunk)
                if size == 0:
                    raise ValueError("Copernicus returned an empty asset")
                media_type = (response.headers.get("Content-Type") or asset.media_type or "application/octet-stream").split(";", 1)[0]
                filename = Path(unquote(parsed.path)).name
                if not filename or len(filename.encode("utf-8")) > 220:
                    filename = f"{scene.provider_reference}_{asset.key}"
                if not Path(filename).suffix:
                    filename += _MEDIA_EXTENSIONS.get(media_type, ".bin")
                return IntegrationResult.succeeded(
                    provider=self.provider_name,
                    operation="download_asset",
                    value=SatelliteDownloadedAsset(
                        scene_reference=scene.provider_reference,
                        asset_key=asset.key,
                        filename=filename,
                        media_type=media_type,
                        content=b"".join(chunks),
                    ),
                )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return IntegrationResult.failed(
                provider=self.provider_name,
                operation="download_asset",
                failure=IntegrationFailure(
                    "asset_download_failed",
                    sanitize_integration_message(exc, secret_values=(self.access_token or "",)),
                    retryable=isinstance(exc, httpx.HTTPError),
                ),
            )

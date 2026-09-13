"""Safe provider inventory and explicit, credential-free Spain diagnostics.

Configuration is not connectivity. This projection never resolves vault
references, returns settings/credentials, or calls a provider while listing.
Only explicit fixed checks perform network I/O. AEMET alone uses a server secret.
"""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import threading
import time
from typing import Any
from uuid import UUID

_PUBLIC_CHECK_LOCK = threading.Lock()
_LAST_CHECK: dict[str, float] = {}
MIN_CHECK_INTERVAL_SECONDS = 30


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    family: str
    selection: str | None
    aliases: tuple[str, ...]
    configuration: str | None
    requirement: str
    implemented: bool = True


PROVIDERS = (
    ProviderSpec("copernicus", "Copernicus Data Space", "Satélite", "satellite", ("copernicus", "cdse", "sentinel"), None, "Catálogo público; descarga y cálculo de índices requieren un flujo adicional."),
    ProviderSpec("miteco", "MITECO", "Medio ambiente", "gis", ("miteco",), None, "Una colección de biodiversidad revisada; no incluye todo el catastro ni todos los datos ambientales."),
    ProviderSpec("aemet", "AEMET OpenData", "Meteorología", "weather", ("aemet", "aemet_opendata"), "aemet", "Clave AEMET y comprobación de observaciones en España."),
    ProviderSpec("google_maps", "Google Places, Geocoding y Routes", "Ubicación", "location", ("google", "google_maps"), "google_maps_location", "Clave de servidor restringida, APIs habilitadas y cuotas aprobadas."),
    ProviderSpec("nodeodm", "NodeODM", "Fotogrametría", "processing", ("nodeodm", "opendronemap"), "nodeodm", "Servicio HTTPS, token, worker y validación de resultados."),
    ProviderSpec("smtp", "Correo SMTP", "Notificaciones", "notifications", ("smtp", "auto"), "smtp", "Buzón autorizado, STARTTLS, credenciales y prueba de entrega consentida."),
    ProviderSpec("azure_notification_hubs", "Azure Notification Hubs / APNs / FCM", "Notificaciones", None, (), "azure_notification_hubs", "Hub, configuración de Apple/Google, dispositivos y consentimiento."),
    ProviderSpec("entra_external_id", "Microsoft Entra External ID", "Identidad", "identity", ("entra_external_id", "transition"), "entra_external_id", "Identidad de usuarios de la app; distinta del acceso Microsoft al piloto."),
    ProviderSpec("google_oauth", "Inicio de sesión Google", "Identidad", None, (), "google_oauth", "Aplicación OAuth, retornos exactos y validación del flujo de acceso."),
    ProviderSpec("microsoft_oauth", "Inicio de sesión Microsoft", "Identidad", None, (), "microsoft_oauth", "Aplicación OAuth de GeoVision; distinta del acceso al portal Azure."),
    ProviderSpec("azure_blob", "Azure Blob Storage", "Almacenamiento", "object_storage", ("azure_blob", "azure"), "azure_blob", "Identidad limitada, contenedor privado y prueba de lectura/escritura."),
    ProviderSpec("s3", "Almacenamiento S3 compatible", "Almacenamiento", "object_storage", ("s3",), "s3", "Alternativa a Azure Blob, no una segunda copia automática."),
    ProviderSpec("azure_service_bus", "Azure Service Bus", "Eventos", "queue", ("azure_service_bus",), "azure_service_bus", "Alternativa a la cola PostgreSQL actual; recursos y permisos propios."),
    ProviderSpec("azure_event_grid", "Azure Event Grid", "Eventos", None, (), "azure_event_grid", "Origen autorizado, firma, protección de duplicados y suscripción."),
    ProviderSpec("azure_iot_hub", "Azure IoT Hub", "IoT", "iot_cloud", ("azure_iot_hub",), "azure_iot_hub", "Dispositivos reales, identidad por dispositivo y pruebas de telemetría."),
    ProviderSpec("mqtt", "MQTT firmado", "IoT", None, (), "mqtt", "Broker, dispositivos, firma y monitor de desconexión."),
    ProviderSpec("azure_app_configuration", "Azure App Configuration", "Plataforma", None, (), "azure_app_configuration", "Configuración y permisos de lectura; no sustituye los derechos del cliente."),
    ProviderSpec("erpnext", "ERPNext", "ERP", "erp", ("erpnext",), "erpnext", "Cuenta de servicio, correspondencia contable e idempotencia verificadas."),
    ProviderSpec("odoo", "Odoo 19", "ERP", "erp", ("odoo",), "odoo", "Puente JSON-2 aprobado, cuenta limitada, worker y conciliación."),
    ProviderSpec("stripe", "Stripe", "Pagos", None, (), "stripe", "Cuenta comercial, webhook firmado y checkout/reembolso de prueba."),
    ProviderSpec("paypal", "PayPal", "Pagos", None, (), "paypal", "Cuenta comercial y pruebas completas de captura y conciliación."),
    ProviderSpec("multicaixa", "Multicaixa", "Pagos", None, (), "multicaixa", "Contrato del adquirente, callbacks y conciliación; cobertura Angola."),
    ProviderSpec("azure_maps_weather", "Azure Maps Weather", "Meteorología", "weather", ("azure_maps", "azure_maps_weather"), None, "Adaptador pendiente; una clave no activa este servicio.", False),
    ProviderSpec("arcgis", "ArcGIS", "GIS del cliente", "gis", ("arcgis",), "arcgis", "Adaptador y acceso al entorno del cliente pendientes.", False),
    ProviderSpec("autodesk_aps", "Autodesk APS", "Construcción", "construction", ("autodesk_aps", "autodesk"), "autodesk_aps", "Adaptador, sandbox y correspondencia con proyectos del cliente.", False),
    ProviderSpec("procore", "Procore", "Construcción", "construction", ("procore",), "procore", "Adaptador, permisos y sandbox del cliente.", False),
    ProviderSpec("bentley_itwin", "Bentley iTwin", "Construcción", "construction", ("bentley_itwin", "bentley"), "bentley_itwin", "Adaptador, permisos y sandbox del cliente.", False),
    ProviderSpec("trimble", "Trimble", "Construcción", "construction", ("trimble",), "trimble", "Adaptador, permisos y sandbox del cliente.", False),
    ProviderSpec("seequent", "Seequent", "Minería y activos", "asset_management", ("seequent",), "seequent", "Adaptador y contrato del cliente.", False),
    ProviderSpec("mine_enterprise", "Mine Enterprise", "Minería y activos", "asset_management", ("mine_enterprise",), None, "Proveedor específico y adaptador pendientes.", False),
    ProviderSpec("sap_eam", "SAP EAM", "Activos industriales", "asset_management", ("sap_eam",), None, "Adaptador y acceso al sistema del cliente.", False),
    ProviderSpec("ibm_maximo", "IBM Maximo", "Activos industriales", "asset_management", ("ibm_maximo",), None, "Adaptador y acceso al sistema del cliente.", False),
    ProviderSpec("dynamics_365", "Dynamics 365 Asset Management", "Activos industriales", "asset_management", ("dynamics_365", "dynamics_365_asset_management"), None, "Adaptador y acceso al sistema del cliente.", False),
    ProviderSpec("customer_cmms", "CMMS del cliente", "Activos industriales", "asset_management", ("customer_cmms",), None, "Identificar el sistema y acordar su contrato de API.", False),
    ProviderSpec("marinetraffic", "MarineTraffic", "Puertos y logística", "maritime", ("marinetraffic", "marine_traffic"), None, "Adaptador, licencia y procedencia de datos pendientes.", False),
    ProviderSpec("kpler", "Kpler", "Puertos y logística", "maritime", ("kpler",), None, "Adaptador, licencia y procedencia de datos pendientes.", False),
    ProviderSpec("puertos_del_estado", "Puertos del Estado", "Puertos y logística", "maritime", ("puertos_del_estado",), None, "Adaptador de contexto y condiciones de reutilización pendientes.", False),
    ProviderSpec("pix4d", "PIX4D", "Fotogrametría", "processing", ("pix4d",), None, "Adaptador y servicio de procesamiento pendientes.", False),
    ProviderSpec("autodesk_processing", "Autodesk Reality Capture", "Fotogrametría", "processing", ("autodesk", "autodesk_reality_capture"), None, "Adaptador y servicio de procesamiento pendientes.", False),
    ProviderSpec("bentley_processing", "Bentley Reality Modeling", "Fotogrametría", "processing", ("bentley", "bentley_reality_modeling"), None, "Adaptador y servicio de procesamiento pendientes.", False),
    ProviderSpec("external_narrative", "Narrativa externa OpenAI / Azure OpenAI", "IA", "report_narrative", ("openai", "azure_openai"), "openai", "Adaptador aprobado, privacidad y validación; nunca autoridad de medición.", False),
)


def provider_inventory(config: Any) -> dict:
    safe = config.safe_summary()
    configured = safe.get("configured", {})
    selections = safe.get("providers", {})
    items = []
    for spec in PROVIDERS:
        available = bool(configured.get(spec.configuration)) if spec.configuration else spec.key in {"miteco", "copernicus"}
        # Providers such as payments/OAuth have no global selection: never
        # infer activation from a credential. Account/entitlement gates apply.
        selected = str(selections.get(spec.selection, "")) in spec.aliases if spec.selection else None
        state = "not_implemented" if not spec.implemented else "requires_configuration" if not available else "not_selected" if selected is False else "configured_unverified"
        items.append({
            "key": spec.key, "label": spec.label, "family": spec.family,
            "implementation": "implemented" if spec.implemented else "scaffold",
            "selected": selected, "configuration_present": available,
            "state": state, "verification": "not_checked",
            "next_step": spec.requirement,
            "public_check_available": spec.key in {"miteco", "copernicus"} and selected is True,
            "credentialed_check_available": spec.key == "aemet" and available and selected is True,
        })
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "items": items,
            "notice": "Configuración no significa conexión validada. Los proveedores alternativos no deben activarse todos a la vez.",
            "separate_checks": ["Mapas visuales OpenStreetMap/Mapbox: comprobar en web y móvil.",
                "Azure Monitor/Application Insights: comprobar exportación, alertas y retención.",
                "Transferencia bancaria manual: no es una API bancaria conectada."]}


def public_provider_check(provider: str, config: Any) -> dict:
    """Fixed public Spain queries only. No credentials, data writes or retries.

The caller must authorize platform administrators and reject request payloads.
Results expose only counts/source metadata, never raw vendor errors or bodies.
"""
    from app.core.integration import RetryPolicy, TimeoutPolicy
    from app.integrations.gis.miteco import MitecoOgcFeaturesProvider
    from app.integrations.gis.miteco_catalog import MITECO_OGC_FEATURES_BASE_URL
    from app.integrations.satellite.copernicus import CopernicusStacProvider
    import httpx

    spec = next((item for item in PROVIDERS if item.key == provider), None)
    if provider not in {"miteco", "copernicus"} or spec is None:
        raise ValueError("unsupported_public_check")
    selected = config.gis_provider if provider == "miteco" else config.satellite_provider
    if selected not in spec.aliases:
        raise ValueError("provider_not_selected")

    if not _PUBLIC_CHECK_LOCK.acquire(blocking=False):
        raise ValueError("public_check_busy")
    start = time.monotonic()
    if start - _LAST_CHECK.get(provider, float("-inf")) < MIN_CHECK_INTERVAL_SECONDS:
        _PUBLIC_CHECK_LOCK.release()
        raise ValueError("public_check_cooldown")
    _LAST_CHECK[provider] = start
    now = datetime.now(timezone.utc)
    output = {"provider": provider, "checked_at": now.isoformat(),
              "status": "failed", "records": None, "context_only": True,
              "scope": "Consulta pública limitada en España; no valida descargas, sensores ni KPIs.",
              "source": MITECO_OGC_FEATURES_BASE_URL if provider == "miteco" else "https://stac.dataspace.copernicus.eu/v1",
              "error_code": None}

    class LimitedStream(httpx.SyncByteStream):
        def __init__(self, stream):
            self.source = stream
        def __iter__(self):
            total = 0
            for chunk in self.source:
                if time.monotonic() - start > 20 or total + len(chunk) > 2 * 1024 * 1024:
                    raise ValueError("public_response_limit")
                total += len(chunk)
                yield chunk
        def close(self):
            self.source.close()

    class BoundedClient(httpx.Client):
        @contextmanager
        def stream(self, *args, **kwargs):
            with super().stream(*args, **kwargs) as response:
                if response.headers.get("Content-Encoding", "identity").lower() not in ("", "identity"):
                    raise ValueError("public_response_encoding")
                size = response.headers.get("Content-Length")
                if size is not None and (not size.isdigit() or int(size) > 2 * 1024 * 1024):
                    raise ValueError("public_response_limit")
                response.stream = LimitedStream(response.stream)
                yield response
        def post(self, url, *, json):
            with self.stream("POST", url, json=json) as response:
                body = bytearray()
                for chunk in response.iter_bytes():
                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                        raise ValueError("public_response_limit")
                    body.extend(chunk)
                return httpx.Response(response.status_code, headers=response.headers,
                                      content=bytes(body), request=response.request)

    try:
        # Do not inherit proxy credentials or provider credentials. These fixed
        # official endpoints support public queries; authenticated APIs are not
        # part of this diagnostic and no location from a customer is sent.
        with BoundedClient(timeout=httpx.Timeout(15, connect=5), follow_redirects=False,
                           trust_env=False, headers={"Accept": "application/geo+json, application/json", "Accept-Encoding": "identity"}) as client:
            if provider == "copernicus":
                adapter = CopernicusStacProvider(base_url=output["source"], client=client, retry_attempts=1)
                result = adapter.search({"geometry": {"type": "Polygon", "coordinates": [[[-3.8, 40.3], [-3.6, 40.3], [-3.6, 40.5], [-3.8, 40.5], [-3.8, 40.3]]]},
                                         "starts_at": now - timedelta(days=14), "ends_at": now,
                                         "limit": 2, "max_cloud_cover_percent": 100})
                count = len(result.value or ())
            else:
                adapter = MitecoOgcFeaturesProvider(base_url=output["source"], client=client,
                    timeout_policy=TimeoutPolicy(connect_seconds=5, read_seconds=15, write_seconds=15, pool_seconds=5),
                    retry_policy=RetryPolicy(max_attempts=1), max_features=1, max_response_bytes=2 * 1024 * 1024)
                result = adapter.query_layers({"internal_id": UUID("00000000-0000-4000-8000-000000000001"),
                    "collection_key": "biodiversity_priority_zones", "bbox": (-3.8, 40.3, -3.6, 40.5), "limit": 1})
                count = len(result.value.features) if result.value is not None else 0
            if result.status == "succeeded":
                output.update(status="response_verified" if count else "reachable_no_data", records=count)
            else:
                # Adapter error text may contain upstream payloads. Only a
                # fixed diagnostic label crosses this administrative boundary.
                output["error_code"] = "public_provider_check_failed"
    except Exception:
        output["error_code"] = "public_provider_check_failed"
    finally:
        _PUBLIC_CHECK_LOCK.release()
    return output


def aemet_observation_check(config: Any) -> dict:
    """One fixed Madrid station check. Secret stays server-side; no DB writes."""
    from app.integrations.weather.aemet import AemetOpenDataProvider

    if config.weather_provider not in {"aemet", "aemet_opendata"} or not config.aemet_api_key:
        raise ValueError("aemet_not_configured")
    if config.aemet_base_url != "https://opendata.aemet.es/opendata":
        raise ValueError("aemet_official_origin_required")
    if not _PUBLIC_CHECK_LOCK.acquire(blocking=False):
        raise ValueError("public_check_busy")
    start = time.monotonic()
    if start - _LAST_CHECK.get("aemet", float("-inf")) < MIN_CHECK_INTERVAL_SECONDS:
        _PUBLIC_CHECK_LOCK.release()
        raise ValueError("public_check_cooldown")
    _LAST_CHECK["aemet"] = start
    now = datetime.now(timezone.utc)
    output = {"provider": "aemet", "checked_at": now.isoformat(), "status": "failed",
              "records": None, "context_only": True, "observed_at": None, "metric_count": None,
              "scope": "Observación reciente de una estación de prueba en Madrid; no es una previsión ni valida KPIs.",
              "source": "https://opendata.aemet.es", "error_code": None}
    adapter = None
    try:
        adapter = AemetOpenDataProvider(base_url=config.aemet_base_url, api_key=config.aemet_api_key,
            station_id="3195", max_response_bytes=2 * 1024 * 1024, retry_attempts=1,
            connect_timeout_seconds=5, read_timeout_seconds=15)
        result = adapter.observations({"latitude": 40.42, "longitude": -3.70,
            "starts_at": (now - timedelta(hours=48)).replace(tzinfo=None),
            "ends_at": now.replace(tzinfo=None), "max_distance_km": 100})
        if result.ok and result.value:
            snapshot = result.value[0]
            output.update(status="response_verified", records=len(result.value),
                          observed_at=snapshot.observed_at.isoformat() + "Z", metric_count=len(snapshot.metrics))
        else:
            code = result.failure.code if result.failure else ""
            output["error_code"] = {"provider_http_401": "aemet_credentials_rejected",
                "provider_http_403": "aemet_credentials_rejected", "provider_http_429": "aemet_rate_limited",
                "no_station_in_range": "aemet_no_recent_observation"}.get(code, "aemet_observation_check_failed")
    except Exception:
        output["error_code"] = "aemet_observation_check_failed"
    finally:
        try:
            if adapter is not None:
                adapter.client.close()
        except Exception:
            output.update(status="failed", records=None, observed_at=None, metric_count=None,
                          error_code="aemet_observation_check_failed")
        finally:
            _PUBLIC_CHECK_LOCK.release()
    return output

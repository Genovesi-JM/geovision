"""Canonical first-party catalogue services and legacy compatibility mapping."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models import (
    AuditLog,
    CatalogItem,
    ProcurementSupplier,
    Product,
    ShopProduct,
    User,
)
from app.product_translations import get_product_translations
from app.modules.catalog.schemas import (
    CatalogItemCreate,
    CatalogItemStatus,
    CatalogItemUpdate,
    PriceModel,
    SupplierCreate,
    SupplierUpdate,
)


class CatalogError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_SECTOR_ALIASES = {
    "AGRO": "AGRICULTURE",
    "AGRICULTURE": "AGRICULTURE",
    "LIVESTOCK": "AGRICULTURE",
    "CONSTRUCTION": "INFRASTRUCTURE",
    "INFRASTRUCTURE": "INFRASTRUCTURE",
    "WATER": "INFRASTRUCTURE",
    "ENERGY": "INFRASTRUCTURE",
    "FACILITIES": "INFRASTRUCTURE",
    "COLD_CHAIN": "INFRASTRUCTURE",
    "SOLAR": "INFRASTRUCTURE",
    "DEMINING": "INFRASTRUCTURE",
    "ENVIRONMENT": "ENVIRONMENTAL",
    "ENVIRONMENTAL": "ENVIRONMENTAL",
    "AMBIENTAL": "ENVIRONMENTAL",
    "MINING": "MINING",
    "INDUSTRY": "PORTS_INDUSTRIAL",
    "INDUSTRIAL": "PORTS_INDUSTRIAL",
    "PORT": "PORTS_INDUSTRIAL",
    "PORTS": "PORTS_INDUSTRIAL",
    "PORTS_INDUSTRIAL": "PORTS_INDUSTRIAL",
}

_LEGACY_SECTORS = {
    "AGRICULTURE": "agro",
    "INFRASTRUCTURE": "infrastructure",
    "ENVIRONMENTAL": "environment",
    "MINING": "mining",
    "PORTS_INDUSTRIAL": "industry",
}


def _identifier(value: object, default: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or default).strip())
    return normalized.strip("_").upper() or default


def _slug(value: object, default: str = "catalog-item") -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or default).strip().lower())
    return normalized.strip("-") or default


def normalize_sector(value: object) -> str:
    normalized = _identifier(value, "INFRASTRUCTURE")
    return _SECTOR_ALIASES.get(normalized, normalized)


def normalize_asset_type(value: object) -> str:
    return _identifier(value, "SITE")


def _json(value: Any) -> str:
    def default(item: Any):
        if isinstance(item, Decimal):
            return float(item)
        if isinstance(item, datetime):
            return item.isoformat()
        raise TypeError(f"Unsupported JSON value: {type(item).__name__}")

    try:
        payload = json.dumps(
            value,
            default=default,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise CatalogError("invalid_json", "Catalogue fields must contain JSON-compatible values") from exc
    if len(payload.encode("utf-8")) > 65_536:
        raise CatalogError("payload_too_large", "A catalogue JSON field cannot exceed 64 KiB")
    return payload


def _json_dict(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _catalog_type(product_type: str | None, category: str | None, name: str | None) -> str:
    combined = " ".join((product_type or "", category or "", name or "")).lower()
    if product_type in {"hardware", "physical", "physical_product"}:
        return "PHYSICAL_PRODUCT"
    if product_type in {"subscription", "monitoring_plan"} or "monitor" in combined:
        return "MONITORING_PLAN"
    if "install" in combined:
        return "INSTALLATION"
    if "inspec" in combined:
        return "INSPECTION"
    if "analy" in combined or "anális" in combined or "analise" in combined:
        return "ANALYSIS"
    return "SERVICE"


def _fulfilment_type(item_type: str) -> str:
    return {
        "PHYSICAL_PRODUCT": "PHYSICAL_SHIPMENT",
        "MONITORING_PLAN": "MONITORING_ACTIVATION",
        "INSTALLATION": "FIELD_INSTALLATION",
        "INSPECTION": "FIELD_SERVICE",
        "ANALYSIS": "REMOTE_ANALYSIS",
    }.get(item_type, "FIELD_SERVICE")


def _audit(
    db: Session,
    *,
    actor: User,
    action: str,
    resource_type: str,
    resource_id: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=actor.id,
            user_email=actor.email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id[:36],
            details=_json(dict(details or {})),
        )
    )


def _validate_supplier(db: Session, supplier_id: str | None) -> None:
    if supplier_id and db.get(ProcurementSupplier, supplier_id) is None:
        raise CatalogError("supplier_not_found", "Internal supplier was not found")


def _validate_publishable(item: CatalogItem) -> None:
    if item.status != CatalogItemStatus.PUBLISHED.value:
        return
    if item.price_model == PriceModel.QUOTE.value:
        return
    prices = _json_dict(item.pricing_json)
    if item.unit_amount is not None:
        prices.setdefault(item.currency, item.unit_amount)
    if not prices:
        raise CatalogError(
            "published_price_required",
            "Published priced items require a non-negative minor-unit price",
        )


def _translations(item: CatalogItem) -> dict[str, dict[str, Any]]:
    content = _json_dict(item.customer_content_json)
    configured = content.get("translations")
    if isinstance(configured, dict) and configured:
        return configured
    existing = get_product_translations(item.id)
    if existing:
        return existing
    description = item.description or item.summary or ""
    summary = item.summary or description
    return {
        language: {
            "name": item.name,
            "description": description,
            "short_description": summary,
            "deliverables": _json_list(item.deliverables_json),
        }
        for language in ("pt", "en", "es", "fr")
    }


def public_item(item: CatalogItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "code": item.code,
        "slug": item.slug,
        "name": item.name,
        "summary": item.summary,
        "description": item.description,
        "item_type": item.item_type,
        "category": item.category,
        "sectors": _json_list(item.sectors_json),
        "asset_types": _json_list(item.asset_types_json),
        "customer_content": _json_dict(item.customer_content_json),
        "deliverables": _json_list(item.deliverables_json),
        "price_model": item.price_model,
        "currency": item.currency,
        "unit_amount": item.unit_amount,
        "pricing": {key: int(value) for key, value in _json_dict(item.pricing_json).items()},
        "availability_status": item.availability_status,
        "recommendation_triggers": _json_list(item.recommendation_triggers_json),
        "image_url": item.image_url,
        "is_featured": item.is_featured,
        "requires_site": item.requires_site,
        "requires_scheduling": item.requires_scheduling,
        "duration_hours": item.duration_hours,
        "fulfilment_type": item.fulfilment_type,
        "installed_product_type": item.installed_product_type,
        "translations": _translations(item),
    }


def internal_item(item: CatalogItem) -> dict[str, Any]:
    return {
        **public_item(item),
        "status": item.status,
        "metadata": _json_dict(item.metadata_json),
        "supplier_id": item.supplier_id,
        "legacy_source": item.legacy_source,
        "legacy_source_id": item.legacy_source_id,
        "published_at": item.published_at.isoformat() if item.published_at else None,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def list_public_items(
    db: Session,
    *,
    item_type: str | None = None,
    sector: str | None = None,
    asset_type: str | None = None,
    search: str | None = None,
) -> list[CatalogItem]:
    query = db.query(CatalogItem).filter(CatalogItem.status == "PUBLISHED")
    if item_type:
        query = query.filter(CatalogItem.item_type == _identifier(item_type, "SERVICE"))
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                CatalogItem.name.ilike(term),
                CatalogItem.summary.ilike(term),
                CatalogItem.description.ilike(term),
                CatalogItem.code.ilike(term),
            )
        )
    items = query.order_by(CatalogItem.is_featured.desc(), CatalogItem.name, CatalogItem.id).all()
    normalized_sector = normalize_sector(sector) if sector else None
    normalized_asset = normalize_asset_type(asset_type) if asset_type else None
    return [
        item
        for item in items
        if (normalized_sector is None or normalized_sector in _json_list(item.sectors_json))
        and (normalized_asset is None or normalized_asset in _json_list(item.asset_types_json))
    ]


def get_public_item(db: Session, reference: str) -> CatalogItem | None:
    return (
        db.query(CatalogItem)
        .filter(
            CatalogItem.status == "PUBLISHED",
            or_(
                CatalogItem.id == reference,
                CatalogItem.slug == reference,
                CatalogItem.code == reference.upper(),
            ),
        )
        .one_or_none()
    )


def list_internal_items(
    db: Session,
    *,
    status: str | None = None,
    item_type: str | None = None,
) -> list[CatalogItem]:
    query = db.query(CatalogItem)
    if status:
        query = query.filter(CatalogItem.status == _identifier(status, "DRAFT"))
    if item_type:
        query = query.filter(CatalogItem.item_type == _identifier(item_type, "SERVICE"))
    return query.order_by(CatalogItem.name, CatalogItem.id).all()


def create_item(db: Session, *, actor: User, data: CatalogItemCreate) -> CatalogItem:
    code = _identifier(data.code or data.name, "CATALOG_ITEM")[:100]
    slug = _slug(data.slug or data.name)[:200]
    if db.query(CatalogItem).filter(or_(CatalogItem.code == code, CatalogItem.slug == slug)).first():
        raise CatalogError("catalog_item_exists", "Catalogue code or slug already exists")
    _validate_supplier(db, data.supplier_id)
    prices = dict(data.pricing)
    if data.unit_amount is not None:
        prices.setdefault(data.currency, data.unit_amount)
    now = utc_now()
    item = CatalogItem(
        id=str(uuid.uuid4()),
        code=code,
        slug=slug,
        name=data.name.strip(),
        summary=data.summary,
        description=data.description,
        item_type=data.item_type.value,
        category=data.category,
        sectors_json=_json(sorted({normalize_sector(value) for value in data.sectors})),
        asset_types_json=_json(sorted({normalize_asset_type(value) for value in data.asset_types})),
        customer_content_json=_json(data.customer_content),
        deliverables_json=_json(data.deliverables),
        price_model=data.price_model.value,
        currency=data.currency,
        unit_amount=data.unit_amount,
        pricing_json=_json(prices),
        availability_status=data.availability_status.value,
        status=data.status.value,
        recommendation_triggers_json=_json(data.recommendation_triggers),
        metadata_json=_json(data.metadata),
        image_url=data.image_url,
        is_featured=data.is_featured,
        requires_site=data.requires_site,
        requires_scheduling=data.requires_scheduling,
        duration_hours=data.duration_hours,
        fulfilment_type=data.fulfilment_type or _fulfilment_type(data.item_type.value),
        installed_product_type=data.installed_product_type,
        supplier_id=data.supplier_id,
        published_at=now if data.status == CatalogItemStatus.PUBLISHED else None,
        created_by_user_id=actor.id,
        updated_by_user_id=actor.id,
        created_at=now,
        updated_at=now,
    )
    _validate_publishable(item)
    db.add(item)
    db.flush()
    mirror_catalog_item(db, item)
    _audit(
        db,
        actor=actor,
        action="catalog.item.created",
        resource_type="catalog_item",
        resource_id=item.id,
        details={"code": item.code, "status": item.status, "item_type": item.item_type},
    )
    return item


_JSON_UPDATE_FIELDS = {
    "sectors": "sectors_json",
    "asset_types": "asset_types_json",
    "customer_content": "customer_content_json",
    "deliverables": "deliverables_json",
    "pricing": "pricing_json",
    "recommendation_triggers": "recommendation_triggers_json",
    "metadata": "metadata_json",
}


def update_item(
    db: Session,
    *,
    actor: User,
    item: CatalogItem,
    data: CatalogItemUpdate,
) -> CatalogItem:
    changes = data.model_dump(exclude_unset=True)
    if "code" in changes:
        changes["code"] = _identifier(changes["code"], item.code)[:100]
    if "slug" in changes:
        changes["slug"] = _slug(changes["slug"], item.slug)[:200]
    for field in ("code", "slug"):
        if field in changes:
            duplicate = (
                db.query(CatalogItem)
                .filter(getattr(CatalogItem, field) == changes[field], CatalogItem.id != item.id)
                .first()
            )
            if duplicate:
                raise CatalogError("catalog_item_exists", f"Catalogue {field} already exists")
    if "supplier_id" in changes:
        _validate_supplier(db, changes["supplier_id"])
    previous_status = item.status
    for field, value in changes.items():
        if field in _JSON_UPDATE_FIELDS:
            if field == "sectors" and value is not None:
                value = sorted({normalize_sector(entry) for entry in value})
            elif field == "asset_types" and value is not None:
                value = sorted({normalize_asset_type(entry) for entry in value})
            empty_value = [] if field in {
                "sectors",
                "asset_types",
                "deliverables",
                "recommendation_triggers",
            } else {}
            setattr(
                item,
                _JSON_UPDATE_FIELDS[field],
                _json(value if value is not None else empty_value),
            )
        else:
            setattr(item, field, _enum_value(value))
    if "unit_amount" in changes and item.unit_amount is not None:
        prices = _json_dict(item.pricing_json)
        prices[item.currency] = item.unit_amount
        item.pricing_json = _json(prices)
    if "currency" in changes and item.unit_amount is not None:
        prices = _json_dict(item.pricing_json)
        prices.setdefault(item.currency, item.unit_amount)
        item.pricing_json = _json(prices)
    now = utc_now()
    if item.status == "PUBLISHED" and previous_status != "PUBLISHED":
        item.published_at = now
    elif item.status != "PUBLISHED":
        item.published_at = None
    item.updated_by_user_id = actor.id
    item.updated_at = now
    _validate_publishable(item)
    db.flush()
    mirror_catalog_item(db, item)
    _audit(
        db,
        actor=actor,
        action="catalog.item.updated",
        resource_type="catalog_item",
        resource_id=item.id,
        details={"fields": sorted(changes), "status": item.status},
    )
    return item


def supplier_internal(supplier: ProcurementSupplier) -> dict[str, Any]:
    return {
        "id": supplier.id,
        "code": supplier.code,
        "legal_name": supplier.legal_name,
        "status": supplier.status,
        "contact_email": supplier.contact_email,
        "contact_phone": supplier.contact_phone,
        "country_code": supplier.country_code,
        "region": supplier.region,
        "service_area": _json_list(supplier.service_area_json),
        "capabilities": _json_list(supplier.capabilities_json),
        "certifications": _json_list(supplier.certifications_json),
        "insurance": _json_dict(supplier.insurance_json),
        "document_refs": _json_list(supplier.document_refs_json),
        "quality_score": (
            float(supplier.quality_score) if supplier.quality_score is not None else None
        ),
        "last_reviewed_at": (
            supplier.last_reviewed_at.isoformat() if supplier.last_reviewed_at else None
        ),
        "notes": supplier.notes,
        "metadata": _json_dict(supplier.metadata_json),
        "created_at": supplier.created_at.isoformat(),
        "updated_at": supplier.updated_at.isoformat(),
    }


def create_supplier(
    db: Session, *, actor: User, data: SupplierCreate
) -> ProcurementSupplier:
    code = _identifier(data.code, "SUPPLIER")[:80]
    if db.query(ProcurementSupplier).filter(ProcurementSupplier.code == code).first():
        raise CatalogError("supplier_exists", "Internal supplier code already exists")
    now = utc_now()
    supplier = ProcurementSupplier(
        id=str(uuid.uuid4()),
        code=code,
        legal_name=data.legal_name.strip(),
        status=data.status,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        country_code=data.country_code,
        region=data.region,
        service_area_json=_json(data.service_area),
        capabilities_json=_json(data.capabilities),
        certifications_json=_json(data.certifications),
        insurance_json=_json(data.insurance),
        document_refs_json=_json(data.document_refs),
        quality_score=data.quality_score,
        last_reviewed_at=data.last_reviewed_at,
        notes=data.notes,
        metadata_json=_json(data.metadata),
        created_at=now,
        updated_at=now,
    )
    db.add(supplier)
    db.flush()
    _audit(
        db,
        actor=actor,
        action="catalog.supplier.created",
        resource_type="procurement_supplier",
        resource_id=supplier.id,
        details={"code": supplier.code, "status": supplier.status},
    )
    return supplier


def update_supplier(
    db: Session,
    *,
    actor: User,
    supplier: ProcurementSupplier,
    data: SupplierUpdate,
) -> ProcurementSupplier:
    changes = data.model_dump(exclude_unset=True)
    json_fields = {
        "service_area": "service_area_json",
        "capabilities": "capabilities_json",
        "certifications": "certifications_json",
        "insurance": "insurance_json",
        "document_refs": "document_refs_json",
    }
    for field, value in changes.items():
        if field == "metadata":
            supplier.metadata_json = _json(value if value is not None else {})
        elif field in json_fields:
            fallback = {} if field == "insurance" else []
            setattr(supplier, json_fields[field], _json(value if value is not None else fallback))
        else:
            setattr(supplier, field, value)
    supplier.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="catalog.supplier.updated",
        resource_type="procurement_supplier",
        resource_id=supplier.id,
        details={"fields": sorted(changes), "status": supplier.status},
    )
    return supplier


def list_suppliers(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    country_code: str | None = None,
    region: str | None = None,
    capability: str | None = None,
    limit: int = 200,
) -> list[ProcurementSupplier]:
    query = db.query(ProcurementSupplier)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                ProcurementSupplier.code.ilike(term),
                ProcurementSupplier.legal_name.ilike(term),
            )
        )
    if status:
        query = query.filter(ProcurementSupplier.status == status.upper())
    if country_code:
        query = query.filter(ProcurementSupplier.country_code == country_code.upper())
    if region:
        query = query.filter(ProcurementSupplier.region.ilike(f"%{region.strip()}%"))
    candidate_limit = min(2_000, max(limit, 500)) if capability else limit
    rows = (
        query.order_by(ProcurementSupplier.legal_name, ProcurementSupplier.id)
        .limit(candidate_limit)
        .all()
    )
    if capability:
        target = _identifier(capability, "")
        rows = [
            row
            for row in rows
            if target in {_identifier(value, "") for value in _json_list(row.capabilities_json)}
        ]
    return rows[:limit]


def deactivate_supplier(
    db: Session, *, actor: User, supplier: ProcurementSupplier
) -> ProcurementSupplier:
    supplier.status = "INACTIVE"
    supplier.updated_at = utc_now()
    _audit(
        db,
        actor=actor,
        action="catalog.supplier.deactivated",
        resource_type="procurement_supplier",
        resource_id=supplier.id,
        details={"code": supplier.code},
    )
    return supplier


def mirror_catalog_item(db: Session, item: CatalogItem) -> ShopProduct:
    """Keep checkout-compatible shop rows as a write-through projection."""

    product = db.get(ShopProduct, item.id)
    if product is None:
        product = ShopProduct(id=item.id, name=item.name, slug=item.slug)
        db.add(product)
    metadata = _json_dict(item.metadata_json)
    pricing = _json_dict(item.pricing_json)
    legacy_type = "hardware" if item.item_type == "PHYSICAL_PRODUCT" else (
        "subscription" if item.item_type == "MONITORING_PLAN" else "service"
    )
    product.name = item.name
    product.slug = item.slug
    product.description = item.description
    product.short_description = item.summary
    product.product_type = legacy_type
    product.category = item.category or item.item_type.lower()
    product.execution_type = metadata.get("execution_type") or (
        "recorrente" if item.item_type == "MONITORING_PLAN" else "pontual"
    )
    product.price = int(pricing.get("AOA", item.unit_amount or 0))
    product.price_usd = int(pricing.get("USD", 0))
    product.price_eur = int(pricing.get("EUR", 0))
    product.currency = item.currency
    product.tax_rate = float(metadata.get("tax_rate", 0.14))
    product.duration_hours = item.duration_hours
    product.requires_site = item.requires_site
    product.min_area_ha = metadata.get("min_area_ha")
    product.sectors_json = _json(
        [_LEGACY_SECTORS.get(value, str(value).lower()) for value in _json_list(item.sectors_json)]
    )
    product.deliverables_json = _json(_json_list(item.deliverables_json))
    product.image_url = item.image_url
    product.is_active = item.status == "PUBLISHED"
    product.is_featured = item.is_featured and product.is_active
    product.track_inventory = bool(metadata.get("track_inventory", False))
    product.stock_quantity = int(metadata.get("stock_quantity", 0))
    product.updated_at = item.updated_at
    return product


def sync_shop_product(db: Session, product: ShopProduct, *, overwrite: bool = False) -> CatalogItem:
    item = (
        db.query(CatalogItem)
        .filter(
            CatalogItem.legacy_source == "shop_products",
            CatalogItem.legacy_source_id == product.id,
        )
        .one_or_none()
    )
    if item is None:
        # Canonical writes intentionally reuse the checkout projection ID. A
        # later compatibility write must update that row, never create a
        # duplicate canonical item with the same slug.
        item = db.get(CatalogItem, product.id)
    if item is not None and not overwrite:
        return item
    now = product.updated_at or product.created_at or utc_now()
    item_type = _catalog_type(product.product_type, product.category, product.name)
    pricing = {
        currency: int(amount)
        for currency, amount in {
            "AOA": product.price,
            "USD": product.price_usd,
            "EUR": product.price_eur,
        }.items()
        if amount is not None and int(amount) > 0
    }
    if item is None:
        item = CatalogItem(
            id=product.id,
            code=_identifier(f"LEGACY_{product.id}", "LEGACY_PRODUCT")[:100],
            slug=product.slug,
            name=product.name,
            item_type=item_type,
            legacy_source="shop_products",
            legacy_source_id=product.id,
            created_at=product.created_at or now,
            updated_at=now,
        )
        db.add(item)
    item.name = product.name
    item.slug = product.slug
    item.summary = product.short_description
    item.description = product.description
    item.item_type = item_type
    item.category = product.category
    item.sectors_json = _json(sorted({normalize_sector(v) for v in _json_list(product.sectors_json)}))
    item.asset_types_json = _json([normalize_asset_type(product.category or "SITE")])
    item.customer_content_json = _json(
        {
            "short_description": product.short_description,
            "execution_type": product.execution_type,
            "minimum_area_hectares": product.min_area_ha,
        }
    )
    item.deliverables_json = _json(_json_list(product.deliverables_json))
    item.price_model = "SUBSCRIPTION" if item_type == "MONITORING_PLAN" else "FIXED"
    item.currency = product.currency or "AOA"
    item.unit_amount = int(product.price or 0)
    item.pricing_json = _json(pricing)
    item.availability_status = "AVAILABLE" if product.is_active else "UNAVAILABLE"
    item.status = "PUBLISHED" if product.is_active else "ARCHIVED"
    item.recommendation_triggers_json = _json([])
    item.metadata_json = _json(
        {
            "legacy": {"source": "shop_products", "id": product.id},
            "tax_rate": float(product.tax_rate or 0),
            "track_inventory": product.track_inventory,
            "stock_quantity": product.stock_quantity,
            "min_area_ha": product.min_area_ha,
            "execution_type": product.execution_type,
        }
    )
    item.image_url = product.image_url
    item.is_featured = product.is_featured
    item.requires_site = product.requires_site
    item.requires_scheduling = item_type not in {"PHYSICAL_PRODUCT", "ANALYSIS"}
    item.duration_hours = product.duration_hours
    item.fulfilment_type = _fulfilment_type(item_type)
    item.installed_product_type = product.category if item_type == "PHYSICAL_PRODUCT" else None
    item.published_at = (item.published_at or now) if product.is_active else None
    item.updated_at = now
    return item


def sync_basic_product(db: Session, product: Product, *, overwrite: bool = False) -> CatalogItem:
    item = (
        db.query(CatalogItem)
        .filter(
            CatalogItem.legacy_source == "products",
            CatalogItem.legacy_source_id == product.id,
        )
        .one_or_none()
    )
    if item is not None and not overwrite:
        mirror_catalog_item(db, item)
        return item
    now = product.updated_at or product.created_at or utc_now()
    item_id = f"legacy_{product.id}"[:50]
    if item is None:
        item = CatalogItem(
            id=item_id,
            code=_identifier(f"INVENTORY_{product.sku}", "INVENTORY_PRODUCT")[:100],
            slug=_slug(f"inventory-{product.sku}"),
            name=product.name,
            item_type="PHYSICAL_PRODUCT",
            legacy_source="products",
            legacy_source_id=product.id,
            created_at=product.created_at or now,
            updated_at=now,
        )
        db.add(item)
    primary_image = next((image.url for image in product.images if image.is_primary), None)
    item.name = product.name
    item.summary = product.description[:500] if product.description else None
    item.description = product.description
    item.category = product.category.slug if product.category else None
    item.sectors_json = _json([])
    item.asset_types_json = _json([])
    item.customer_content_json = _json({"brand": product.brand, "unit": product.unit})
    item.deliverables_json = _json([])
    item.price_model = "FIXED"
    item.currency = product.currency or "AOA"
    item.unit_amount = int(product.price or 0)
    item.pricing_json = _json({item.currency: int(product.price or 0)})
    item.availability_status = "AVAILABLE" if product.is_active else "UNAVAILABLE"
    item.status = "PUBLISHED" if product.is_active else "ARCHIVED"
    item.recommendation_triggers_json = _json([])
    item.metadata_json = _json(
        {
            "legacy": {"source": "products", "id": product.id},
            "sku": product.sku,
            "brand": product.brand,
            "track_inventory": True,
            "stock_quantity": product.inventory.qty_on_hand if product.inventory else 0,
        }
    )
    item.image_url = primary_image
    item.is_featured = False
    item.requires_site = False
    item.requires_scheduling = False
    item.fulfilment_type = "PHYSICAL_SHIPMENT"
    item.installed_product_type = product.category.slug if product.category else None
    item.published_at = (item.published_at or now) if product.is_active else None
    item.updated_at = now
    mirror_catalog_item(db, item)
    return item


def sync_catalog_from_legacy(db: Session) -> int:
    """Non-destructively import legacy rows once; canonical edits then win."""

    created_before = db.query(CatalogItem).count()
    for product in db.query(ShopProduct).order_by(ShopProduct.id).all():
        sync_shop_product(db, product)
    db.flush()
    for product in db.query(Product).order_by(Product.id).all():
        sync_basic_product(db, product)
    db.commit()
    return db.query(CatalogItem).count() - created_before


def legacy_product(item: CatalogItem) -> dict[str, Any]:
    """Project canonical data into the existing `/shop/products` response."""

    metadata = _json_dict(item.metadata_json)
    content = _json_dict(item.customer_content_json)
    prices = _json_dict(item.pricing_json)
    product_type = "hardware" if item.item_type == "PHYSICAL_PRODUCT" else (
        "subscription" if item.item_type == "MONITORING_PLAN" else "service"
    )
    return {
        "id": item.id,
        "name": item.name,
        "slug": item.slug,
        "description": item.description,
        "short_description": item.summary,
        "product_type": product_type,
        "category": item.category,
        "execution_type": content.get("execution_type") or metadata.get("execution_type"),
        "price": int(prices.get("AOA", item.unit_amount or 0)),
        "price_usd": int(prices.get("USD", 0)),
        "price_eur": int(prices.get("EUR", 0)),
        "currency": item.currency,
        "tax_rate": float(metadata.get("tax_rate", 0.14)),
        "duration_hours": item.duration_hours,
        "requires_site": item.requires_site,
        "requires_scheduling": item.requires_scheduling,
        "min_area_ha": content.get("minimum_area_hectares") or metadata.get("min_area_ha"),
        "sectors": [
            _LEGACY_SECTORS.get(value, str(value).lower())
            for value in _json_list(item.sectors_json)
        ],
        "deliverables": _json_list(item.deliverables_json),
        "translations": _translations(item),
        "image_url": item.image_url,
        "is_active": item.status == "PUBLISHED",
        "is_featured": item.is_featured,
        "track_inventory": bool(metadata.get("track_inventory", False)),
        "stock_quantity": int(metadata.get("stock_quantity", 0)),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


__all__ = [
    "CatalogError",
    "create_item",
    "create_supplier",
    "deactivate_supplier",
    "get_public_item",
    "internal_item",
    "legacy_product",
    "list_internal_items",
    "list_public_items",
    "list_suppliers",
    "mirror_catalog_item",
    "normalize_asset_type",
    "normalize_sector",
    "public_item",
    "supplier_internal",
    "sync_basic_product",
    "sync_catalog_from_legacy",
    "sync_shop_product",
    "update_item",
    "update_supplier",
]

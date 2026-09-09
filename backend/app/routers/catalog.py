"""Canonical GeoVision-owned catalogue API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import CatalogItem, ProcurementSupplier, User
from app.modules.catalog.schemas import (
    CatalogItemCreate,
    CatalogItemInternal,
    CatalogItemPublic,
    CatalogItemUpdate,
    SupplierCreate,
    SupplierInternal,
    SupplierUpdate,
)
from app.modules.catalog.services import (
    CatalogError,
    create_item,
    create_supplier,
    get_public_item,
    internal_item,
    list_internal_items,
    list_public_items,
    public_item,
    supplier_internal,
    update_item,
    update_supplier,
)
from app.modules.organizations.domain import internal_permissions
from app.modules.organizations.services import active_internal_roles


router = APIRouter(prefix="/catalog", tags=["catalog"])

_CATALOG_MANAGEMENT_PERMISSIONS = {
    "platform:admin",
    "inventory:internal",
    "sales:internal",
    "operations:access",
}


def require_catalog_staff(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    permissions = internal_permissions(active_internal_roles(db, user))
    if not permissions.intersection(_CATALOG_MANAGEMENT_PERMISSIONS):
        raise HTTPException(status_code=403, detail="Catalogue staff permission required")
    return user


CatalogStaff = Annotated[User, Depends(require_catalog_staff)]


def _raise_catalog_error(exc: CatalogError) -> None:
    error_status = {
        "catalog_item_exists": status.HTTP_409_CONFLICT,
        "supplier_exists": status.HTTP_409_CONFLICT,
        "supplier_not_found": status.HTTP_404_NOT_FOUND,
    }.get(exc.code, status.HTTP_422_UNPROCESSABLE_ENTITY)
    raise HTTPException(
        status_code=error_status,
        detail={"code": exc.code, "message": str(exc)},
    ) from exc


@router.get("/items", response_model=list[CatalogItemPublic])
def browse_catalog(
    item_type: str | None = Query(default=None),
    sector: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    """Browse only customer-published, GeoVision-owned offers."""

    return [
        public_item(item)
        for item in list_public_items(
            db,
            item_type=item_type,
            sector=sector,
            asset_type=asset_type,
            search=search,
        )
    ]


@router.get("/items/{reference}", response_model=CatalogItemPublic)
def catalog_item_detail(reference: str, db: Session = Depends(get_db)):
    item = get_public_item(db, reference)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalogue item not found")
    return public_item(item)


@router.get("/internal/items", response_model=list[CatalogItemInternal])
def staff_catalog_items(
    actor: CatalogStaff,
    item_status: str | None = Query(default=None, alias="status"),
    item_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    del actor
    return [
        internal_item(item)
        for item in list_internal_items(db, status=item_status, item_type=item_type)
    ]


@router.get("/internal/items/{item_id}", response_model=CatalogItemInternal)
def staff_catalog_item(item_id: str, actor: CatalogStaff, db: Session = Depends(get_db)):
    del actor
    item = db.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalogue item not found")
    return internal_item(item)


@router.post(
    "/internal/items",
    response_model=CatalogItemInternal,
    status_code=status.HTTP_201_CREATED,
)
def staff_create_catalog_item(
    data: CatalogItemCreate,
    actor: CatalogStaff,
    db: Session = Depends(get_db),
):
    try:
        item = create_item(db, actor=actor, data=data)
        db.commit()
        db.refresh(item)
        return internal_item(item)
    except CatalogError as exc:
        db.rollback()
        _raise_catalog_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Catalogue code or slug already exists") from exc


@router.patch("/internal/items/{item_id}", response_model=CatalogItemInternal)
def staff_update_catalog_item(
    item_id: str,
    data: CatalogItemUpdate,
    actor: CatalogStaff,
    db: Session = Depends(get_db),
):
    item = db.get(CatalogItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Catalogue item not found")
    try:
        item = update_item(db, actor=actor, item=item, data=data)
        db.commit()
        db.refresh(item)
        return internal_item(item)
    except CatalogError as exc:
        db.rollback()
        _raise_catalog_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Catalogue update conflicts with an existing item") from exc


@router.get("/internal/suppliers", response_model=list[SupplierInternal])
def staff_suppliers(actor: CatalogStaff, db: Session = Depends(get_db)):
    del actor
    suppliers = db.query(ProcurementSupplier).order_by(ProcurementSupplier.legal_name).all()
    return [supplier_internal(supplier) for supplier in suppliers]


@router.post(
    "/internal/suppliers",
    response_model=SupplierInternal,
    status_code=status.HTTP_201_CREATED,
)
def staff_create_supplier(
    data: SupplierCreate,
    actor: CatalogStaff,
    db: Session = Depends(get_db),
):
    try:
        supplier = create_supplier(db, actor=actor, data=data)
        db.commit()
        db.refresh(supplier)
        return supplier_internal(supplier)
    except CatalogError as exc:
        db.rollback()
        _raise_catalog_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Internal supplier code already exists") from exc


@router.patch("/internal/suppliers/{supplier_id}", response_model=SupplierInternal)
def staff_update_supplier(
    supplier_id: str,
    data: SupplierUpdate,
    actor: CatalogStaff,
    db: Session = Depends(get_db),
):
    supplier = db.get(ProcurementSupplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Internal supplier not found")
    try:
        supplier = update_supplier(db, actor=actor, supplier=supplier, data=data)
        db.commit()
        db.refresh(supplier)
        return supplier_internal(supplier)
    except CatalogError as exc:
        db.rollback()
        _raise_catalog_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Supplier update conflicts with existing data") from exc


__all__ = ["router"]

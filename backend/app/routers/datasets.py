"""Canonical tenant-safe dataset registry and secure object upload API."""

from __future__ import annotations

import tempfile

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.deps import get_authorization_context, get_current_user, get_db
from app.models import DatasetFile, User
from app.modules.assets.services import AssetAccessError
from app.modules.datasets.domain import (
    DatasetError,
    DatasetStatus,
    ObjectArea,
    normalize_dataset_type,
)
from app.modules.datasets.schemas import (
    DatasetCreate,
    DatasetFileOut,
    DatasetListResponse,
    DatasetOut,
    DatasetUpdate,
    PresignedUrlRequest,
    PresignedUrlResponse,
    SourceTool,
)
from app.modules.datasets.services import (
    archive_dataset,
    complete_reserved_upload_from_stream,
    confirm_reserved_upload,
    create_dataset as create_dataset_record,
    dataset_file_out,
    dataset_out,
    delete_dataset_file,
    download_url,
    finalize_dataset as finalize_dataset_record,
    get_owned_dataset,
    list_owned_datasets,
    reserve_upload,
    update_dataset as update_dataset_record,
    upload_dataset_file,
)
from app.modules.identity.domain import AuthorizationContext
from app.services.storage import StorageService, get_storage_service


router = APIRouter(
    prefix="/datasets",
    tags=["datasets"],
    dependencies=[Depends(get_current_user)],
)


def _storage() -> StorageService:
    return get_storage_service()


def _raise_dataset_error(exc: Exception) -> None:
    code = getattr(exc, "code", "invalid_dataset")
    if code in {
        "asset_not_found",
        "dataset_not_found",
        "file_not_found",
        "mission_not_found",
        "upload_not_found",
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif code in {"dataset_access_denied", "workspace_required"}:
        status_code = status.HTTP_403_FORBIDDEN
    elif code == "file_too_large":
        status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    elif code in {
        "dataset_archived",
        "invalid_transition",
        "storage_provider_mismatch",
        "version_conflict",
    }:
        status_code = status.HTTP_409_CONFLICT
    elif code == "upload_missing":
        status_code = status.HTTP_400_BAD_REQUEST
    elif code == "upload_expired":
        status_code = status.HTTP_410_GONE
    else:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(exc)},
    ) from exc


def _requested_company(
    context: AuthorizationContext,
    company_id: str | None,
) -> None:
    if company_id and company_id != context.active_organization_id:
        raise HTTPException(status_code=404, detail="Organization was not found")


@router.put("/storage/local", status_code=status.HTTP_204_NO_CONTENT)
async def put_local_object(
    request: Request,
    key: str = Query(..., min_length=1, max_length=2_000),
    expires: int = Query(..., ge=1),
    upload: bool = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    provider = storage.provider
    validator = getattr(provider, "validate_signature", None)
    if storage.provider_name != "local" or not callable(validator):
        raise HTTPException(status_code=404, detail="Local storage is unavailable")
    if not upload or not validator(
        key=key,
        expires=expires,
        for_upload=True,
        signature=signature,
    ):
        raise HTTPException(status_code=403, detail="Upload URL is invalid or expired")
    reserved = db.query(DatasetFile).filter(DatasetFile.storage_key == key).one_or_none()
    if reserved is None:
        raise HTTPException(status_code=404, detail="Upload reservation not found")
    try:
        dataset = get_owned_dataset(
            db,
            context=context,
            dataset_id=reserved.dataset_id,
            write=True,
        )
        try:
            content_length = int(request.headers.get("content-length") or 0)
        except ValueError as exc:
            raise DatasetError(
                "invalid_file_size", "Content-Length must be an integer"
            ) from exc
        if content_length < 0:
            raise DatasetError(
                "invalid_file_size", "Content-Length cannot be negative"
            )
        if content_length > settings.dataset_signed_upload_max_bytes:
            raise DatasetError("file_too_large", "Signed upload exceeds its size limit")
        size_bytes = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as stream:
            async for chunk in request.stream():
                size_bytes += len(chunk)
                if size_bytes > settings.dataset_signed_upload_max_bytes:
                    raise DatasetError(
                        "file_too_large", "Signed upload exceeds its size limit"
                    )
                stream.write(chunk)
            stream.seek(0)
            complete_reserved_upload_from_stream(
                db,
                actor=actor,
                dataset=dataset,
                storage_key=key,
                file_obj=stream,
                content_type=request.headers.get("content-type"),
                storage=storage,
            )
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except (RuntimeError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Object upload failed") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/storage/local")
def get_local_object(
    key: str = Query(..., min_length=1, max_length=2_000),
    expires: int = Query(..., ge=1),
    upload: bool = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    provider = storage.provider
    validator = getattr(provider, "validate_signature", None)
    path_resolver = getattr(provider, "path_for", None)
    if (
        storage.provider_name != "local"
        or not callable(validator)
        or not callable(path_resolver)
    ):
        raise HTTPException(status_code=404, detail="Local storage is unavailable")
    if upload or not validator(
        key=key,
        expires=expires,
        for_upload=False,
        signature=signature,
    ):
        raise HTTPException(status_code=403, detail="Download URL is invalid or expired")
    file = db.query(DatasetFile).filter(DatasetFile.storage_key == key).one_or_none()
    if file is None or file.status != "uploaded":
        raise HTTPException(status_code=404, detail="Dataset file not found")
    try:
        get_owned_dataset(
            db,
            context=context,
            dataset_id=file.dataset_id,
            write=False,
        )
        path = path_resolver(key)
    except (DatasetError, AssetAccessError, ValueError) as exc:
        _raise_dataset_error(exc)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Dataset file not found")
    return FileResponse(path, filename=file.filename, media_type=file.mime_type)


@router.post("/", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
def create_dataset(
    data: DatasetCreate,
    company_id: str | None = Query(default=None, description="Legacy organization ID"),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    _requested_company(context, company_id)
    try:
        dataset = create_dataset_record(
            db,
            actor=actor,
            context=context,
            data=data,
            storage=storage,
        )
        db.commit()
        db.refresh(dataset)
        return dataset_out(dataset)
    except (DatasetError, AssetAccessError, ValueError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Dataset conflicts with existing data") from exc


@router.get("/", response_model=DatasetListResponse)
def list_datasets(
    company_id: str | None = Query(default=None, description="Legacy organization ID"),
    site_id: str | None = Query(default=None, max_length=36),
    asset_id: str | None = Query(default=None, max_length=36),
    sector: str | None = Query(default=None, max_length=50),
    dataset_status: DatasetStatus | None = Query(default=None, alias="status"),
    source_tool: SourceTool | None = None,
    dataset_type: str | None = Query(default=None, max_length=80),
    include_archived: bool = False,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    _requested_company(context, company_id)
    try:
        normalized_type = normalize_dataset_type(dataset_type) if dataset_type else None
        rows, total = list_owned_datasets(
            db,
            context=context,
            asset_id=asset_id,
            site_id=site_id,
            sector=sector,
            status=dataset_status.value if dataset_status else None,
            source_tool=source_tool.value if source_tool else None,
            dataset_type=normalized_type,
            include_archived=include_archived,
            page=page,
            per_page=per_page,
        )
        return DatasetListResponse(
            datasets=[DatasetOut.model_validate(dataset_out(row)) for row in rows],
            total=total,
            page=page,
            per_page=per_page,
        )
    except (DatasetError, AssetAccessError, ValueError) as exc:
        _raise_dataset_error(exc)


@router.get("/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=False
        )
        return dataset_out(dataset)
    except (DatasetError, AssetAccessError) as exc:
        _raise_dataset_error(exc)


@router.patch("/{dataset_id}", response_model=DatasetOut)
def update_dataset(
    dataset_id: str,
    data: DatasetUpdate,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        update_dataset_record(db, actor=actor, dataset=dataset, data=data)
        db.commit()
        db.refresh(dataset)
        return dataset_out(dataset)
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        dataset = get_owned_dataset(
            db,
            context=context,
            dataset_id=dataset_id,
            write=True,
            include_archived=True,
        )
        archive_dataset(db, actor=actor, dataset=dataset)
        db.commit()
        return {
            "message": "Dataset archived; tracked objects were retained",
            "id": dataset_id,
        }
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)


@router.post("/{dataset_id}/upload", response_model=DatasetFileOut)
async def upload_file(
    dataset_id: str,
    file: UploadFile = File(...),
    object_area: ObjectArea | None = Form(default=None),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        filename = file.filename or f"upload_{dataset_id}.bin"
        row = upload_dataset_file(
            db,
            actor=actor,
            dataset=dataset,
            file_obj=file.file,
            filename=filename,
            content_type=file.content_type,
            storage=storage,
            object_area=object_area,
        )
        return dataset_file_out(row)
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except (RuntimeError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Object upload failed") from exc
    finally:
        await file.close()


@router.post(
    "/{dataset_id}/presigned-url",
    response_model=PresignedUrlResponse,
)
def get_upload_url(
    dataset_id: str,
    request: PresignedUrlRequest,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        file, upload_url, expires_in = reserve_upload(
            db,
            actor=actor,
            dataset=dataset,
            filename=request.filename,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            storage=storage,
            object_area=request.object_area,
        )
        headers: dict[str, str] = {}
        if request.content_type:
            headers["Content-Type"] = request.content_type
        if storage.provider_name == "azure_blob":
            headers["x-ms-blob-type"] = "BlockBlob"
        return PresignedUrlResponse(
            upload_url=upload_url,
            storage_key=file.storage_key or "",
            expires_in=expires_in,
            file_id=file.id,
            storage_provider=storage.provider_name,
            required_headers=headers,
        )
    except (DatasetError, AssetAccessError, ValueError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Signed upload is unavailable") from exc


@router.post("/{dataset_id}/confirm-upload", response_model=DatasetFileOut)
def confirm_upload(
    dataset_id: str,
    storage_key: str = Form(..., min_length=1, max_length=2_000),
    filename: str = Form(..., min_length=1, max_length=240),
    size_bytes: int = Form(..., ge=0),
    sha256_hash: str | None = Form(default=None, max_length=64),
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        file = confirm_reserved_upload(
            db,
            actor=actor,
            dataset=dataset,
            storage_key=storage_key,
            filename=filename,
            claimed_size_bytes=size_bytes,
            sha256_hash=sha256_hash,
            storage=storage,
        )
        return dataset_file_out(file)
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail="Upload confirmation failed") from exc


@router.get("/{dataset_id}/files/{file_id}/download")
def get_download_url(
    dataset_id: str,
    file_id: str,
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=False
        )
        file, url, expires_in = download_url(
            dataset=dataset,
            file_id=file_id,
            storage=storage,
        )
        return {
            "download_url": url,
            "filename": file.filename,
            "expires_in": expires_in,
        }
    except (DatasetError, AssetAccessError) as exc:
        _raise_dataset_error(exc)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Download is unavailable") from exc


@router.delete("/{dataset_id}/files/{file_id}")
def delete_file(
    dataset_id: str,
    file_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(_storage),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        delete_dataset_file(
            db,
            actor=actor,
            dataset=dataset,
            file_id=file_id,
            storage=storage,
        )
        return {"message": "File deleted", "id": file_id}
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=502,
            detail="Storage deletion failed; database reference was retained",
        ) from exc


@router.post("/{dataset_id}/finalize", response_model=DatasetOut)
def finalize_dataset(
    dataset_id: str,
    actor: User = Depends(get_current_user),
    context: AuthorizationContext = Depends(get_authorization_context),
    db: Session = Depends(get_db),
):
    try:
        dataset = get_owned_dataset(
            db, context=context, dataset_id=dataset_id, write=True
        )
        finalize_dataset_record(db, actor=actor, dataset=dataset)
        db.commit()
        db.refresh(dataset)
        return dataset_out(dataset)
    except (DatasetError, AssetAccessError) as exc:
        db.rollback()
        _raise_dataset_error(exc)


@router.post("/webhooks/{source_tool}")
def source_webhook(
    source_tool: SourceTool,
    company_id: str | None = Query(default=None),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    _requested_company(context, company_id)
    return {
        "status": "not_implemented",
        "source_tool": source_tool.value,
        "message": "Use the authenticated dataset upload flow for provider data",
    }


@router.post("/sync/{source_tool}")
def sync_from_source(
    source_tool: SourceTool,
    company_id: str | None = Query(default=None),
    site_id: str | None = Query(default=None),
    project_id: str | None = Query(default=None, description="External project ID"),
    context: AuthorizationContext = Depends(get_authorization_context),
):
    del site_id, project_id
    _requested_company(context, company_id)
    return {
        "status": "not_implemented",
        "source_tool": source_tool.value,
        "message": "Provider sync requires a configured adapter; direct upload is available",
    }


__all__ = ["router"]

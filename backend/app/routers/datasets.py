"""
Dataset Registry Router

Endpoints for dataset ingestion from external tools:
- DJI Terra, Pix4D, Metashape, DroneDeploy
- ArcGIS, QGIS, LiDAR processors
- BIM 360, Procore

Supported file types:
- GeoTIFF, DSM/DTM, Orthomosaics
- OBJ/FBX 3D models
- LAS/LAZ/E57 point clouds
- PDF reports, CSV, Shapefiles, GeoJSON, DXF/DWG
"""
import uuid
import logging
from datetime import datetime
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.services.storage import get_storage_service, detect_file_type, detect_mime_type

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/datasets", tags=["datasets"], dependencies=[Depends(get_current_user)])


# ============ ENUMS ============

class SourceTool(str, Enum):
    DJI_TERRA = "dji_terra"
    PIX4D = "pix4d"
    METASHAPE = "metashape"
    DRONEDEPLOY = "dronedeploy"
    ARCGIS = "arcgis"
    QGIS = "qgis"
    LIDAR_PROC = "lidar_processor"
    BIM360 = "bim360"
    PROCORE = "procore"
    MANUAL = "manual"
    API = "api"


class DatasetStatus(str, Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class FileType(str, Enum):
    GEOTIFF = "geotiff"
    DSM = "dsm"
    DTM = "dtm"
    ORTHOMOSAIC = "orthomosaic"
    POINTCLOUD_LAS = "pointcloud_las"
    POINTCLOUD_LAZ = "pointcloud_laz"
    POINTCLOUD_E57 = "pointcloud_e57"
    MODEL_OBJ = "model_obj"
    MODEL_FBX = "model_fbx"
    SHAPEFILE = "shapefile"
    GEOJSON = "geojson"
    DXF = "dxf"
    DWG = "dwg"
    PDF = "pdf"
    CSV = "csv"
    IMAGE = "image"
    OTHER = "other"


# ============ SCHEMAS ============

class DatasetFileOut(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    storage_key: str
    download_url: Optional[str] = None
    md5_hash: Optional[str] = None
    created_at: datetime


class DatasetOut(BaseModel):
    id: str
    company_id: str
    site_id: str
    name: str
    description: Optional[str] = None
    source_tool: str
    status: str
    sector: Optional[str] = None
    capture_date: Optional[datetime] = None
    files: List[DatasetFileOut] = []
    file_count: int = 0
    total_size_bytes: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DatasetCreate(BaseModel):
    site_id: str
    name: str
    description: Optional[str] = None
    source_tool: SourceTool = SourceTool.MANUAL
    sector: Optional[str] = None
    capture_date: Optional[datetime] = None
    metadata: Optional[dict] = None


class DatasetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[DatasetStatus] = None
    capture_date: Optional[datetime] = None
    metadata: Optional[dict] = None


class PresignedUrlRequest(BaseModel):
    filename: str
    content_type: Optional[str] = None


class PresignedUrlResponse(BaseModel):
    upload_url: str
    storage_key: str
    expires_in: int = 3600


class DatasetListResponse(BaseModel):
    datasets: List[DatasetOut]
    total: int
    page: int
    per_page: int


# ============ IN-MEMORY STORE (replace with DB) ============
# For now, using in-memory store until DB migration is run

_datasets_store: dict = {}
_files_store: dict = {}


# ============ ENDPOINTS ============

@router.post("/", response_model=DatasetOut)
async def create_dataset(
    data: DatasetCreate,
    company_id: str = Query(..., description="Company ID"),
):
    """
    Create a new dataset record.
    
    After creating, use /datasets/{id}/upload or /datasets/{id}/presigned-url
    to upload files.
    """
    dataset_id = str(uuid.uuid4())
    now = datetime.utcnow()
    
    dataset = {
        "id": dataset_id,
        "company_id": company_id,
        "site_id": data.site_id,
        "name": data.name,
        "description": data.description,
        "source_tool": data.source_tool.value,
        "status": DatasetStatus.UPLOADING.value,
        "sector": data.sector,
        "capture_date": data.capture_date,
        "metadata": data.metadata or {},
        "files": [],
        "file_count": 0,
        "total_size_bytes": 0,
        "created_at": now,
        "updated_at": now,
    }
    
    _datasets_store[dataset_id] = dataset
    
    logger.info(f"Created dataset {dataset_id} for company {company_id}")
    
    return DatasetOut(**dataset)


@router.get("/", response_model=DatasetListResponse)
async def list_datasets(
    company_id: str = Query(...),
    site_id: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    status: Optional[DatasetStatus] = Query(None),
    source_tool: Optional[SourceTool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List datasets with filtering."""
    
    # Filter datasets
    datasets = [d for d in _datasets_store.values() if d["company_id"] == company_id]
    
    if site_id:
        datasets = [d for d in datasets if d["site_id"] == site_id]
    if sector:
        datasets = [d for d in datasets if d.get("sector") == sector]
    if status:
        datasets = [d for d in datasets if d["status"] == status.value]
    if source_tool:
        datasets = [d for d in datasets if d["source_tool"] == source_tool.value]
    
    total = len(datasets)
    
    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    datasets = datasets[start:end]
    
    return DatasetListResponse(
        datasets=[DatasetOut(**d) for d in datasets],
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str):
    """Get dataset by ID."""
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return DatasetOut(**_datasets_store[dataset_id])


@router.patch("/{dataset_id}", response_model=DatasetOut)
async def update_dataset(dataset_id: str, data: DatasetUpdate):
    """Update dataset metadata."""
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    if data.name is not None:
        dataset["name"] = data.name
    if data.description is not None:
        dataset["description"] = data.description
    if data.status is not None:
        dataset["status"] = data.status.value
    if data.capture_date is not None:
        dataset["capture_date"] = data.capture_date
    if data.metadata is not None:
        dataset["metadata"].update(data.metadata)
    
    dataset["updated_at"] = datetime.utcnow()
    
    return DatasetOut(**dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str):
    """Delete dataset and all files."""
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    # Delete files from storage
    storage = get_storage_service()
    for file_info in dataset.get("files", []):
        try:
            storage.delete_file(file_info["storage_key"])
        except Exception as e:
            logger.warning(f"Failed to delete file {file_info['storage_key']}: {e}")
    
    # Remove from store
    del _datasets_store[dataset_id]
    
    return {"message": "Dataset deleted", "id": dataset_id}


@router.post("/{dataset_id}/upload", response_model=DatasetFileOut)
async def upload_file(
    dataset_id: str,
    file: UploadFile = File(...),
):
    """
    Direct file upload to dataset.
    
    For large files (>100MB), use presigned URL instead.
    """
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    # Validate file size (max 500MB for direct upload)
    MAX_SIZE = 500 * 1024 * 1024  # 500MB
    content = await file.read()
    
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max {MAX_SIZE // (1024*1024)}MB for direct upload. Use presigned URL for larger files."
        )
    
    # Upload to S3
    storage = get_storage_service()
    
    filename = file.filename or f"upload_{dataset_id}"
    
    storage_key = storage.generate_key(
        company_id=dataset["company_id"],
        site_id=dataset["site_id"],
        dataset_id=dataset_id,
        filename=filename
    )
    
    from io import BytesIO
    key, size_bytes, md5_hash, sha256_hash = storage.upload_bytes(
        data=content,
        key=storage_key,
        content_type=file.content_type or detect_mime_type(filename),
        metadata={
            "dataset_id": dataset_id,
            "original_filename": file.filename,
            "source_tool": dataset["source_tool"],
        }
    )
    
    # Create file record
    file_id = str(uuid.uuid4())
    file_type = detect_file_type(filename)
    
    file_record = {
        "id": file_id,
        "filename": filename,
        "file_type": file_type,
        "size_bytes": size_bytes,
        "storage_key": storage_key,
        "md5_hash": md5_hash,
        "sha256_hash": sha256_hash,
        "created_at": datetime.utcnow(),
    }
    
    # Update dataset
    dataset["files"].append(file_record)
    dataset["file_count"] = len(dataset["files"])
    dataset["total_size_bytes"] = sum(f["size_bytes"] for f in dataset["files"])
    dataset["updated_at"] = datetime.utcnow()
    
    # Auto-update status if first file
    if dataset["status"] == DatasetStatus.UPLOADING.value:
        dataset["status"] = DatasetStatus.PROCESSING.value
    
    logger.info(f"Uploaded file {file.filename} to dataset {dataset_id}")
    
    return DatasetFileOut(**file_record)


@router.post("/{dataset_id}/presigned-url", response_model=PresignedUrlResponse)
async def get_upload_url(
    dataset_id: str,
    request: PresignedUrlRequest,
):
    """
    Get presigned URL for direct upload to S3.
    
    Use this for large files (>100MB) to upload directly from client.
    """
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    storage = get_storage_service()
    
    storage_key = storage.generate_key(
        company_id=dataset["company_id"],
        site_id=dataset["site_id"],
        dataset_id=dataset_id,
        filename=request.filename
    )
    
    upload_url = storage.get_presigned_url(
        key=storage_key,
        expires_in=3600,
        for_upload=True
    )
    
    return PresignedUrlResponse(
        upload_url=upload_url,
        storage_key=storage_key,
        expires_in=3600
    )


@router.post("/{dataset_id}/confirm-upload")
async def confirm_upload(
    dataset_id: str,
    storage_key: str = Form(...),
    filename: str = Form(...),
    size_bytes: int = Form(...),
):
    """
    Confirm upload after using presigned URL.
    
    Call this after successful direct upload to S3 to register the file.
    """
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    # Verify file exists in S3
    storage = get_storage_service()
    if not storage.file_exists(storage_key):
        raise HTTPException(status_code=400, detail="File not found in storage")
    
    # Create file record
    file_id = str(uuid.uuid4())
    file_type = detect_file_type(filename)
    
    file_record = {
        "id": file_id,
        "filename": filename,
        "file_type": file_type,
        "size_bytes": size_bytes,
        "storage_key": storage_key,
        "md5_hash": None,
        "created_at": datetime.utcnow(),
    }
    
    # Update dataset
    dataset["files"].append(file_record)
    dataset["file_count"] = len(dataset["files"])
    dataset["total_size_bytes"] = sum(f["size_bytes"] for f in dataset["files"])
    dataset["updated_at"] = datetime.utcnow()
    
    return DatasetFileOut(**file_record)


@router.get("/{dataset_id}/files/{file_id}/download")
async def get_download_url(dataset_id: str, file_id: str):
    """Get presigned download URL for a file."""
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    # Find file
    file_record = next((f for f in dataset["files"] if f["id"] == file_id), None)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    storage = get_storage_service()
    download_url = storage.get_presigned_url(
        key=file_record["storage_key"],
        expires_in=3600,
        for_upload=False
    )
    
    return {
        "download_url": download_url,
        "filename": file_record["filename"],
        "expires_in": 3600,
    }


@router.delete("/{dataset_id}/files/{file_id}")
async def delete_file(dataset_id: str, file_id: str):
    """Delete a file from dataset."""
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    # Find file
    file_record = next((f for f in dataset["files"] if f["id"] == file_id), None)
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Delete from S3
    storage = get_storage_service()
    storage.delete_file(file_record["storage_key"])
    
    # Remove from dataset
    dataset["files"] = [f for f in dataset["files"] if f["id"] != file_id]
    dataset["file_count"] = len(dataset["files"])
    dataset["total_size_bytes"] = sum(f["size_bytes"] for f in dataset["files"])
    dataset["updated_at"] = datetime.utcnow()
    
    return {"message": "File deleted", "id": file_id}


@router.post("/{dataset_id}/finalize", response_model=DatasetOut)
async def finalize_dataset(dataset_id: str):
    """
    Mark dataset as ready after all files are uploaded.
    
    This triggers any post-processing (e.g., thumbnail generation, metadata extraction).
    """
    
    if dataset_id not in _datasets_store:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    dataset = _datasets_store[dataset_id]
    
    if not dataset["files"]:
        raise HTTPException(status_code=400, detail="Dataset has no files")
    
    dataset["status"] = DatasetStatus.READY.value
    dataset["updated_at"] = datetime.utcnow()
    
    # TODO: Trigger async processing (thumbnails, metadata extraction, etc.)
    
    logger.info(f"Finalized dataset {dataset_id} with {dataset['file_count']} files")
    
    return DatasetOut(**dataset)


# ============ CONNECTOR WEBHOOKS ============

@router.post("/webhooks/{source_tool}")
async def source_webhook(
    source_tool: SourceTool,
    company_id: str = Query(...),
):
    """
    Webhook endpoint for external tools to push data.
    
    Each tool sends data in its own format, which we normalize.
    """
    
    # TODO: Implement per-tool webhook handlers
    # - DJI Terra: Project export notifications
    # - Pix4D: Processing complete callbacks
    # - BIM 360: Model update webhooks
    
    return {
        "status": "received",
        "source_tool": source_tool.value,
        "message": f"Webhook handler for {source_tool.value} not yet implemented"
    }


# ============ API CONNECTOR SYNC ============

@router.post("/sync/{source_tool}")
async def sync_from_source(
    source_tool: SourceTool,
    company_id: str = Query(...),
    site_id: str = Query(...),
    project_id: Optional[str] = Query(None, description="External project ID"),
):
    """
    Pull data from external tool API.
    
    Requires API credentials configured for the company.
    """
    
    # TODO: Implement per-tool API sync
    # - Pix4D Cloud API
    # - DroneDeploy API
    # - BIM 360 API
    
    return {
        "status": "not_implemented",
        "source_tool": source_tool.value,
        "message": f"API sync for {source_tool.value} coming soon. Please use direct upload or webhooks."
    }

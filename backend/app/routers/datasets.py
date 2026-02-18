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
import json
import logging
from datetime import datetime
from typing import Optional, List
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
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
    model_config = ConfigDict(from_attributes=True)


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


# ============ DB-backed (no more in-memory store) ============

def _ds_out(ds) -> DatasetOut:
    """Convert Dataset ORM object to DatasetOut schema."""
    files = []
    for f in ds.files:
        files.append(DatasetFileOut(
            id=f.id, filename=f.filename, file_type=detect_file_type(f.filename),
            size_bytes=f.file_size or 0, storage_key=f.storage_key,
            created_at=f.created_at))
    return DatasetOut(
        id=ds.id, company_id=ds.company_id, site_id=ds.site_id, name=ds.name,
        source_tool=ds.source_tool, status=ds.status, sector=ds.sector,
        files=files, file_count=ds.file_count or 0,
        total_size_bytes=sum(f.size_bytes for f in files),
        created_at=ds.created_at, updated_at=ds.updated_at)


# ============ ENDPOINTS ============

@router.post("/", response_model=DatasetOut)
async def create_dataset(
    data: DatasetCreate,
    company_id: str = Query(..., description="Company ID"),
    db: Session = Depends(get_db),
):
    from app.models import Dataset as DSModel
    dataset_id = str(uuid.uuid4())
    ds = DSModel(id=dataset_id, company_id=company_id, site_id=data.site_id,
                 name=data.name, source_tool=data.source_tool.value,
                 status=DatasetStatus.UPLOADING.value, sector=data.sector,
                 metadata_json=json.dumps(data.metadata or {}))
    db.add(ds); db.commit(); db.refresh(ds)
    logger.info(f"Created dataset {dataset_id} for company {company_id}")
    return _ds_out(ds)


@router.get("/", response_model=DatasetListResponse)
async def list_datasets(
    company_id: str = Query(...),
    site_id: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    status: Optional[DatasetStatus] = Query(None),
    source_tool: Optional[SourceTool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    from app.models import Dataset as DSModel
    q = db.query(DSModel).filter(DSModel.company_id == company_id)
    if site_id: q = q.filter(DSModel.site_id == site_id)
    if sector: q = q.filter(DSModel.sector == sector)
    if status: q = q.filter(DSModel.status == status.value)
    if source_tool: q = q.filter(DSModel.source_tool == source_tool.value)
    total = q.count()
    datasets = q.offset((page-1)*per_page).limit(per_page).all()
    return DatasetListResponse(datasets=[_ds_out(d) for d in datasets],
                               total=total, page=page, per_page=per_page)


@router.get("/{dataset_id}", response_model=DatasetOut)
async def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    return _ds_out(ds)


@router.patch("/{dataset_id}", response_model=DatasetOut)
async def update_dataset(dataset_id: str, data: DatasetUpdate, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    if data.name is not None: ds.name = data.name
    if data.status is not None: ds.status = data.status.value
    if data.metadata is not None:
        existing = json.loads(ds.metadata_json or "{}")
        existing.update(data.metadata)
        ds.metadata_json = json.dumps(existing)
    ds.updated_at = datetime.utcnow()
    db.commit(); db.refresh(ds)
    return _ds_out(ds)


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel, DatasetFile as DFModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    storage = get_storage_service()
    for f in ds.files:
        try: storage.delete_file(f.storage_key)
        except Exception as e: logger.warning(f"Failed to delete file {f.storage_key}: {e}")
    db.query(DFModel).filter(DFModel.dataset_id == dataset_id).delete()
    db.delete(ds); db.commit()
    return {"message": "Dataset deleted", "id": dataset_id}


@router.post("/{dataset_id}/upload", response_model=DatasetFileOut)
async def upload_file(dataset_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel, DatasetFile as DFModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    MAX_SIZE = 500 * 1024 * 1024
    content = await file.read()
    if len(content) > MAX_SIZE:
        raise HTTPException(413, f"File too large. Max {MAX_SIZE // (1024*1024)}MB for direct upload.")
    storage = get_storage_service()
    filename = file.filename or f"upload_{dataset_id}"
    storage_key = storage.generate_key(company_id=ds.company_id, site_id=ds.site_id,
                                        dataset_id=dataset_id, filename=filename)
    from io import BytesIO
    key, size_bytes, md5_hash, sha256_hash = storage.upload_bytes(
        data=content, key=storage_key,
        content_type=file.content_type or detect_mime_type(filename),
        metadata={"dataset_id": dataset_id, "original_filename": file.filename, "source_tool": ds.source_tool})
    file_id = str(uuid.uuid4())
    file_type = detect_file_type(filename)
    df = DFModel(id=file_id, dataset_id=dataset_id, filename=filename,
                 storage_key=storage_key, file_size=size_bytes, mime_type=file.content_type)
    db.add(df)
    ds.file_count = len(ds.files) + 1
    if ds.status == DatasetStatus.UPLOADING.value:
        ds.status = DatasetStatus.PROCESSING.value
    ds.updated_at = datetime.utcnow()
    db.commit(); db.refresh(df)
    logger.info(f"Uploaded file {filename} to dataset {dataset_id}")
    return DatasetFileOut(id=df.id, filename=df.filename, file_type=file_type,
                          size_bytes=df.file_size or 0, storage_key=df.storage_key,
                          created_at=df.created_at)


@router.post("/{dataset_id}/presigned-url", response_model=PresignedUrlResponse)
async def get_upload_url(dataset_id: str, request: PresignedUrlRequest, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    storage = get_storage_service()
    storage_key = storage.generate_key(company_id=ds.company_id, site_id=ds.site_id,
                                        dataset_id=dataset_id, filename=request.filename)
    upload_url = storage.get_presigned_url(key=storage_key, expires_in=3600, for_upload=True)
    return PresignedUrlResponse(upload_url=upload_url, storage_key=storage_key, expires_in=3600)


@router.post("/{dataset_id}/confirm-upload")
async def confirm_upload(dataset_id: str, storage_key: str = Form(...),
                          filename: str = Form(...), size_bytes: int = Form(...),
                          db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel, DatasetFile as DFModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    storage = get_storage_service()
    if not storage.file_exists(storage_key):
        raise HTTPException(400, "File not found in storage")
    file_id = str(uuid.uuid4())
    file_type = detect_file_type(filename)
    df = DFModel(id=file_id, dataset_id=dataset_id, filename=filename,
                 storage_key=storage_key, file_size=size_bytes)
    db.add(df); ds.file_count = len(ds.files) + 1; ds.updated_at = datetime.utcnow()
    db.commit(); db.refresh(df)
    return DatasetFileOut(id=df.id, filename=df.filename, file_type=file_type,
                          size_bytes=df.file_size or 0, storage_key=df.storage_key,
                          created_at=df.created_at)


@router.get("/{dataset_id}/files/{file_id}/download")
async def get_download_url(dataset_id: str, file_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel, DatasetFile as DFModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    df = db.get(DFModel, file_id)
    if not df or df.dataset_id != dataset_id: raise HTTPException(404, "File not found")
    storage = get_storage_service()
    download_url = storage.get_presigned_url(key=df.storage_key, expires_in=3600, for_upload=False)
    return {"download_url": download_url, "filename": df.filename, "expires_in": 3600}


@router.delete("/{dataset_id}/files/{file_id}")
async def delete_file(dataset_id: str, file_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel, DatasetFile as DFModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    df = db.get(DFModel, file_id)
    if not df or df.dataset_id != dataset_id: raise HTTPException(404, "File not found")
    storage = get_storage_service()
    storage.delete_file(df.storage_key)
    db.delete(df); ds.file_count = max(0, (ds.file_count or 0) - 1)
    ds.updated_at = datetime.utcnow(); db.commit()
    return {"message": "File deleted", "id": file_id}


@router.post("/{dataset_id}/finalize", response_model=DatasetOut)
async def finalize_dataset(dataset_id: str, db: Session = Depends(get_db)):
    from app.models import Dataset as DSModel
    ds = db.get(DSModel, dataset_id)
    if not ds: raise HTTPException(404, "Dataset not found")
    if not ds.files: raise HTTPException(400, "Dataset has no files")
    ds.status = DatasetStatus.READY.value; ds.updated_at = datetime.utcnow()
    db.commit(); db.refresh(ds)
    logger.info(f"Finalized dataset {dataset_id} with {ds.file_count} files")
    return _ds_out(ds)


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
    
    # FUTURE: Implement per-tool webhook handlers
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
    
    # FUTURE: Implement per-tool API sync
    # - Pix4D Cloud API
    # - DroneDeploy API
    # - BIM 360 API
    
    return {
        "status": "not_implemented",
        "source_tool": source_tool.value,
        "message": f"API sync for {source_tool.value} coming soon. Please use direct upload or webhooks."
    }

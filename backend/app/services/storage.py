"""
Storage Service - S3-Compatible Object Storage

Handles file uploads to S3-compatible storage (AWS S3, MinIO, Cloudflare R2, etc.)
"""
import os
import hashlib
import mimetypes
from datetime import datetime, timedelta
from typing import Optional, BinaryIO, Tuple
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


class StorageService:
    """
    S3-compatible storage service for dataset files.
    """
    
    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET", "geovision-datasets")
        self.endpoint_url = os.getenv("S3_ENDPOINT_URL")  # For MinIO/R2
        self.region = os.getenv("S3_REGION", "eu-west-1")
        
        # Initialize S3 client
        config = Config(
            signature_version='s3v4',
            retries={'max_attempts': 3, 'mode': 'standard'}
        )
        
        client_kwargs = {
            "service_name": "s3",
            "region_name": self.region,
            "config": config,
        }
        
        if self.endpoint_url:
            client_kwargs["endpoint_url"] = self.endpoint_url
        
        # Use env vars for credentials
        aws_key = os.getenv("S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret = os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
        
        if aws_key and aws_secret:
            client_kwargs["aws_access_key_id"] = aws_key
            client_kwargs["aws_secret_access_key"] = aws_secret
        
        self.client = boto3.client(**client_kwargs)
    
    def generate_key(
        self,
        company_id: str,
        site_id: str,
        dataset_id: str,
        filename: str
    ) -> str:
        """Generate S3 key with company/site/dataset hierarchy."""
        # Sanitize filename
        safe_filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        return f"companies/{company_id}/sites/{site_id}/datasets/{dataset_id}/{timestamp}_{safe_filename}"
    
    def upload_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Tuple[str, int, str, str]:
        """
        Upload file to S3.
        
        Returns: (storage_key, size_bytes, md5_hash, sha256_hash)
        """
        # Calculate hashes while reading
        md5_hasher = hashlib.md5()
        sha256_hasher = hashlib.sha256()
        
        # Read file content
        file_obj.seek(0)
        content = file_obj.read()
        size_bytes = len(content)
        
        md5_hasher.update(content)
        sha256_hasher.update(content)
        
        md5_hash = md5_hasher.hexdigest()
        sha256_hash = sha256_hasher.hexdigest()
        
        # Reset file position
        file_obj.seek(0)
        
        # Prepare upload params
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = {k: str(v) for k, v in metadata.items()}
        
        # Upload
        self.client.upload_fileobj(
            file_obj,
            self.bucket,
            key,
            ExtraArgs=extra_args
        )
        
        return key, size_bytes, md5_hash, sha256_hash
    
    def upload_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> Tuple[str, int, str, str]:
        """Upload bytes to S3."""
        from io import BytesIO
        return self.upload_file(BytesIO(data), key, content_type, metadata)
    
    def get_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False
    ) -> str:
        """
        Generate presigned URL for download or upload.
        
        Args:
            key: S3 object key
            expires_in: URL validity in seconds
            for_upload: If True, generate upload URL (PUT), else download (GET)
        """
        method = "put_object" if for_upload else "get_object"
        
        try:
            url = self.client.generate_presigned_url(
                method,
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {e}")
    
    def delete_file(self, key: str) -> bool:
        """Delete file from S3."""
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def file_exists(self, key: str) -> bool:
        """Check if file exists in S3."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
    
    def get_file_info(self, key: str) -> Optional[dict]:
        """Get file metadata from S3."""
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return {
                "size_bytes": response.get("ContentLength"),
                "content_type": response.get("ContentType"),
                "last_modified": response.get("LastModified"),
                "metadata": response.get("Metadata", {}),
            }
        except ClientError:
            return None

    def download_file(self, key: str) -> bytes:
        """Download file content from S3 as bytes."""
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            raise Exception(f"Ficheiro não encontrado no armazenamento: {e}")

    def generate_document_key(
        self, company_id: str, doc_id: str, filename: str
    ) -> str:
        """Generate S3 key for document uploads."""
        safe_name = "".join(
            c for c in filename if c.isalnum() or c in "._- "
        ).strip()
        return f"documents/{company_id}/{doc_id}_{safe_name}"


def is_s3_key(path: Optional[str]) -> bool:
    """Check if a stored path is an S3 key (vs legacy local filesystem path)."""
    return bool(path and not path.startswith("/"))


# Singleton instance
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """Get or create storage service instance."""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


# File type detection helpers
FILE_TYPE_MAP = {
    # Orthomosaics / GeoTIFFs
    ".tif": "geotiff",
    ".tiff": "geotiff",
    # Point clouds
    ".las": "pointcloud_las",
    ".laz": "pointcloud_laz",
    ".e57": "pointcloud_e57",
    ".ply": "pointcloud_ply",
    ".xyz": "pointcloud_ply",
    # 3D Models
    ".obj": "model_obj",
    ".fbx": "model_fbx",
    # GIS
    ".shp": "shapefile",
    ".geojson": "geojson",
    ".json": "geojson",
    ".dxf": "dxf",
    ".dwg": "dwg",
    # Documents
    ".pdf": "pdf",
    ".csv": "csv",
    ".docx": "docx",
    ".doc": "docx",
    # Images
    ".jpg": "image_jpg",
    ".jpeg": "image_jpg",
    ".png": "image_png",
}


def detect_file_type(filename: str) -> str:
    """Detect file type from extension."""
    ext = Path(filename).suffix.lower()
    return FILE_TYPE_MAP.get(ext, "other")


def detect_mime_type(filename: str) -> str:
    """Detect MIME type from filename."""
    mime_type, _ = mimetypes.guess_type(filename)
    return mime_type or "application/octet-stream"

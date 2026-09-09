"""S3-compatible implementation of the datasets object-storage port."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any, BinaryIO, Mapping, Optional

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
)

from app.core.integration import IntegrationUnavailableError
from app.core.integration import (
    IntegrationFailure,
    IntegrationResult,
    IntegrationStatus,
)
from app.modules.datasets.ports import StoredObject


class S3ObjectStorageProvider:
    """Store GeoVision objects in AWS S3 or an S3-compatible service."""

    provider_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        endpoint_url: Optional[str],
        access_key_id: Optional[str],
        secret_access_key: Optional[str],
        retry_attempts: int,
        connect_timeout_seconds: float,
        read_timeout_seconds: float,
        client: Any = None,
    ) -> None:
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region
        if client is not None:
            self.client = client
            return

        client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "region_name": region,
            "config": Config(
                signature_version="s3v4",
                connect_timeout=connect_timeout_seconds,
                read_timeout=read_timeout_seconds,
                retries={"total_max_attempts": retry_attempts, "mode": "standard"},
            ),
        }
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if access_key_id and secret_access_key:
            client_kwargs["aws_access_key_id"] = access_key_id
            client_kwargs["aws_secret_access_key"] = secret_access_key
        try:
            self.client = boto3.client(**client_kwargs)
        except Exception as exc:
            raise IntegrationUnavailableError(
                provider=self.provider_name,
                operation="initialize",
                message="object-storage client initialization failed",
            ) from exc

    def _failed(self, operation: str, error: Exception) -> IntegrationResult[Any]:
        code = "storage_unavailable"
        message = "object-storage request failed"
        retryable = True
        status = IntegrationStatus.RETRYING
        if isinstance(error, ClientError):
            provider_code = str(error.response.get("Error", {}).get("Code", ""))
            if provider_code in {
                "AccessDenied",
                "ExpiredToken",
                "InvalidAccessKeyId",
                "InvalidToken",
                "SignatureDoesNotMatch",
            }:
                code = "storage_authentication_failed"
                message = "object-storage authentication failed"
                retryable = False
                status = IntegrationStatus.FAILED
            elif provider_code in {
                "InvalidBucketName",
                "NoSuchBucket",
                "PermanentRedirect",
            }:
                code = "storage_not_configured"
                message = "object-storage bucket configuration is invalid"
                retryable = False
                status = IntegrationStatus.NOT_CONFIGURED
            elif provider_code in {"404", "NoSuchKey", "NotFound"}:
                code = "storage_not_found"
                message = "object-storage object was not found"
                retryable = False
                status = IntegrationStatus.FAILED
            elif provider_code not in {
                "500",
                "503",
                "InternalError",
                "RequestTimeout",
                "ServiceUnavailable",
                "SlowDown",
                "Throttling",
            }:
                code = "storage_invalid_request"
                message = "object-storage rejected the request"
                retryable = False
                status = IntegrationStatus.FAILED
        elif isinstance(error, (NoCredentialsError, PartialCredentialsError)):
            code = "storage_not_configured"
            message = "object-storage credentials are not configured"
            retryable = False
            status = IntegrationStatus.NOT_CONFIGURED
        elif isinstance(error, ParamValidationError):
            code = "storage_invalid_request"
            message = "object-storage rejected the request"
            retryable = False
            status = IntegrationStatus.FAILED
        elif not isinstance(error, (BotoCoreError, S3UploadFailedError)):
            code = "storage_error"
            message = "object-storage operation failed unexpectedly"
            retryable = False
            status = IntegrationStatus.FAILED
        return IntegrationResult.failed(
            provider=self.provider_name,
            operation=operation,
            status=status,
            failure=IntegrationFailure(
                code=code,
                message=message,
                retryable=retryable,
            ),
        )

    def put_file(
        self,
        file_obj: BinaryIO,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        file_obj.seek(0)
        content = file_obj.read()
        stored = StoredObject(
            key=key,
            size_bytes=len(content),
            md5_hash=hashlib.md5(content).hexdigest(),
            sha256_hash=hashlib.sha256(content).hexdigest(),
        )
        file_obj.seek(0)

        extra_args: dict[str, Any] = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = {name: str(value) for name, value in metadata.items()}
        try:
            self.client.upload_fileobj(
                file_obj,
                self.bucket,
                key,
                ExtraArgs=extra_args,
            )
        except Exception as exc:
            return self._failed("put_file", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="put_file",
            value=stored,
        )

    def put_bytes(
        self,
        data: bytes,
        key: str,
        content_type: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> IntegrationResult[StoredObject]:
        return self.put_file(BytesIO(data), key, content_type, metadata)

    def presign(
        self,
        key: str,
        expires_in: int = 3600,
        for_upload: bool = False,
    ) -> IntegrationResult[str]:
        method = "put_object" if for_upload else "get_object"
        try:
            url = self.client.generate_presigned_url(
                method,
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            return self._failed("presign", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="presign",
            value=url,
        )

    def delete(self, key: str) -> IntegrationResult[bool]:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            return self._failed("delete", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="delete",
            value=True,
        )

    def exists(self, key: str) -> IntegrationResult[bool]:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            exists = True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                exists = False
            else:
                return self._failed("exists", exc)
        except Exception as exc:
            return self._failed("exists", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="exists",
            value=exists,
        )

    def stat(self, key: str) -> IntegrationResult[Optional[Mapping[str, Any]]]:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            value: Optional[Mapping[str, Any]] = {
                "size_bytes": response.get("ContentLength"),
                "content_type": response.get("ContentType"),
                "last_modified": response.get("LastModified"),
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                value = None
            else:
                return self._failed("stat", exc)
        except Exception as exc:
            return self._failed("stat", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="stat",
            value=value,
        )

    def get_bytes(self, key: str) -> IntegrationResult[bytes]:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            value = response["Body"].read()
        except Exception as exc:
            return self._failed("get_bytes", exc)
        return IntegrationResult.succeeded(
            provider=self.provider_name,
            operation="get_bytes",
            value=value,
        )


__all__ = ["S3ObjectStorageProvider"]

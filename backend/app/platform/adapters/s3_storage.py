"""S3-compatible StoragePort adapter (preview MinIO, cloud S3, private S3).

Private by design: the bucket is never public, objects are addressed by key
(server-side), and reads go through expiring presigned URLs — never raw paths
or public bucket URLs. Tenant/object ownership checks stay in the domain
layer; this adapter only enforces key hygiene (no traversal, no absolute
paths), mirroring LocalStorageAdapter.

boto3 is imported lazily so unit tests and dev boot never pay for it unless
STORAGE_ADAPTER=s3 is selected.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.platform.config import Settings
from app.platform.ports.ports import StoredObjectMeta


def _check_key(key: str) -> None:
    if not key or ".." in key or key.startswith("/") or key.startswith("\\"):
        raise ValueError("invalid storage key")


class S3StorageAdapter:
    """StoragePort over an S3-compatible endpoint (MinIO or AWS S3)."""

    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        if settings.STORAGE_ADAPTER != "s3":
            raise RuntimeError("S3StorageAdapter selected but STORAGE_ADAPTER != s3")
        for var in ("S3_ENDPOINT_URL", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
            if not getattr(settings, var):
                # Name the variable, never the value.
                raise RuntimeError(f"{var} is required for STORAGE_ADAPTER=s3")
        self._bucket = settings.S3_BUCKET
        self._client = client or self._build_client(settings)
        if settings.S3_ENSURE_BUCKET:
            self._ensure_bucket()

    @staticmethod
    def _build_client(settings: Settings) -> Any:
        import boto3  # type: ignore[import-untyped]  # lazy: only for STORAGE_ADAPTER=s3

        session = boto3.session.Session()
        return session.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL or None,
            region_name=settings.S3_REGION,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            use_ssl=settings.S3_USE_TLS,
        )

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception as exc:  # noqa: BLE001 — missing bucket is the expected case
            if "404" not in str(exc) and "NoSuchBucket" not in str(exc):
                raise
            self._client.create_bucket(Bucket=self._bucket)

    def put(self, *, key: str, data: bytes, content_type: str) -> StoredObjectMeta:
        _check_key(key)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)
        return StoredObjectMeta(
            key=key,
            size_bytes=len(data),
            content_type=content_type,
            sha256=hashlib.sha256(data).hexdigest(),
        )

    def get(self, *, key: str) -> bytes:
        _check_key(key)
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        body = resp["Body"]
        return body.read() if hasattr(body, "read") else bytes(body)

    def exists(self, *, key: str) -> bool:
        _check_key(key)
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 — absence is a normal outcome
            return False

    def delete(self, *, key: str) -> None:
        _check_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def signed_access(self, *, key: str, expires_seconds: int) -> str:
        """Expiring, unguessable capability URL. Never a raw path."""
        _check_key(key)
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_seconds,
            )
        )


def build_storage_adapter(settings: Settings) -> Any:
    """Select the configured StoragePort adapter. Single selection point —
    domain code never branches on deployment."""
    if settings.STORAGE_ADAPTER == "s3":
        return S3StorageAdapter(settings)
    if settings.STORAGE_ADAPTER == "local":
        from app.platform.adapters.dev_adapters import LocalStorageAdapter

        return LocalStorageAdapter(
            root=settings.STORAGE_LOCAL_ROOT, signing_secret=settings.JWT_SECRET
        )
    raise RuntimeError("STORAGE_ADAPTER must be one of ['local', 's3']")

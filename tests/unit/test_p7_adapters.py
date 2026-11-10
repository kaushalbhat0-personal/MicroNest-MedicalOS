"""P7 adapter selection: S3 storage (fake client) and notify providers."""

import pytest

from app.platform.adapters.notify import NullNotifyAdapter, build_notify_adapter
from app.platform.adapters.s3_storage import S3StorageAdapter, build_storage_adapter
from app.platform.config import Settings
from app.platform.ports.ports import NotifyRequest

LONG_SECRET = "test-only-secret-min-32-chars-xxxxxxxx"


class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.buckets: set[str] = set()

    def head_bucket(self, *, Bucket: str) -> None:
        if Bucket not in self.buckets:
            raise RuntimeError("404 NoSuchBucket")

    def create_bucket(self, *, Bucket: str) -> None:
        self.buckets.add(Bucket)

    def put_object(
        self, *, Bucket: str, Key: str, Body: bytes, ContentType: str
    ) -> None:
        self.objects[(Bucket, Key)] = (bytes(Body), ContentType)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        data, _ = self.objects[(Bucket, Key)]

        class _Body:
            def read(self) -> bytes:
                return data

        return {"Body": _Body()}

    def head_object(self, *, Bucket: str, Key: str) -> None:
        if (Bucket, Key) not in self.objects:
            raise RuntimeError("404 Not Found")

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop((Bucket, Key), None)

    def generate_presigned_url(
        self, op: str, *, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        return f"https://s3.example/{Params['Bucket']}/{Params['Key']}?exp={ExpiresIn}"


def _s3_settings(**overrides):  # type: ignore[no-untyped-def]
    kwargs = {
        "ENV": "preview",
        "DEPLOYMENT": "cloud",
        "JWT_SECRET": LONG_SECRET,
        "DEV_NOTIFICATIONS_ALLOW": False,
        "NOTIFY_PROVIDER": "none",
        "STORAGE_ADAPTER": "s3",
        "S3_ENDPOINT_URL": "https://s3.example.com",
        "S3_REGION": "us-east-1",
        "S3_BUCKET": "hos-preview",
        "S3_ACCESS_KEY": "ak",
        "S3_SECRET_KEY": "sk",
        "S3_ENSURE_BUCKET": False,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


def _adapter(**overrides):  # type: ignore[no-untyped-def]
    fake = FakeS3Client()
    fake.buckets.add("hos-preview")
    return S3StorageAdapter(_s3_settings(**overrides), client=fake), fake


def test_s3_roundtrip() -> None:
    adapter, _ = _adapter()
    meta = adapter.put(key="t1/doc.pdf", data=b"bytes", content_type="application/pdf")
    assert meta.size_bytes == 5
    assert adapter.exists(key="t1/doc.pdf")
    assert adapter.get(key="t1/doc.pdf") == b"bytes"
    adapter.delete(key="t1/doc.pdf")
    assert not adapter.exists(key="t1/doc.pdf")


def test_s3_signed_access_is_expiring_reference() -> None:
    adapter, _ = _adapter()
    ref = adapter.signed_access(key="t1/doc.pdf", expires_seconds=300)
    assert "t1/doc.pdf" not in ref.split("?")[0] or "exp=" in ref
    assert "exp=300" in ref


def test_s3_rejects_traversal_keys() -> None:
    adapter, _ = _adapter()
    for bad in ("../escape", "/absolute", "", "..\\win"):
        with pytest.raises(ValueError, match="invalid storage key"):
            adapter.put(key=bad, data=b"x", content_type="text/plain")


def test_s3_requires_configuration() -> None:
    with pytest.raises(RuntimeError, match="S3_BUCKET"):
        S3StorageAdapter(_s3_settings(S3_BUCKET=""), client=FakeS3Client())


def test_s3_ensure_bucket_creates_missing_bucket() -> None:
    fake = FakeS3Client()
    S3StorageAdapter(_s3_settings(S3_ENSURE_BUCKET=True), client=fake)
    assert "hos-preview" in fake.buckets


def test_s3_refuses_wrong_adapter_selection() -> None:
    settings = Settings(ENV="dev", JWT_SECRET=LONG_SECRET, STORAGE_ADAPTER="local")
    with pytest.raises(RuntimeError, match="STORAGE_ADAPTER != s3"):
        S3StorageAdapter(settings, client=FakeS3Client())


def test_build_storage_adapter_selects_local() -> None:
    from app.platform.adapters.dev_adapters import LocalStorageAdapter

    settings = Settings(ENV="dev", JWT_SECRET=LONG_SECRET, STORAGE_ADAPTER="local")
    assert isinstance(build_storage_adapter(settings), LocalStorageAdapter)


def test_null_notify_is_honest_and_fail_closed() -> None:
    adapter = NullNotifyAdapter()
    assert adapter.health() is False
    req = NotifyRequest(
        channel="email", to_ref="user", template="t", locale="en", context_refs={}
    )
    with pytest.raises(RuntimeError, match="not configured"):
        adapter.send(req)


def test_build_notify_adapter_selection() -> None:
    from app.platform.adapters.dev_adapters import DevNotifyAdapter

    dev = Settings(
        ENV="dev",
        JWT_SECRET=LONG_SECRET,
        DEV_NOTIFICATIONS_ALLOW=True,
        NOTIFY_PROVIDER="dev-console",
    )
    assert isinstance(build_notify_adapter(dev), DevNotifyAdapter)
    none = Settings(ENV="dev", JWT_SECRET=LONG_SECRET, NOTIFY_PROVIDER="none")
    assert isinstance(build_notify_adapter(none), NullNotifyAdapter)
    bad = Settings(ENV="dev", JWT_SECRET=LONG_SECRET, NOTIFY_PROVIDER="none")
    object.__setattr__(bad, "NOTIFY_PROVIDER", "pigeon")
    with pytest.raises(RuntimeError, match="NOTIFY_PROVIDER"):
        build_notify_adapter(bad)

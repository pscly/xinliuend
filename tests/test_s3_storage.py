from __future__ import annotations

from typing import Any

import pytest

from flow_backend.integrations.storage.s3_storage import S3ObjectStorage


class _FakeBody:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        self.put_calls.append(dict(kwargs))

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.get_calls.append({"Bucket": Bucket, "Key": Key})
        return {"Body": _FakeBody(b"hello")}

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.delete_calls.append({"Bucket": Bucket, "Key": Key})


@pytest.mark.anyio
async def test_s3_object_storage_put_get_delete(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeS3Client()
    boto3_calls: list[dict[str, Any]] = []

    import boto3

    def _fake_client(service_name: str, **kwargs: Any):
        boto3_calls.append({"service_name": service_name, **kwargs})
        return fake

    async def _run_inline(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return fn()

    monkeypatch.setattr(boto3, "client", _fake_client)
    monkeypatch.setattr(
        "flow_backend.integrations.storage.s3_storage.run_in_threadpool", _run_inline
    )

    s = S3ObjectStorage(
        endpoint_url="http://localhost:9000",
        region="",
        bucket="bucket",
        access_key_id="ak",
        secret_access_key="sk",
        force_path_style=True,
    )
    assert boto3_calls and boto3_calls[0]["service_name"] == "s3"

    await s.put_bytes("k1", b"data")
    await s.put_bytes("k2", b"data2", content_type="text/plain")
    out = await s.get_bytes("k3")
    await s.delete("k4")

    assert out == b"hello"

    assert fake.put_calls[0]["Bucket"] == "bucket"
    assert fake.put_calls[0]["Key"] == "k1"
    assert "ContentType" not in fake.put_calls[0]

    assert fake.put_calls[1]["Key"] == "k2"
    assert fake.put_calls[1]["ContentType"] == "text/plain"

    assert fake.get_calls == [{"Bucket": "bucket", "Key": "k3"}]
    assert fake.delete_calls == [{"Bucket": "bucket", "Key": "k4"}]


@pytest.mark.anyio
async def test_s3_object_storage_virtual_host_style(monkeypatch: pytest.MonkeyPatch):
    # Only asserts init does not raise when using virtual-host style.
    fake = _FakeS3Client()

    import boto3

    def _fake_client(service_name: str, **kwargs: Any):
        _ = kwargs
        assert service_name == "s3"
        return fake

    async def _run_inline(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        _ = args, kwargs
        return fn()

    monkeypatch.setattr(boto3, "client", _fake_client)
    monkeypatch.setattr(
        "flow_backend.integrations.storage.s3_storage.run_in_threadpool", _run_inline
    )

    s = S3ObjectStorage(
        endpoint_url="http://localhost:9000",
        region="us-east-1",
        bucket="bucket",
        access_key_id="ak",
        secret_access_key="sk",
        force_path_style=False,
    )
    await s.delete("k")

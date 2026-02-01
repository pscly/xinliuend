from __future__ import annotations

from typing import Protocol

from flow_backend.config import settings


class ObjectStorage(Protocol):
    async def put_bytes(
        self, key: str, data: bytes, *, content_type: str | None = None
    ) -> None: ...

    async def get_bytes(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


def build_attachment_storage_key(*, user_id: int, attachment_id: str) -> str:
    # Pinned local layout: ${ATTACHMENTS_LOCAL_DIR}/{user_id}/{attachment_id}
    # The same key works for S3 providers.
    return f"{user_id}/{attachment_id}"


def get_object_storage() -> ObjectStorage:
    # Default to local storage when S3 config is incomplete.
    if (
        settings.s3_bucket.strip()
        and settings.s3_endpoint_url.strip()
        and settings.s3_access_key_id.strip()
        and settings.s3_secret_access_key.strip()
    ):
        from .s3_storage import S3ObjectStorage

        return S3ObjectStorage(
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            bucket=settings.s3_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            force_path_style=settings.s3_force_path_style,
        )

    from .local_storage import LocalObjectStorage

    return LocalObjectStorage(root_dir=settings.attachments_local_dir)

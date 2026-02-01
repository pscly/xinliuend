from __future__ import annotations

from dataclasses import dataclass

from botocore.config import Config
from starlette.concurrency import run_in_threadpool


@dataclass(frozen=True)
class S3Config:
    endpoint_url: str
    region: str
    bucket: str
    access_key_id: str
    secret_access_key: str
    force_path_style: bool


class S3ObjectStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        force_path_style: bool,
    ) -> None:
        self._cfg = S3Config(
            endpoint_url=endpoint_url,
            region=region,
            bucket=bucket,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            force_path_style=force_path_style,
        )

        import boto3

        addressing_style = "path" if force_path_style else "virtual"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region or None,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(s3={"addressing_style": addressing_style}),
        )

    async def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        def _put() -> None:
            kwargs: dict[str, object] = {
                "Bucket": self._cfg.bucket,
                "Key": key,
                "Body": data,
            }
            if content_type:
                kwargs["ContentType"] = content_type
            self._client.put_object(**kwargs)

        await run_in_threadpool(_put)

    async def get_bytes(self, key: str) -> bytes:
        def _get() -> bytes:
            resp = self._client.get_object(Bucket=self._cfg.bucket, Key=key)
            body = resp.get("Body")
            # StreamingBody.read() is blocking; run in threadpool.
            return body.read() if body is not None else b""

        return await run_in_threadpool(_get)

    async def delete(self, key: str) -> None:
        def _delete() -> None:
            self._client.delete_object(Bucket=self._cfg.bucket, Key=key)

        await run_in_threadpool(_delete)

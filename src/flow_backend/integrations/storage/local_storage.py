from __future__ import annotations

from pathlib import Path, PurePosixPath

from starlette.concurrency import run_in_threadpool


def _safe_join(root: Path, key: str) -> Path:
    parts = [p for p in PurePosixPath(key).parts if p not in {"/", ""}]
    if any(p in {"..", "."} for p in parts):
        raise ValueError("invalid storage key")
    return root.joinpath(*parts)


class LocalObjectStorage:
    def __init__(self, *, root_dir: str) -> None:
        self._root = Path(root_dir)

    def resolve_path(self, key: str) -> Path:
        return _safe_join(self._root, key)

    async def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        _ = content_type
        path = self.resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(path.name + ".tmp")

        def _write() -> None:
            _ = tmp_path.write_bytes(data)
            _ = tmp_path.replace(path)

        await run_in_threadpool(_write)

    async def get_bytes(self, key: str) -> bytes:
        path = self.resolve_path(key)
        return await run_in_threadpool(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self.resolve_path(key)
        if not path.exists():
            return
        await run_in_threadpool(path.unlink)

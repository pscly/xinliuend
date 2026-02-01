from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator

import pytest

from flow_backend.db import dispose_engine_cache, get_engine


@pytest.fixture(autouse=True)
async def _dispose_engine_cache_per_test(  # pyright: ignore[reportUnusedFunction]
    anyio_backend: object,  # noqa: ARG001
) -> AsyncGenerator[None, None]:
    # Ensure the cached AsyncEngine (aiosqlite worker thread) is disposed
    # before the per-test anyio/asyncio event loop is torn down on Windows.
    _ = anyio_backend
    yield

    # Prefer the async engine disposal so sqlite worker threads get shut down
    # while the event loop is still alive (Windows + anyio can otherwise warn).
    try:
        engine = get_engine()
    except Exception:
        engine = None

    if engine is not None:
        try:
            result = engine.dispose()
            if inspect.isawaitable(result):
                await result
        except Exception:
            # Best-effort: fall back to sync pool dispose below.
            pass

    dispose_engine_cache()

    # Clear cached engine so the next test doesn't reuse a half-closed engine.
    get_engine.cache_clear()


def pytest_sessionfinish(session: object, exitstatus: int) -> None:  # noqa: ARG001
    # Safety net: close cached engine so CI can exit cleanly.
    _ = session, exitstatus
    dispose_engine_cache()

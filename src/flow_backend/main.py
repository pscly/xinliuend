from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from flow_backend.config import settings  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.db import dispose_engine_cache  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.db import session_scope
from flow_backend.device_tracking import extract_device_id_name, record_device_activity
from flow_backend.routers import (  # pyright: ignore[reportMissingTypeStubs]
    admin,
    auth,
    settings as settings_router,
    sync as sync_router,
    todo,
)
from flow_backend.v2.app import v2_app  # pyright: ignore[reportMissingTypeStubs]


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app: ASGIApp = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        request_id_header: bytes | None = None
        inbound_headers = cast(list[tuple[bytes, bytes]], scope.get("headers") or [])
        for key, value in inbound_headers:
            if key.lower() == b"x-request-id":
                value = value.strip()
                if value:
                    request_id_header = value
                break

        if request_id_header is None:
            request_id = str(uuid.uuid4())
            request_id_header = request_id.encode("ascii")
        else:
            # latin-1 is a 1-1 mapping for bytes -> str.
            request_id = request_id_header.decode("latin-1")

        scope.setdefault("state", {})["request_id"] = request_id

        async def send_wrapper(message: Message) -> None:
            if message.get("type") == "http.response.start":
                headers = cast(list[tuple[bytes, bytes]], message.get("headers", []))
                headers = [(k, v) for (k, v) in headers if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id_header))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    # Ensure sqlite/aiosqlite worker threads don't keep the process alive.
    dispose_engine_cache()


app = FastAPI(title=settings.app_name, lifespan=_lifespan)

app.add_middleware(RequestIdMiddleware)


logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))

logger = logging.getLogger(__name__)
for msg in settings.security_warnings():
    logger.warning("SECURITY WARNING: %s", msg)


async def _persist_device_tracking_best_effort(request: Request, user_id: int) -> None:
    request_id = getattr(request.state, "request_id", None)
    try:
        async with session_scope() as tracking_session:
            await record_device_activity(session=tracking_session, user_id=user_id, request=request)
            await tracking_session.commit()
    except Exception:
        logger.warning("device tracking failed request_id=%s", request_id, exc_info=True)


@app.middleware("http")
async def device_tracking_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)

    user_id = getattr(request.state, "auth_user_id", None)
    if not isinstance(user_id, int):
        return response

    device_id, _device_name = extract_device_id_name(request)
    if not device_id:
        return response

    if settings.device_tracking_async:
        task = BackgroundTask(_persist_device_tracking_best_effort, request, user_id)
        existing = response.background
        if existing is None:
            response.background = task
        elif isinstance(existing, BackgroundTasks):
            _ = existing.add_task(_persist_device_tracking_best_effort, request, user_id)
        else:
            tasks = BackgroundTasks()
            _ = tasks.add_task(existing)
            _ = tasks.add_task(_persist_device_tracking_best_effort, request, user_id)
            response.background = tasks
        return response

    # Tests can force inline execution to avoid background timing issues.
    await _persist_device_tracking_best_effort(request, user_id)
    return response


origins = settings.cors_origins_list()
if origins == ["*"]:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        # Bearer-token auth; no cross-site cookies needed.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    return {"ok": True}


# Mounted API v2 sub-app (separate OpenAPI schema).
app.mount("/api/v2", v2_app)


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(settings_router.router, prefix=settings.api_prefix)
app.include_router(todo.router, prefix=settings.api_prefix)
app.include_router(sync_router.router, prefix=settings.api_prefix)
app.include_router(admin.router)

from __future__ import annotations

import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from starlette.background import BackgroundTask, BackgroundTasks
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from flow_backend.config import settings  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.db import dispose_engine_cache  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.db import session_scope
from flow_backend.device_tracking import extract_device_id_name, record_device_activity
from flow_backend.routers import (  # pyright: ignore[reportMissingTypeStubs]
    admin,
    auth,
    me,
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
        # For cookie auth across origins, set an explicit allowlist in CORS_ALLOW_ORIGINS
        # (no '*') so we can safely enable allow_credentials.
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
elif origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        # Explicit origins -> allow cookies cross-origin for SPA session auth.
        allow_credentials=settings.cors_allow_credentials(),
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/health")
def health():
    return {"ok": True}


# Mounted API v2 sub-app (separate OpenAPI schema).
app.mount("/api/v2", v2_app)


app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(me.router, prefix=settings.api_prefix)
app.include_router(settings_router.router, prefix=settings.api_prefix)
app.include_router(todo.router, prefix=settings.api_prefix)
app.include_router(sync_router.router, prefix=settings.api_prefix)
app.include_router(admin.router, include_in_schema=False)


@app.api_route(
    f"{settings.api_prefix.rstrip('/')}/{{path:path}}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def _v1_fallback_not_found(path: str) -> None:  # noqa: ARG001
    # Without this, a frontend SPA/static mount at `/` would catch unknown
    # `/api/v1/*` paths and return HTML instead of FastAPI's default JSON 404.
    raise HTTPException(status_code=404, detail="Not Found")


def _try_mount_exported_web_ui(_app: FastAPI) -> None:
    """Best-effort mount for `web/out` (Next static export).

    Goals:
    - Same-origin web + API (cookie auth works without CORS complexity)
    - Preserve routing precedence: `/api/*` and `/admin` must win

    This mount is intentionally optional: if the export output is missing, the
    backend still runs as an API-only service.
    """

    if os.getenv("FLOW_DISABLE_WEB_STATIC") == "1":
        return

    out_dir_env = os.getenv("FLOW_WEB_OUT_DIR")
    if out_dir_env:
        out_dir = Path(out_dir_env)
    else:
        # `src/flow_backend/main.py` -> repo root -> `web/out`
        out_dir = Path(__file__).resolve().parents[2] / "web" / "out"

    index_html = out_dir / "index.html"
    if not out_dir.is_dir() or not index_html.is_file():
        return

    logger.info("mounting exported web UI: %s", out_dir)
    _app.mount("/", StaticFiles(directory=str(out_dir), html=True, check_dir=False), name="web")


_try_mount_exported_web_ui(app)


def _openapi_schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _ensure_components_schema(schema: dict[str, object], *, name: str, model) -> None:  # type: ignore[no-untyped-def]
    components = cast(dict[str, object], schema.setdefault("components", {}))
    schemas = cast(dict[str, object], components.setdefault("schemas", {}))
    if name in schemas:
        return
    schemas[name] = model.model_json_schema(ref_template="#/components/schemas/{model}")


def _patch_main_openapi(schema: dict[str, object]) -> dict[str, object]:
    # v1 response envelope.
    from flow_backend.schemas import ApiResponse  # pyright: ignore[reportMissingTypeStubs]

    _ensure_components_schema(schema, name="ApiResponse", model=ApiResponse)

    api_prefix = settings.api_prefix.rstrip("/")
    paths = cast(dict[str, object], schema.get("paths") or {})

    for _path, path_item_obj in paths.items():
        if not isinstance(path_item_obj, dict):
            continue
        path_item = cast(dict[str, object], path_item_obj)

        for method in ("get", "post", "put", "patch", "delete"):
            op_obj = path_item.get(method)
            if not isinstance(op_obj, dict):
                continue
            op = cast(dict[str, object], op_obj)
            responses = cast(dict[str, object], op.setdefault("responses", {}))

            # Document X-Request-Id response header (added by middleware).
            for resp_obj in responses.values():
                if not isinstance(resp_obj, dict):
                    continue
                headers = cast(dict[str, object], resp_obj.setdefault("headers", {}))
                headers.setdefault(
                    "X-Request-Id",
                    {
                        "schema": {"type": "string"},
                        "description": "Echoed or generated request id.",
                    },
                )

            # Document optional inbound request id header.
            # The middleware accepts X-Request-Id from clients (or generates one if absent).
            params_obj = op.setdefault("parameters", [])
            if isinstance(params_obj, list):
                params = cast(list[object], params_obj)
                has_x_request_id = False
                for param_obj in params:
                    if not isinstance(param_obj, dict):
                        continue
                    ref = param_obj.get("$ref")
                    if isinstance(ref, str) and "x-request-id" in ref.lower():
                        has_x_request_id = True
                        break
                    name = param_obj.get("name")
                    location = param_obj.get("in")
                    if (
                        isinstance(name, str)
                        and isinstance(location, str)
                        and location == "header"
                        and name.lower() == "x-request-id"
                    ):
                        has_x_request_id = True
                        break
                if not has_x_request_id:
                    params.append(
                        {
                            "name": "X-Request-Id",
                            "in": "header",
                            "required": False,
                            "schema": {"type": "string"},
                            "description": "Optional client-provided request id; echoed back in responses.",
                        }
                    )

            # Only patch v1 API responses (keep /health and other non-v1 endpoints unchanged).
            if not _path.startswith(api_prefix + "/"):
                continue

            # v1 endpoints return {code, data} envelope; reflect that in 200 schema.
            resp_200 = cast(dict[str, object], responses.setdefault("200", {"description": "OK"}))
            content = cast(dict[str, object], resp_200.setdefault("content", {}))
            app_json = cast(dict[str, object], content.setdefault("application/json", {}))
            app_json["schema"] = _openapi_schema_ref("ApiResponse")

            # Auth endpoints are rate-limited and can return 429 with Retry-After.
            if _path in {f"{api_prefix}/auth/login", f"{api_prefix}/auth/register"}:
                resp_429 = cast(
                    dict[str, object],
                    responses.setdefault(
                        "429",
                        {
                            "description": "Too Many Requests",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {"detail": {"type": "string"}},
                                        "required": ["detail"],
                                    }
                                }
                            },
                        },
                    ),
                )
                headers = cast(dict[str, object], resp_429.setdefault("headers", {}))
                headers.setdefault(
                    "Retry-After",
                    {
                        "schema": {"type": "string"},
                        "description": "Seconds to wait before retrying.",
                    },
                )
                headers.setdefault(
                    "X-Request-Id",
                    {
                        "schema": {"type": "string"},
                        "description": "Echoed or generated request id.",
                    },
                )

    return schema


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return cast(dict[str, object], app.openapi_schema)

    schema = cast(
        dict[str, object],
        get_openapi(
            title=app.title,
            version=cast(str, app.version) if app.version else "0.1.0",
            routes=app.routes,
        ),
    )
    app.openapi_schema = _patch_main_openapi(schema)
    return cast(dict[str, object], app.openapi_schema)


app.openapi = custom_openapi  # type: ignore[method-assign]

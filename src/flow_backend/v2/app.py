from __future__ import annotations

# These handlers are registered via `add_exception_handler` (v2-only).

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from flow_backend.config import settings
from flow_backend.v2.routers.attachments import router as attachments_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.health import router as health_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.notes import router as notes_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.public import router as public_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.revisions import router as revisions_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.shares import router as shares_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.sync import router as sync_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.routers.todo import router as todo_router  # pyright: ignore[reportMissingTypeStubs]
from flow_backend.v2.schemas.errors import ErrorResponse  # pyright: ignore[reportMissingTypeStubs]

v2_app = FastAPI(title="Flow Backend v2")

logger = logging.getLogger(__name__)


def _map_http_status_to_error(status_code: int) -> str:
    mapping: dict[int, str] = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "gone",
        429: "rate_limited",
        502: "upstream_error",
    }
    return mapping.get(status_code, f"http_{status_code}")


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # v2-only unified error shape; v1 retains FastAPI defaults.
    http_exc = cast(StarletteHTTPException, exc)

    details: object | None = None
    message = str(http_exc.detail)
    if isinstance(http_exc.detail, dict):
        # Convention: {'message': str, 'details': object}
        msg = http_exc.detail.get("message")
        if isinstance(msg, str):
            message = msg
            details = http_exc.detail.get("details")
        else:
            details = http_exc.detail
    elif isinstance(http_exc.detail, list):
        details = http_exc.detail

    payload = ErrorResponse(
        error=_map_http_status_to_error(http_exc.status_code),
        message=message,
        request_id=getattr(request.state, "request_id", None),
        details=details,
    )
    return JSONResponse(
        status_code=http_exc.status_code,
        content=jsonable_encoder(payload, exclude_none=True),
    )


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    validation_exc = cast(RequestValidationError, exc)
    payload = ErrorResponse(
        error="validation_error",
        message="Request validation error",
        request_id=getattr(request.state, "request_id", None),
        details=validation_exc.errors(),
    )
    return JSONResponse(status_code=422, content=jsonable_encoder(payload, exclude_none=True))


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    # Log with request context; response stays generic for clients.
    logger.exception(
        "unhandled exception request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
        exc_info=exc,
    )
    payload = ErrorResponse(
        error="internal_error",
        message="Internal server error",
        request_id=request_id,
    )
    return JSONResponse(status_code=500, content=jsonable_encoder(payload, exclude_none=True))


# Register v2-only exception handlers (do not affect /api/v1).
v2_app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
v2_app.add_exception_handler(RequestValidationError, _validation_exception_handler)
v2_app.add_exception_handler(Exception, _unhandled_exception_handler)


v2_app.include_router(health_router)
v2_app.include_router(notes_router)
v2_app.include_router(attachments_router)
v2_app.include_router(shares_router)
v2_app.include_router(public_router)
v2_app.include_router(revisions_router)
v2_app.include_router(todo_router)
v2_app.include_router(sync_router)

if settings.environment.lower() != "production":
    from flow_backend.v2.routers.debug import router as debug_router  # pyright: ignore[reportMissingTypeStubs]

    v2_app.include_router(debug_router)

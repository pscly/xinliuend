from __future__ import annotations

# These handlers are registered via `add_exception_handler` (v2-only).

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
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

    # Debug endpoints are internal-only; keep them out of OpenAPI.
    v2_app.include_router(debug_router, include_in_schema=False)


def _openapi_schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _ensure_components_schema(schema: dict[str, object], *, name: str, model) -> None:  # type: ignore[no-untyped-def]
    components = cast(dict[str, object], schema.setdefault("components", {}))
    schemas = cast(dict[str, object], components.setdefault("schemas", {}))
    if name in schemas:
        return
    # Pydantic v2 generates JSON Schema compatible with OpenAPI 3.1.
    schemas[name] = model.model_json_schema(ref_template="#/components/schemas/{model}")


def _patch_v2_openapi(schema: dict[str, object]) -> dict[str, object]:
    # v2 is mounted at /api/v2. Add a server entry so imported clients work.
    schema["servers"] = [{"url": "/api/v2"}]

    # Pin v2 error model in schema components.
    _ensure_components_schema(schema, name="ErrorResponse", model=ErrorResponse)

    paths = cast(dict[str, object], schema.get("paths") or {})
    for path, path_item_obj in paths.items():
        if not isinstance(path_item_obj, dict):
            continue

        path_item = cast(dict[str, object], path_item_obj)
        for method in ("get", "post", "put", "patch", "delete"):
            op_obj = path_item.get(method)
            if not isinstance(op_obj, dict):
                continue

            op = cast(dict[str, object], op_obj)
            responses = cast(dict[str, object], op.setdefault("responses", {}))

            # FastAPI default OpenAPI documents 422 as HTTPValidationError.
            # Runtime v2 returns ErrorResponse for validation errors.
            responses["422"] = {
                "description": "Validation Error",
                "content": {"application/json": {"schema": _openapi_schema_ref("ErrorResponse")}},
            }

            auth_required = bool(op.get("security"))

            # Common error responses (runtime always returns ErrorResponse for these).
            if auth_required:
                responses.setdefault(
                    "401",
                    {
                        "description": "Unauthorized",
                        "content": {
                            "application/json": {"schema": _openapi_schema_ref("ErrorResponse")}
                        },
                    },
                )
                responses.setdefault(
                    "403",
                    {
                        "description": "Forbidden",
                        "content": {
                            "application/json": {"schema": _openapi_schema_ref("ErrorResponse")}
                        },
                    },
                )

            for code, desc in (
                ("400", "Bad Request"),
                ("404", "Not Found"),
                ("409", "Conflict"),
                ("410", "Gone"),
                ("500", "Internal Server Error"),
            ):
                responses.setdefault(
                    code,
                    {
                        "description": desc,
                        "content": {
                            "application/json": {"schema": _openapi_schema_ref("ErrorResponse")}
                        },
                    },
                )

            # Document response header added by RequestIdMiddleware in the main app.
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

            # Binary download endpoints.
            if method == "get" and path in {
                "/attachments/{attachment_id}",
                "/public/shares/{share_token}/attachments/{attachment_id}",
            }:
                responses["200"] = {
                    "description": "File bytes",
                    "content": {
                        "application/octet-stream": {
                            "schema": {"type": "string", "format": "binary"}
                        }
                    },
                    "headers": {
                        "Content-Disposition": {
                            "schema": {"type": "string"},
                            "description": "attachment; filename=...",
                        },
                        "X-Request-Id": {
                            "schema": {"type": "string"},
                            "description": "Echoed or generated request id.",
                        },
                    },
                }

    return schema


def custom_openapi() -> dict[str, object]:
    # Cache the generated schema to avoid per-request work.
    if v2_app.openapi_schema:
        return cast(dict[str, object], v2_app.openapi_schema)

    schema = cast(
        dict[str, object],
        get_openapi(
            title=v2_app.title,
            version=cast(str, v2_app.version) if v2_app.version else "0.1.0",
            routes=v2_app.routes,
        ),
    )
    v2_app.openapi_schema = _patch_v2_openapi(schema)
    return cast(dict[str, object], v2_app.openapi_schema)


v2_app.openapi = custom_openapi  # type: ignore[method-assign]

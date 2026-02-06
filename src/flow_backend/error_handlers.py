"""统一异常处理（ErrorResponse）。

目标：
- 让所有 API（现统一为 /api/v1）在出错时返回稳定的 JSON 结构：
  {error, message, request_id, details}
- 避免 FastAPI 默认 {"detail": ...} 与自定义错误混杂，降低客户端分支成本
"""

from __future__ import annotations

import logging
from typing import cast

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from flow_backend.v2.schemas.errors import ErrorResponse

logger = logging.getLogger(__name__)


def _map_http_status_to_error(status_code: int) -> str:
    mapping: dict[int, str] = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        410: "gone",
        413: "payload_too_large",
        422: "validation_error",
        429: "rate_limited",
        502: "upstream_error",
    }
    return mapping.get(status_code, f"http_{status_code}")


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    http_exc = cast(StarletteHTTPException, exc)

    details: object | None = None
    message = str(http_exc.detail)
    if isinstance(http_exc.detail, dict):
        # 约定：{'message': str, 'details': object}
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
    headers = getattr(http_exc, "headers", None)
    return JSONResponse(
        status_code=http_exc.status_code,
        content=jsonable_encoder(payload, exclude_none=True),
        headers=headers,
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


def register_error_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册统一异常处理。"""

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

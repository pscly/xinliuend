from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """统一错误响应格式（Pinned Error Contract）。

    该结构最初用于 v2，但在“合并 v2 到 v1（仅保留 /api/v1）”后，
    服务端对外统一使用此错误响应格式，便于客户端与 Web 端做一致的错误解析。
    """

    error: str
    message: str
    request_id: str | None = None
    details: object | None = None

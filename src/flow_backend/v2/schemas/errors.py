from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Pinned v2 error contract.

    Keep this shape stable and v2-only (v1 keeps FastAPI default {"detail": ...}).
    """

    error: str
    message: str
    request_id: str | None = None
    details: object | None = None

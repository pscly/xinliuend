from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PublicShareCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=20_000)
    author_name: str | None = Field(default=None, max_length=100)
    attachment_ids: list[str] = Field(default_factory=list)
    # Optional; the API also accepts X-Captcha-Token header.
    captcha_token: str | None = Field(default=None, max_length=2000)


class PublicShareComment(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    body: str
    author_name: str | None = None
    attachment_ids: list[str] = Field(default_factory=list)

    is_folded: bool
    folded_reason: str | None = None
    created_at: datetime


class PublicShareCommentListResponse(BaseModel):
    comments: list[PublicShareComment] = Field(default_factory=list)


class ShareCommentConfigUpdateRequest(BaseModel):
    allow_anonymous_comments: bool | None = None
    anonymous_comments_require_captcha: bool | None = None


class ShareCommentConfig(BaseModel):
    allow_anonymous_comments: bool
    anonymous_comments_require_captcha: bool

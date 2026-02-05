from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_MAX_APP_PASSWORD_BYTES_FOR_MEMOS = 71


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(min_length=6, max_length=72)

    @field_validator("password")
    @classmethod
    def validate_password_bytes_for_memos(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_APP_PASSWORD_BYTES_FOR_MEMOS:
            raise ValueError("密码过长（为了给 Memos 追加 x，最多 71 字节）")
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9]+$")
    password: str = Field(min_length=1, max_length=72)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=6, max_length=72)
    new_password2: str = Field(min_length=6, max_length=72)

    @field_validator("new_password", "new_password2")
    @classmethod
    def validate_password_bytes_for_memos(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_APP_PASSWORD_BYTES_FOR_MEMOS:
            raise ValueError("密码过长（为了给 Memos 追加 x，最多 71 字节）")
        return v


class AuthData(BaseModel):
    token: str
    server_url: str


class AuthTokenResponse(BaseModel):
    token: str
    server_url: str
    csrf_token: str


class MeResponse(BaseModel):
    username: str
    is_admin: bool
    csrf_token: str | None = None


class ChangePasswordResponse(BaseModel):
    ok: bool = True
    csrf_token: str


class ApiResponse(BaseModel):
    code: int = 200
    data: dict

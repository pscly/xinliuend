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
    email: str | None = None
    email_verified: bool = False


class EmailBindRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class EmailBindConfirmRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=4, max_length=12)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    message: str = "如果该邮箱已注册并验证，重置链接已发送，请查收（含垃圾邮件）。"


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8, max_length=512)
    new_password: str = Field(min_length=6, max_length=72)
    new_password2: str = Field(min_length=6, max_length=72)

    @field_validator("new_password", "new_password2")
    @classmethod
    def validate_password_bytes_for_memos(cls, v: str) -> str:
        if len(v.encode("utf-8")) > _MAX_APP_PASSWORD_BYTES_FOR_MEMOS:
            raise ValueError("密码过长（为了给 Memos 追加 x，最多 71 字节）")
        return v


class ResetPasswordResponse(BaseModel):
    ok: bool = True
    memos_sync_warning: str | None = None


class ChangePasswordResponse(BaseModel):
    ok: bool = True
    csrf_token: str


class ApiResponse(BaseModel):
    code: int = 200
    data: dict


class MemosCredentialStatusResponse(BaseModel):
    memos_base_url: str
    has_token: bool
    token_preview: str | None = None
    memos_user_id: int | None = None
    memos_user_name: str | None = None
    can_auto_issue_token: bool


class MemosCredentialTokenRequest(BaseModel):
    memos_token: str = Field(min_length=1, max_length=8192)
    memos_user_id: int | None = Field(default=None, ge=0)


class MemosCredentialIssueTokenRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)


class MemosCredentialUpdateResponse(BaseModel):
    ok: bool = True
    token: str
    server_url: str
    memos_user_id: int | None
    memos_user_name: str
    memos_username: str
    token_preview: str
    csrf_token: str | None = None

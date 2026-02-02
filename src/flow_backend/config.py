from __future__ import annotations

from typing import ClassVar, final

try:
    # Pydantic v2
    from pydantic import AliasChoices, Field, model_validator
except ImportError:  # pragma: no cover
    # Fallback for environments where AliasChoices is unavailable.
    from pydantic import Field

    AliasChoices = None  # type: ignore[assignment]
    model_validator = None  # type: ignore[assignment]

from pydantic_settings import BaseSettings, SettingsConfigDict


_CORS_ALLOW_ORIGINS_VALIDATION_ALIAS = (
    AliasChoices("CORS_ALLOW_ORIGINS", "CORS_ORIGINS")
    if AliasChoices is not None
    else "CORS_ALLOW_ORIGINS"
)

# NOTE: Keep alias parsing centralized to avoid per-field conditional declarations.


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


@final
class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
        extra="ignore",
    )
    app_name: str = "Flow Backend"
    api_prefix: str = "/api/v1"

    # Environment (ENVIRONMENT): development | production
    environment: str = "development"

    database_url: str = "sqlite:///./dev.db"

    memos_base_url: str = "https://memos.example.com"
    memos_admin_token: str = ""
    memos_request_timeout_seconds: float = 15.0

    # Primary env: CORS_ALLOW_ORIGINS; also accept CORS_ORIGINS as alias.
    cors_allow_origins: str = Field(
        default="*",
        validation_alias=_CORS_ALLOW_ORIGINS_VALIDATION_ALIAS,
    )

    # Sharing
    public_base_url: str = "http://localhost:31031"
    share_token_secret: str = "share_token_secret_change_me"

    # Attachments
    attachments_local_dir: str = ".data/attachments"
    attachments_max_size_bytes: int = 25 * 1024 * 1024

    # S3 / Tencent Cloud COS
    s3_endpoint_url: str = ""
    s3_region: str = ""
    s3_bucket: str = ""
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    s3_force_path_style: bool = False

    admin_basic_user: str = "admin"
    admin_basic_password: str = "admin_password_change_me"

    # 管理后台会话：Cookie 签名密钥（生产环境务必通过 .env 覆写为高强度随机值）
    admin_session_secret: str = "admin_session_secret_change_me"
    # 管理后台会话有效期（秒）
    admin_session_max_age_seconds: int = 60 * 60 * 12  # 12 小时
    # 管理后台会话 Cookie 名称
    admin_session_cookie_name: str = "flow_admin_session"

    # Comma-separated endpoint list, tried in order.
    memos_create_user_endpoints: str = "/api/v1/users"
    memos_create_token_endpoints: str = "/api/v1/users/{user_id}/accessTokens"

    # Notes connector endpoint overrides (comma-separated)
    memos_note_list_endpoints: str = "/api/v1/memos"
    memos_note_upsert_endpoints: str = "/api/v1/memos"
    memos_note_delete_endpoints: str = "/api/v1/memos/{memo_id}"

    dev_bypass_memos: bool = False
    log_level: str = "INFO"
    memos_allow_reset_password_for_existing_user: bool = False

    # Sync（离线/多端）相关：LWW 使用 client_updated_at_ms，并对客户端“超前时间”做钳制
    sync_max_client_clock_skew_seconds: int = 300
    sync_pull_limit: int = 200
    default_tzid: str = "Asia/Shanghai"

    # Device/IP tracking (for admin dashboard)
    # If true, use X-Forwarded-For to determine client IP. Only enable behind a trusted proxy.
    trust_x_forwarded_for: bool = False

    # If true, trust X-Forwarded-Proto (for Secure cookies behind a reverse proxy).
    # Only enable behind a trusted proxy.
    trust_x_forwarded_proto: bool = False
    # Consider a device "online" if it has called any authenticated API within this window.
    device_active_window_seconds: int = 60 * 60 * 24  # 24 hours

    # If true, persist device tracking after the response in a background task.
    # Tests can set DEVICE_TRACKING_ASYNC=false to make writes deterministic.
    device_tracking_async: bool = True

    # Rate limiting (best-effort; to reduce brute-force / abuse)
    rate_limit_window_seconds: int = 60 * 5
    auth_login_rate_limit_per_ip: int = 30
    auth_login_rate_limit_per_ip_user: int = 10
    auth_register_rate_limit_per_ip: int = 10
    admin_login_rate_limit_per_ip: int = 20

    # Validate production settings early to fail fast on unsafe defaults.
    if model_validator is not None:

        @model_validator(mode="after")
        def _validate_production_settings(self) -> "Settings":  # pyright: ignore[reportUnusedFunction]  # basedpyright: ignore[reportUnusedFunction]
            if self.environment.strip().lower() != "production":
                return self

            errors: list[str] = []

            if (
                not self.admin_basic_password.strip()
                or self.admin_basic_password == "admin_password_change_me"
            ):
                errors.append("ADMIN_BASIC_PASSWORD must be set in production")

            if (
                not self.admin_session_secret.strip()
                or self.admin_session_secret == "admin_session_secret_change_me"
            ):
                errors.append("ADMIN_SESSION_SECRET must be set in production")

            share_secret = self.share_token_secret.strip()
            if not share_secret or share_secret == "share_token_secret_change_me":
                errors.append("SHARE_TOKEN_SECRET must be set in production")

            cors_v = self.cors_allow_origins.strip()
            if not cors_v or cors_v == "*":
                errors.append("CORS_ALLOW_ORIGINS must be explicit (not '*') in production")

            if self.dev_bypass_memos:
                errors.append("DEV_BYPASS_MEMOS must be false in production")

            # If any S3 setting is provided, require the full set to avoid silently falling back to local storage.
            s3_fields = {
                "S3_BUCKET": self.s3_bucket.strip(),
                "S3_ENDPOINT_URL": self.s3_endpoint_url.strip(),
                "S3_ACCESS_KEY_ID": self.s3_access_key_id.strip(),
                "S3_SECRET_ACCESS_KEY": self.s3_secret_access_key.strip(),
            }
            if any(v for v in s3_fields.values()) and any(not v for v in s3_fields.values()):
                missing = ",".join([k for k, v in s3_fields.items() if not v])
                errors.append(f"S3 config incomplete in production; missing: {missing}")

            if errors:
                raise ValueError("Invalid production settings: " + "; ".join(errors))
            return self

    def cors_origins_list(self) -> list[str]:
        v = self.cors_allow_origins.strip()
        if not v:
            return []
        if v == "*":
            return ["*"]
        return _split_csv(v)

    def create_user_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_create_user_endpoints)
        if "/api/v1/users" in eps and "/api/v1/user" in eps:
            # 某些部署/版本 /api/v1/user 不存在，优先尝试 /api/v1/users
            eps = ["/api/v1/users", "/api/v1/user"] + [
                e for e in eps if e not in {"/api/v1/users", "/api/v1/user"}
            ]
        return eps

    def create_token_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_create_token_endpoints)
        preferred = "/api/v1/users/{user_id}/accessTokens"
        if preferred in eps:
            eps = [preferred] + [e for e in eps if e != preferred]
        return eps

    def note_list_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_note_list_endpoints)
        preferred = "/api/v1/memos"
        if preferred in eps:
            eps = [preferred] + [e for e in eps if e != preferred]
        return eps

    def note_upsert_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_note_upsert_endpoints)
        preferred = "/api/v1/memos"
        if preferred in eps:
            eps = [preferred] + [e for e in eps if e != preferred]
        return eps

    def note_delete_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_note_delete_endpoints)
        preferred = "/api/v1/memos/{memo_id}"
        if preferred in eps:
            eps = [preferred] + [e for e in eps if e != preferred]
        return eps

    def security_warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.admin_basic_password == "admin_password_change_me":
            warnings.append("ADMIN_BASIC_PASSWORD is using placeholder value")
        if self.admin_session_secret == "admin_session_secret_change_me":
            warnings.append("ADMIN_SESSION_SECRET is using placeholder value")
        share_secret = self.share_token_secret.strip()
        if not share_secret or share_secret == "share_token_secret_change_me":
            warnings.append("SHARE_TOKEN_SECRET is missing or using placeholder value")
        if self.cors_allow_origins.strip() == "*":
            warnings.append("CORS_ALLOW_ORIGINS='*' is permissive")
        if self.dev_bypass_memos:
            warnings.append("DEV_BYPASS_MEMOS=true should not be enabled in production")
        return warnings


if model_validator is not None:
    # The validator is invoked by Pydantic at runtime.
    _ = Settings._validate_production_settings


settings = Settings()

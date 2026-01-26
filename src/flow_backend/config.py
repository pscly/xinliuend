from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Flow Backend"
    api_prefix: str = "/api/v1"

    database_url: str = "sqlite:///./dev.db"

    memos_base_url: str = "https://memos.example.com"
    memos_admin_token: str = ""
    memos_request_timeout_seconds: float = 15.0

    cors_allow_origins: str = "*"

    admin_basic_user: str = "admin"
    admin_basic_password: str = "admin_password_change_me"

    # Comma-separated endpoint list, tried in order.
    memos_create_user_endpoints: str = "/api/v1/users"
    memos_create_token_endpoints: str = (
        "/api/v1/users/{user_id}/accessTokens"
    )

    dev_bypass_memos: bool = False
    log_level: str = "INFO"
    memos_allow_reset_password_for_existing_user: bool = False

    # Sync（离线/多端）相关：LWW 使用 client_updated_at_ms，并对客户端“超前时间”做钳制
    sync_max_client_clock_skew_seconds: int = 300
    sync_pull_limit: int = 200
    default_tzid: str = "Asia/Shanghai"

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
            eps = ["/api/v1/users", "/api/v1/user"] + [e for e in eps if e not in {"/api/v1/users", "/api/v1/user"}]
        return eps

    def create_token_endpoints_list(self) -> list[str]:
        eps = _split_csv(self.memos_create_token_endpoints)
        preferred = "/api/v1/users/{user_id}/accessTokens"
        if preferred in eps:
            eps = [preferred] + [e for e in eps if e != preferred]
        return eps


settings = Settings()

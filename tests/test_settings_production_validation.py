from __future__ import annotations

import pytest

from flow_backend.config import Settings


def test_settings_development_allows_placeholders():
    # Development should stay frictionless: placeholder values are allowed.
    Settings.model_validate({"environment": "development"})


def test_settings_production_requires_secrets_and_core_config():
    with pytest.raises(Exception) as excinfo:
        Settings.model_validate({"environment": "production"})

    msg = str(excinfo.value)
    assert "ADMIN_BASIC_PASSWORD" in msg
    assert "ADMIN_SESSION_SECRET" in msg
    assert "USER_SESSION_SECRET" in msg
    assert "USER_PASSWORD_ENCRYPTION_KEY" in msg
    assert "SHARE_TOKEN_SECRET" in msg
    assert "CORS_ALLOW_ORIGINS" in msg
    assert "MEMOS_ADMIN_TOKEN" in msg
    assert "MEMOS_BASE_URL" in msg
    assert "DATABASE_URL" in msg
    assert "PUBLIC_BASE_URL" in msg


def test_settings_production_allows_safe_defaults_when_configured():
    Settings.model_validate(
        {
            "environment": "production",
            "database_url": "postgresql+psycopg://u:p@localhost:5432/flow",
            "memos_base_url": "https://memos.real.example.com",
            "memos_admin_token": "test-admin-token",
            "public_base_url": "https://public.example.com",
            "admin_basic_password": "strong-password",
            "admin_session_secret": "strong-session-secret",
            "user_session_secret": "strong-user-session-secret",
            "user_password_encryption_key": "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno=",
            "share_token_secret": "strong-share-secret",
            "cors_allow_origins": "https://example.com",
            "dev_bypass_memos": False,
            "attachments_max_size_bytes": 1024,
        }
    )


def test_settings_production_rejects_partial_s3_config():
    with pytest.raises(Exception) as excinfo:
        Settings.model_validate(
            {
                "environment": "production",
                "database_url": "postgresql+psycopg://u:p@localhost:5432/flow",
                "memos_base_url": "https://memos.real.example.com",
                "memos_admin_token": "test-admin-token",
                "public_base_url": "https://public.example.com",
                "admin_basic_password": "strong-password",
                "admin_session_secret": "strong-session-secret",
                "user_session_secret": "strong-user-session-secret",
                "user_password_encryption_key": "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno=",
                "share_token_secret": "strong-share-secret",
                "cors_allow_origins": "https://example.com",
                "dev_bypass_memos": False,
                "s3_bucket": "bucket",
            }
        )

    assert "S3 config incomplete" in str(excinfo.value)

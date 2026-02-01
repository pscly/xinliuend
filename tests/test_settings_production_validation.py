from __future__ import annotations

import pytest

from flow_backend.config import Settings


def test_settings_development_allows_placeholders():
    # Development should stay frictionless: placeholder values are allowed.
    Settings(_env_file=None, environment="development")


def test_settings_production_requires_secrets_and_cors():
    with pytest.raises(ValueError) as excinfo:
        Settings(_env_file=None, environment="production")

    msg = str(excinfo.value)
    assert "ADMIN_BASIC_PASSWORD" in msg
    assert "ADMIN_SESSION_SECRET" in msg
    assert "SHARE_TOKEN_SECRET" in msg
    assert "CORS_ALLOW_ORIGINS" in msg


def test_settings_production_allows_safe_defaults_when_configured():
    Settings(
        _env_file=None,
        environment="production",
        admin_basic_password="strong-password",
        admin_session_secret="strong-session-secret",
        share_token_secret="strong-share-secret",
        cors_allow_origins="https://example.com",
        dev_bypass_memos=False,
    )


def test_settings_production_rejects_partial_s3_config():
    with pytest.raises(ValueError) as excinfo:
        Settings(
            _env_file=None,
            environment="production",
            admin_basic_password="strong-password",
            admin_session_secret="strong-session-secret",
            share_token_secret="strong-share-secret",
            cors_allow_origins="https://example.com",
            dev_bypass_memos=False,
            s3_bucket="bucket",
        )

    assert "S3 config incomplete" in str(excinfo.value)

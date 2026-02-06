from __future__ import annotations

import pytest

from flow_backend.config import settings
from flow_backend.password_crypto import decrypt_password, encrypt_password


def test_password_crypto_encrypt_decrypt_roundtrip():
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = "WmfpBBPjCEIb_IJvZP_t6aG9AZ51qHm_iNg0Q_y6Bno="
    try:
        token = encrypt_password("pass1234")
        assert token != "pass1234"
        assert decrypt_password(token) == "pass1234"
    finally:
        settings.user_password_encryption_key = old_key


def test_password_crypto_requires_key():
    old_key = settings.user_password_encryption_key
    settings.user_password_encryption_key = ""
    try:
        with pytest.raises(ValueError):
            _ = encrypt_password("x")
    finally:
        settings.user_password_encryption_key = old_key

from __future__ import annotations

import pytest

from flow_backend.memos_client import MemosClientError, memos_password_from_app_password
from flow_backend.schemas import RegisterRequest


def test_memos_password_from_app_password_appends_x() -> None:
    assert memos_password_from_app_password("123456") == "123456x"


def test_memos_password_from_app_password_rejects_over_71_bytes() -> None:
    too_long = "a" * 72
    with pytest.raises(MemosClientError):
        memos_password_from_app_password(too_long)


def test_register_request_rejects_over_71_bytes_password() -> None:
    too_long = "a" * 72
    with pytest.raises(ValueError):
        RegisterRequest(username="abc123", password=too_long)

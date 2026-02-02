from __future__ import annotations

from typing import cast

import httpx
import pytest

from flow_backend.main import app  # pyright: ignore[reportMissingTypeStubs]


def _make_async_client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.anyio
async def test_v1_openapi_documents_x_request_id_header_parameter_for_login() -> None:
    async with _make_async_client() as client:
        r = await client.get("/openapi.json")
        assert r.status_code == 200

        data = cast(dict[str, object], r.json())
        paths_obj = data.get("paths", {})
        assert isinstance(paths_obj, dict)
        paths = cast(dict[str, object], paths_obj)

        login_path_obj = paths.get("/api/v1/auth/login")
        assert isinstance(login_path_obj, dict)
        login_path = cast(dict[str, object], login_path_obj)

        login_post_obj = login_path.get("post")
        assert isinstance(login_post_obj, dict)
        login_post = cast(dict[str, object], login_post_obj)

        params_obj = login_post.get("parameters", [])
        params = params_obj if isinstance(params_obj, list) else []
        assert any(
            isinstance(p, dict)
            and p.get("in") == "header"
            and isinstance(p.get("name"), str)
            and cast(str, p.get("name")).lower() == "x-request-id"
            for p in params
        )

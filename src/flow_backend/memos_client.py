"""Memos 管理端 API 封装。

说明：Memos 的 API 在不同版本之间变动较大，因此这里不把 endpoint/payload 写死，
而是采用“多 endpoint + 多 payload 尝试”的策略，并允许通过环境变量覆写。

如果你在 /api/v1/auth/register 看到 502，优先用 Postman 在当前 Memos 实例上把
“创建用户/创建 Token”流程调通，再把正确的 endpoint 写入 .env。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx


@dataclass(frozen=True)
class MemosUserAndToken:
    memos_user_id: int
    memos_token: str


class MemosClientError(RuntimeError):
    pass


class MemosPermissionDeniedError(MemosClientError):
    pass


class MemosUserAlreadyExistsError(MemosClientError):
    pass


_MEMOS_PASSWORD_SUFFIX = "x"
_MAX_APP_PASSWORD_BYTES_FOR_MEMOS = 71


def memos_password_from_app_password(password: str) -> str:
    """将“App 侧密码”转换为“Memos 侧密码”。

    目的：避免用户用同一账号密码直接登录 Memos 后台（Memos 侧密码总是多一个后缀）。
    约束：考虑到 bcrypt 72 字节截断，为确保后缀有效，App 侧密码最多 71 字节（UTF-8）。
    """
    if len(password.encode("utf-8")) > _MAX_APP_PASSWORD_BYTES_FOR_MEMOS:
        raise MemosClientError("密码过长（为了给 Memos 追加 x，最多 71 字节）")
    return f"{password}{_MEMOS_PASSWORD_SUFFIX}"


class MemosClient:
    def __init__(self, base_url: str, admin_token: str, timeout_seconds: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token.strip()
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        if not self._admin_token:
            raise MemosClientError("MEMOS_ADMIN_TOKEN is empty")
        return {"Authorization": f"Bearer {self._admin_token}"}

    async def _post_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, headers=self._headers(), json=payload)

    async def _post_json_with_headers(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, headers=headers, json=payload)

    async def _patch_json(
        self, url: str, payload: dict[str, Any], params: dict[str, Any] | None = None
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.patch(url, headers=self._headers(), params=params, json=payload)

    async def list_users(self) -> list[dict[str, Any]]:
        url = f"{self._base_url}/api/v1/users"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers())
            if 200 <= resp.status_code < 300:
                data = resp.json()
                if isinstance(data, dict) and isinstance(data.get("users"), list):
                    return [u for u in data["users"] if isinstance(u, dict)]
                raise MemosClientError(f"List users succeeded but cannot parse response: {data}")
            raise MemosClientError(f"List users failed. {resp.status_code} {resp.text}")

    async def find_user_id_by_username(self, username: str) -> int | None:
        users = await self.list_users()
        for u in users:
            if (
                u.get("username") == username
                and isinstance(u.get("name"), str)
                and u["name"].startswith("users/")
            ):
                try:
                    return int(u["name"].split("/", 1)[1])
                except Exception:
                    return None
        return None

    async def update_user_password(self, user_id: int, new_password: str) -> None:
        url = f"{self._base_url}/api/v1/users/{user_id}"
        params = {"update_mask": "password"}
        payload = {
            "name": f"users/{user_id}",
            "password": memos_password_from_app_password(new_password),
        }
        resp = await self._patch_json(url, payload=payload, params=params)
        if 200 <= resp.status_code < 300:
            return
        raise MemosClientError(f"Update user password failed. {resp.status_code} {resp.text}")

    async def create_user(self, endpoints: list[str], username: str, password: str) -> int:
        memos_password = memos_password_from_app_password(password)
        payloads = [
            {"username": username, "password": memos_password},
            {"user": {"username": username, "password": memos_password}},
            {"user": {"username": username, "password": memos_password, "role": "USER"}},
        ]
        last_error = ""
        saw_already_exists = False
        for ep in endpoints:
            url = f"{self._base_url}{ep}"
            for payload in payloads:
                resp = await self._post_json(url, payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    # Common shapes:
                    # - {"id": 1}
                    # - {"name": "users/1"}
                    # - {"user": {"id": 1}} / {"user": {"name": "users/1"}}
                    if isinstance(data, dict):
                        if isinstance(data.get("id"), int):
                            return data["id"]
                        user = data.get("user")
                        if isinstance(user, dict) and isinstance(user.get("id"), int):
                            return user["id"]
                        if (
                            isinstance(user, dict)
                            and isinstance(user.get("name"), str)
                            and user["name"].startswith("users/")
                        ):
                            try:
                                return int(user["name"].split("/", 1)[1])
                            except Exception:
                                pass
                        name = data.get("name")
                        if isinstance(name, str) and name.startswith("users/"):
                            try:
                                return int(name.split("/", 1)[1])
                            except Exception:
                                pass
                    raise MemosClientError(
                        f"Create user succeeded but cannot parse response: {data}"
                    )
                if resp.status_code in (400, 409) and "already" in resp.text.lower():
                    saw_already_exists = True
                last_error = f"{resp.status_code} {resp.text}"
        if saw_already_exists:
            raise MemosUserAlreadyExistsError(
                f"Create user failed (already exists). last_error={last_error}"
            )
        raise MemosClientError(f"Create user failed. last_error={last_error}")

    async def create_access_token(self, endpoints: list[str], user_id: int, token_name: str) -> str:
        # 兼容性说明：
        # - 在某些 Memos 版本中，创建 Token 的请求体是“扁平字段”，成功响应里返回字段名是 accessToken（不是 token）。
        # - 旧版本/其它版本可能返回 token 或 accessToken.token。
        payloads = [
            {"description": token_name},
            {"name": token_name},
        ]
        last_error = ""
        saw_permission_denied = False
        for ep in endpoints:
            ep2 = ep.replace("{user_id}", str(user_id))
            url = f"{self._base_url}{ep2}"
            for payload in payloads:
                resp = await self._post_json(url, payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    # Common shapes:
                    # - {"accessToken": "..."}                      (memos 新版常见)
                    # - {"token": "..."}
                    # - {"accessToken": {"token": "..."}}           (某些版本)
                    if isinstance(data, dict):
                        access_token = data.get("accessToken")
                        if isinstance(access_token, str) and access_token:
                            return access_token
                        token = data.get("token")
                        if isinstance(token, str) and token:
                            return token
                        at = data.get("accessToken")
                        if isinstance(at, dict):
                            token2 = at.get("token")
                            if isinstance(token2, str) and token2:
                                return token2
                    raise MemosClientError(
                        f"Create token succeeded but cannot parse response: {data}"
                    )
                if resp.status_code == 403 and "permission denied" in resp.text.lower():
                    saw_permission_denied = True
                last_error = f"{resp.status_code} {resp.text}"
        if saw_permission_denied:
            raise MemosPermissionDeniedError(
                f"Create token permission denied for user {user_id}. last_error={last_error}"
            )
        raise MemosClientError(f"Create token failed. last_error={last_error}")

    async def create_session(self, username: str, password: str) -> httpx.Cookies:
        url = f"{self._base_url}/api/v1/auth/sessions"
        payload = {
            "passwordCredentials": {
                "username": username,
                "password": memos_password_from_app_password(password),
            }
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, json=payload)
            if 200 <= resp.status_code < 300:
                # 说明：某些 Memos 版本通过 grpc-metadata-set-cookie 下发 cookie（而非标准 Set-Cookie）。
                cookie_header = (
                    resp.headers.get("grpc-metadata-set-cookie")
                    or resp.headers.get("set-cookie")
                    or ""
                )
                cookie_pair = cookie_header.split(";", 1)[0].strip()
                if cookie_pair:
                    # 形如：user_session=xxxx
                    return httpx.Cookies(
                        {cookie_pair.split("=", 1)[0]: cookie_pair.split("=", 1)[1]}
                    )
                raise MemosClientError("Create session succeeded but no session cookie returned")
            raise MemosClientError(f"Create session failed. {resp.status_code} {resp.text}")

    async def create_access_token_as_user(
        self,
        user_id: int,
        username: str,
        password: str,
        token_name: str,
    ) -> str:
        cookies = await self.create_session(username=username, password=password)
        url = f"{self._base_url}/api/v1/users/{user_id}/accessTokens"
        payload = {"description": token_name}
        async with httpx.AsyncClient(timeout=self._timeout, cookies=cookies) as client:
            resp = await client.post(url, json=payload)
            if 200 <= resp.status_code < 300:
                data = resp.json()
                if isinstance(data, dict):
                    access_token = data.get("accessToken")
                    if isinstance(access_token, str) and access_token:
                        return access_token
                    token = data.get("token")
                    if isinstance(token, str) and token:
                        return token
                raise MemosClientError(f"Create token succeeded but cannot parse response: {data}")
            raise MemosClientError(f"Create token (as user) failed. {resp.status_code} {resp.text}")

    async def create_access_token_with_bearer(
        self,
        user_id: int,
        bearer_token: str,
        token_name: str,
    ) -> str:
        """用“已有用户 token”给自己再签发一个新 token。

        用途：Admin 后台“重置 Token”不应依赖用户密码（后端不保存明文密码），而是用现有 token 作为凭据。
        """
        url = f"{self._base_url}/api/v1/users/{user_id}/accessTokens"
        headers = {"Authorization": f"Bearer {bearer_token}"}
        payload = {"description": token_name}
        resp = await self._post_json_with_headers(url, payload=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            data = resp.json()
            if isinstance(data, dict):
                access_token = data.get("accessToken")
                if isinstance(access_token, str) and access_token:
                    return access_token
                token = data.get("token")
                if isinstance(token, str) and token:
                    return token
            raise MemosClientError(f"Create token succeeded but cannot parse response: {data}")
        raise MemosClientError(f"Create token (bearer) failed. {resp.status_code} {resp.text}")

    async def create_user_and_token(
        self,
        create_user_endpoints: list[str],
        create_token_endpoints: list[str],
        username: str,
        password: str,
        allow_reset_existing_user_password: bool = False,
    ) -> MemosUserAndToken:
        # 重要：某些 Memos 版本中，管理员无权为“其它用户”直接创建 accessToken（会 403）。
        # 因此这里采用“同密码创建 Memos 用户 + 以该用户创建 session 后自助生成 token”的策略。
        try:
            memos_user_id = await self.create_user(
                create_user_endpoints, username=username, password=password
            )
        except MemosUserAlreadyExistsError:
            if not allow_reset_existing_user_password:
                raise
            existing_user_id = await self.find_user_id_by_username(username=username)
            if not existing_user_id:
                raise MemosClientError(
                    "User already exists in Memos, but cannot find user id via list users"
                )
            # 将 Memos 侧密码更新为用户提交的密码，便于创建 session 并签发 token（用于修复历史半成品账号）
            await self.update_user_password(user_id=existing_user_id, new_password=password)
            memos_user_id = existing_user_id
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        token_name = f"flow-{username}-{ts}"
        try:
            memos_token = await self.create_access_token(
                create_token_endpoints, user_id=memos_user_id, token_name=token_name
            )
        except MemosPermissionDeniedError:
            memos_token = await self.create_access_token_as_user(
                user_id=memos_user_id,
                username=username,
                password=password,
                token_name=token_name,
            )
        return MemosUserAndToken(memos_user_id=memos_user_id, memos_token=memos_token)

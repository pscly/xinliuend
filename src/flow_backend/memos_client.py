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
    memos_user_id: int | None
    memos_user_name: str
    memos_token: str


@dataclass(frozen=True)
class MemosCurrentUser:
    username: str
    # 新版 Memos 可能只返回 users/<username>，此时没有数字 ID，沿用 0 作为兼容哨兵值。
    user_id: int
    user_name: str

    def __getitem__(self, key: str) -> str | int:
        if key == "username":
            return self.username
        if key == "user_id":
            return self.user_id
        if key in {"user_name", "name"}:
            return self.user_name
        raise KeyError(key)

    def as_dict(self) -> dict[str, str | int]:
        return {
            "username": self.username,
            "user_id": self.user_id,
            # 保留 name 兼容已有调用方/测试；服务层会把它视为 user resource name。
            "name": self.user_name,
        }


@dataclass(frozen=True)
class MemosSignInResult:
    access_token: str
    username: str
    user_id: int
    user_name: str

    def __getitem__(self, key: str) -> str | int:
        if key == "access_token":
            return self.access_token
        if key == "username":
            return self.username
        if key == "user_id":
            return self.user_id
        if key in {"user_name", "name"}:
            return self.user_name
        raise KeyError(key)

    def as_dict(self) -> dict[str, str | int]:
        return {
            "access_token": self.access_token,
            "username": self.username,
            "user_id": self.user_id,
            # 保留 name 兼容已有调用方/测试；服务层会把它视为 user resource name。
            "name": self.user_name,
        }


class MemosClientError(RuntimeError):
    pass


class MemosPermissionDeniedError(MemosClientError):
    pass


class MemosUserAlreadyExistsError(MemosClientError):
    pass


_MEMOS_PASSWORD_SUFFIX = "x"
_MAX_APP_PASSWORD_BYTES_FOR_MEMOS = 71


def _parse_user_id_from_name(name: object) -> int | None:
    if isinstance(name, str) and name.startswith("users/"):
        raw = name.split("/", 1)[1]
        if raw.isdigit():
            return int(raw)
    return None


def _parse_user_name(name: object) -> str | None:
    if isinstance(name, str) and name.startswith("users/"):
        return name
    return None


def _resource_tail(user_name: str) -> str:
    if user_name.startswith("users/"):
        return user_name.split("/", 1)[1]
    return user_name


def _parse_user_identity(data: object) -> MemosCurrentUser:
    candidates: list[dict[str, Any]] = []
    if isinstance(data, dict):
        candidates.append(data)
        user_obj = data.get("user")
        if isinstance(user_obj, dict):
            candidates.insert(0, user_obj)

    for obj in candidates:
        username = obj.get("username")
        if not isinstance(username, str) or not username.strip():
            continue

        clean_username = username.strip()
        user_name = _parse_user_name(obj.get("name")) or f"users/{clean_username}"

        user_id: int | None = None
        if isinstance(obj.get("id"), int):
            user_id = int(obj["id"])
        elif isinstance(obj.get("id"), str) and str(obj.get("id")).isdigit():
            user_id = int(str(obj.get("id")))
        if user_id is None:
            user_id = _parse_user_id_from_name(obj.get("name"))

        return MemosCurrentUser(
            username=clean_username,
            user_id=int(user_id) if user_id is not None else 0,
            user_name=user_name,
        )

    raise MemosClientError(f"Cannot parse Memos user identity from response: {data}")


def _extract_token(data: object) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in ("accessToken", "access_token", "token"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    access_token_obj = data.get("accessToken")
    if isinstance(access_token_obj, dict):
        for key in ("token", "accessToken", "access_token"):
            value = access_token_obj.get(key)
            if isinstance(value, str) and value:
                return value
    pat_obj = data.get("personalAccessToken")
    if isinstance(pat_obj, dict):
        for key in ("token", "accessToken", "access_token"):
            value = pat_obj.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def memos_password_from_app_password(password: str) -> str:
    """将“App 侧密码”转换为“Memos 侧密码”。

    目的：避免用户用同一账号密码直接登录 Memos 后台（Memos 侧密码总是多一个后缀）。
    约束：考虑到 bcrypt 72 字节截断，为确保后缀有效，App 侧密码最多 71 字节（UTF-8）。
    """
    if len(password.encode("utf-8")) > _MAX_APP_PASSWORD_BYTES_FOR_MEMOS:
        raise MemosClientError("密码过长（为了给 Memos 追加 x，最多 71 字节）")
    return f"{password}{_MEMOS_PASSWORD_SUFFIX}"


class MemosClient:
    def __init__(
        self,
        base_url: str,
        admin_token: str,
        timeout_seconds: float,
        trust_env: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._admin_token = admin_token.strip()
        self._timeout = timeout_seconds
        self._trust_env = bool(trust_env)

    def _build_async_client(self, *, cookies: httpx.Cookies | None = None) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {
            "timeout": self._timeout,
            "trust_env": self._trust_env,
        }
        if cookies is not None:
            kwargs["cookies"] = cookies
        return httpx.AsyncClient(**kwargs)

    def _headers(self) -> dict[str, str]:
        if not self._admin_token:
            raise MemosClientError("MEMOS_ADMIN_TOKEN is empty")
        return {"Authorization": f"Bearer {self._admin_token}"}

    async def _post_json(self, url: str, payload: dict[str, Any]) -> httpx.Response:
        async with self._build_async_client() as client:
            return await client.post(url, headers=self._headers(), json=payload)

    async def _post_json_with_headers(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> httpx.Response:
        async with self._build_async_client() as client:
            return await client.post(url, headers=headers, json=payload)

    async def _patch_json(
        self, url: str, payload: dict[str, Any], params: dict[str, Any] | None = None
    ) -> httpx.Response:
        async with self._build_async_client() as client:
            return await client.patch(url, headers=self._headers(), params=params, json=payload)

    async def list_users(self) -> list[dict[str, Any]]:
        url = f"{self._base_url}/api/v1/users"
        async with self._build_async_client() as client:
            resp = await client.get(url, headers=self._headers())
            if 200 <= resp.status_code < 300:
                data = resp.json()
                if isinstance(data, dict) and isinstance(data.get("users"), list):
                    return [u for u in data["users"] if isinstance(u, dict)]
                raise MemosClientError(f"List users succeeded but cannot parse response: {data}")
            raise MemosClientError(f"List users failed. {resp.status_code} {resp.text}")

    async def find_user_id_by_username(self, username: str) -> int | None:
        users = await self.list_users()
        normalized = username.strip()
        for u in users:
            if u.get("username") != normalized:
                continue
            if isinstance(u.get("name"), str) and u["name"].startswith("users/"):
                try:
                    return int(u["name"].split("/", 1)[1])
                except Exception:
                    pass
            if isinstance(u.get("id"), int):
                return int(u["id"])
            if isinstance(u.get("id"), str) and str(u.get("id")).isdigit():
                return int(str(u.get("id")))
        return None

    async def find_user_name_by_username(self, username: str) -> str | None:
        users = await self.list_users()
        normalized = username.strip()
        for u in users:
            if u.get("username") != normalized:
                continue
            name = u.get("name")
            if isinstance(name, str) and name.startswith("users/"):
                return name
            if isinstance(u.get("id"), int):
                return f"users/{int(u['id'])}"
            if isinstance(u.get("id"), str) and str(u.get("id")).isdigit():
                return f"users/{str(u.get('id'))}"
        return None

    async def update_user_password(
        self,
        *,
        new_password: str,
        user_name: str | None = None,
        user_id: int | None = None,
        username: str | None = None,
    ) -> None:
        """Patch a Memos user's password.

        兼容两类用户资源：
        - 新版：`users/<username>`
        - 旧版：`users/<numeric_id>`
        """

        memos_password = memos_password_from_app_password(new_password)
        attempts: list[tuple[str, dict[str, object]]] = []

        explicit_user_name = (user_name or "").strip()
        clean_username = (username or "").strip()

        if explicit_user_name:
            attempts.append(
                (
                    f"{self._base_url}/api/v1/{explicit_user_name}",
                    {
                        "name": explicit_user_name,
                        "password": memos_password,
                    },
                )
            )
        elif clean_username:
            username_resource = f"users/{clean_username}"
            attempts.append(
                (
                    f"{self._base_url}/api/v1/{username_resource}",
                    {
                        "name": username_resource,
                        "username": clean_username,
                        "password": memos_password,
                    },
                )
            )

        if isinstance(user_id, int) and user_id > 0:
            numeric_resource = f"users/{user_id}"
            if not attempts or attempts[-1][0] != f"{self._base_url}/api/v1/{numeric_resource}":
                attempts.append(
                    (
                        f"{self._base_url}/api/v1/{numeric_resource}",
                        {
                            "name": numeric_resource,
                            "password": memos_password,
                        },
                    )
                )

        if not attempts:
            raise MemosClientError(
                "Update user password failed: neither memos user id nor username is set"
            )

        last_error = ""
        for url, payload in attempts:
            resp = await self._patch_json(url, payload=payload, params={"update_mask": "password"})
            if 200 <= resp.status_code < 300:
                return
            last_error = f"{url} -> {resp.status_code} {resp.text}"
        raise MemosClientError(f"Update user password failed. last_error={last_error}")

    async def create_user(self, endpoints: list[str], username: str, password: str) -> str:
        memos_password = memos_password_from_app_password(password)
        payloads = [
            {
                "user": {
                    "username": username,
                    "password": memos_password,
                    "role": "USER",
                    "state": "NORMAL",
                },
                "userId": username.lower(),
            },
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
                    if isinstance(data, dict):
                        user = data.get("user")
                        if isinstance(user, dict) and isinstance(user.get("name"), str):
                            user_name = _parse_user_name(user.get("name"))
                            if user_name:
                                return user_name
                        if isinstance(data.get("id"), int):
                            return f"users/{int(data['id'])}"
                        if isinstance(data.get("id"), str) and str(data.get("id")).isdigit():
                            return f"users/{str(data.get('id'))}"
                        if isinstance(user, dict) and isinstance(user.get("id"), int):
                            return f"users/{int(user['id'])}"
                        if (
                            isinstance(user, dict)
                            and isinstance(user.get("id"), str)
                            and str(user.get("id")).isdigit()
                        ):
                            return f"users/{str(user.get('id'))}"
                        name = data.get("name")
                        user_name = _parse_user_name(name)
                        if user_name:
                            return user_name
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

    async def create_access_token(
        self,
        endpoints: list[str],
        user_name: str,
        token_name: str,
    ) -> str:
        # 兼容性说明：
        # - 新版 PAT 路径：/api/v1/{user_name}/personalAccessTokens
        # - 老版/兜底：/api/v1/users/{user_id}/accessTokens
        last_error = ""
        saw_permission_denied = False
        resource_tail = _resource_tail(user_name)
        for ep in endpoints:
            ep2 = (
                ep.replace("{user_id}", resource_tail)
                .replace("{user_name}", user_name)
                .replace("{user}", resource_tail)
            )
            url = f"{self._base_url}{ep2}"
            is_pat_endpoint = "personalAccessTokens" in ep2
            payloads = (
                [
                    {
                        "parent": user_name,
                        "description": token_name,
                        "expiresInDays": 0,
                    },
                    {"description": token_name},
                    {"name": token_name},
                ]
                if is_pat_endpoint
                else [
                    {"description": token_name},
                    {"name": token_name},
                    {
                        "parent": user_name,
                        "description": token_name,
                        "expiresInDays": 0,
                    },
                ]
            )
            for payload in payloads:
                resp = await self._post_json(url, payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
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
                f"Create token permission denied for user {user_name}. last_error={last_error}"
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
        async with self._build_async_client() as client:
            resp = await client.post(url, json=payload)
            if 200 <= resp.status_code < 300:
                cookie_header = (
                    resp.headers.get("grpc-metadata-set-cookie")
                    or resp.headers.get("set-cookie")
                    or ""
                )
                cookie_pair = cookie_header.split(";", 1)[0].strip()
                if cookie_pair:
                    return httpx.Cookies(
                        {cookie_pair.split("=", 1)[0]: cookie_pair.split("=", 1)[1]}
                    )
                raise MemosClientError("Create session succeeded but no session cookie returned")
            raise MemosClientError(f"Create session failed. {resp.status_code} {resp.text}")

    async def create_access_token_as_user(
        self,
        *,
        user_name: str,
        username: str,
        password: str,
        token_name: str,
    ) -> str:
        cookies = await self.create_session(username=username, password=password)
        candidates = [
            (
                f"/api/v1/{user_name}/personalAccessTokens",
                {
                    "parent": user_name,
                    "description": token_name,
                    "expiresInDays": 0,
                },
            ),
            (f"/api/v1/{user_name}/accessTokens", {"description": token_name}),
        ]
        last_error = ""
        async with self._build_async_client(cookies=cookies) as client:
            for ep, payload in candidates:
                url = f"{self._base_url}{ep}"
                resp = await client.post(url, json=payload)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    token = _extract_token(data)
                    if token:
                        return token
                    raise MemosClientError(
                        f"Create token succeeded but cannot parse response: {data}"
                    )
                last_error = f"{resp.status_code} {resp.text}"
        raise MemosClientError(f"Create token (as user) failed. last_error={last_error}")

    async def create_access_token_with_bearer(
        self,
        *,
        bearer_token: str,
        token_name: str,
        user_name: str | None = None,
        user_id: int | None = None,
    ) -> str:
        """用“已有用户 token”给自己再签发一个新 token。"""
        resource = (user_name or "").strip()
        if not resource and isinstance(user_id, int) and user_id > 0:
            resource = f"users/{user_id}"
        if not resource:
            raise MemosClientError("Create token (bearer) failed: user identity is empty")

        url = f"{self._base_url}/api/v1/{resource}/accessTokens"
        headers = {"Authorization": f"Bearer {bearer_token.strip()}"}
        payload = {"description": token_name}
        resp = await self._post_json_with_headers(url, payload=payload, headers=headers)
        if 200 <= resp.status_code < 300:
            data = resp.json()
            token = _extract_token(data)
            if token:
                return token
            raise MemosClientError(f"Create token succeeded but cannot parse response: {data}")
        raise MemosClientError(f"Create token (bearer) failed. {resp.status_code} {resp.text}")

    async def get_current_user_with_bearer(self, token: str) -> dict[str, str | int]:
        bearer = token.strip()
        if not bearer:
            raise MemosClientError("Memos bearer token is empty")
        url = f"{self._base_url}/api/v1/auth/me"
        headers = {"Authorization": f"Bearer {bearer}"}
        async with self._build_async_client() as client:
            resp = await client.get(url, headers=headers)
        if 200 <= resp.status_code < 300:
            try:
                return _parse_user_identity(resp.json()).as_dict()
            except Exception as e:
                if isinstance(e, MemosClientError):
                    raise
                raise MemosClientError(
                    f"Get current user succeeded but cannot parse response: {e}"
                ) from e
        raise MemosClientError(f"Get current user failed. {resp.status_code} {resp.text}")

    async def sign_in_with_password(self, username: str, app_password: str) -> dict[str, str | int]:
        url = f"{self._base_url}/api/v1/auth/signin"
        payload = {
            "passwordCredentials": {
                "username": username,
                "password": memos_password_from_app_password(app_password),
            }
        }
        async with self._build_async_client() as client:
            resp = await client.post(url, json=payload)
        if 200 <= resp.status_code < 300:
            data = resp.json()
            token = _extract_token(data)
            if not token:
                raise MemosClientError(f"Sign in succeeded but cannot parse access token: {data}")
            identity = _parse_user_identity(data)
            return MemosSignInResult(
                access_token=token,
                username=identity.username,
                user_id=identity.user_id,
                user_name=identity.user_name,
            ).as_dict()
        raise MemosClientError(f"Sign in failed. {resp.status_code} {resp.text}")

    async def create_personal_access_token_with_bearer(
        self,
        *,
        bearer_token: str,
        description: str,
        user_name: str | None = None,
        user_id: int | None = None,
        expires_in_days: int = 0,
    ) -> str:
        bearer = bearer_token.strip()
        if not bearer:
            raise MemosClientError("Memos bearer token is empty")

        resource = (user_name or "").strip()
        if not resource and isinstance(user_id, int) and user_id > 0:
            resource = f"users/{user_id}"
        if not resource:
            raise MemosClientError("Create personal access token failed: user identity is empty")

        headers = {"Authorization": f"Bearer {bearer}"}
        candidates: list[tuple[str, dict[str, Any]]] = [
            (
                f"/api/v1/{resource}/personalAccessTokens",
                {
                    "parent": resource,
                    "description": description,
                    "expiresInDays": expires_in_days,
                },
            ),
            (f"/api/v1/{resource}/accessTokens", {"description": description}),
        ]
        last_error = ""
        for ep, payload in candidates:
            url = f"{self._base_url}{ep}"
            resp = await self._post_json_with_headers(url, payload=payload, headers=headers)
            if 200 <= resp.status_code < 300:
                data = resp.json()
                token = _extract_token(data)
                if token:
                    return token
                raise MemosClientError(f"Create token succeeded but cannot parse response: {data}")
            last_error = f"{resp.status_code} {resp.text}"
        raise MemosClientError(f"Create personal access token failed. last_error={last_error}")

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
            memos_user_name = await self.create_user(
                create_user_endpoints, username=username, password=password
            )
        except MemosUserAlreadyExistsError:
            if not allow_reset_existing_user_password:
                raise
            existing_user_name = await self.find_user_name_by_username(username=username)
            if not existing_user_name:
                raise MemosClientError(
                    "User already exists in Memos, but cannot find user resource name via list users"
                )
            await self.update_user_password(
                user_name=existing_user_name,
                user_id=_parse_user_id_from_name(existing_user_name),
                new_password=password,
            )
            memos_user_name = existing_user_name

        memos_user_id = _parse_user_id_from_name(memos_user_name)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        token_name = f"flow-{username}-{ts}"
        try:
            memos_token = await self.create_access_token(
                create_token_endpoints,
                user_name=memos_user_name,
                token_name=token_name,
            )
        except MemosPermissionDeniedError:
            memos_token = await self.create_access_token_as_user(
                user_name=memos_user_name,
                username=username,
                password=password,
                token_name=token_name,
            )
        return MemosUserAndToken(
            memos_user_id=memos_user_id,
            memos_user_name=memos_user_name,
            memos_token=memos_token,
        )

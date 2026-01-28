# 心流云服务后端（Flow Backend）

本仓库用于实现 `plan.md` 里规划的后端能力：

- App 只向本后端发起 **注册/登录**，获取：
  - `token`：Memos 的 Access Token
  - `server_url`：Memos 的 Base URL
- App 拿到 `token` 后，后续 **直接连接 Memos**（记笔记/同步/上传等不经过本后端）。

## 快速开始（Windows + uv）

1）复制环境变量文件：

- 将 `.env.example` 复制为 `.env`
- 按需填写：
  - `DATABASE_URL`
  - `MEMOS_BASE_URL`
  - `MEMOS_ADMIN_TOKEN`
  - `ADMIN_BASIC_USER` / `ADMIN_BASIC_PASSWORD`

2）安装依赖：

```powershell
uv sync
```

（可选）安装开发依赖并运行本地检查：

```powershell
uv sync --extra dev
uv run ruff check .
uv run ruff format .
uv run pytest
```

3）启动服务：

```powershell
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

## Docker Compose 一键部署（SQLite / PostgreSQL）

1）准备环境变量：

- 将 `.env.example` 复制为 `.env`
- 至少配置：
  - `DATABASE_URL`
  - `ADMIN_BASIC_PASSWORD`
  - `MEMOS_BASE_URL`
  - `MEMOS_ADMIN_TOKEN`（生产必填；本地联调可临时用 `DEV_BYPASS_MEMOS=true`）

2）启动（首次会自动构建镜像并跑 Alembic 迁移）：

- SQLite（默认）：

```powershell
docker compose up -d --build
```

- PostgreSQL：将 `.env` 里的 `DATABASE_URL` 设置为 `postgresql+psycopg://...@postgres:5432/...`（或直接用 `postgresql://...`），并启用 postgres profile：

```powershell
docker compose --profile postgres up -d --build
```

说明：该 profile 会启动仓库内置的 `postgres` 服务（用户名/密码/库名通过 `.env` 里的 `POSTGRES_*` 配置）。

3）查看日志：

```powershell
docker compose logs -f api
```

4）访问：

- 健康检查：`http://localhost:31031/health`
- 管理后台：`http://localhost:31031/admin`

停止：

```powershell
docker compose down
```

（可选）清空 PostgreSQL 数据卷：

```powershell
docker compose down -v
```

## 接口

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /admin`（管理后台首页，未登录会跳转到登录页）
- `GET /admin/login` / `POST /admin/login`（管理后台登录）
- `POST /admin/logout`（退出登录）
- `GET /health`

成功返回示例：

```json
{"code":200,"data":{"token":"...","server_url":"https://memos.example.com"}}
```

## 重要限制与实现说明

- 用户名校验：部分 Memos 部署对用户名校验较严格，后端已限制为 **仅字母数字**（不支持下划线）。
- Token 生成策略：管理员 Token **无权**为“其它用户”直接创建 `accessToken`（会返回 403 `permission denied`），因此后端采用：
  - 先用 `MEMOS_ADMIN_TOKEN` 创建 Memos 用户（密码使用你在 Backend 注册时的密码）
  - 再用该用户的账号密码调用 `POST /api/v1/auth/sessions` 建立会话
  - 最后以该用户身份调用 `POST /api/v1/users/{id}/accessTokens` 生成永久 Token 并返回给 App

## Memos API 兼容说明（重要）

Memos 的 API 版本变动较快，“创建用户/生成 Token”的 endpoint 与 payload 可能因版本不同而不一致。

本项目默认采用“多 endpoint + 多 payload 尝试”的策略，并提供环境变量用于覆写：

- `MEMOS_CREATE_USER_ENDPOINTS`
- `MEMOS_CREATE_TOKEN_ENDPOINTS`

如果注册接口返回 502（通常是 Memos 对接失败），建议你先用 Postman 在当前 Memos 实例上把流程调通，然后把正确的 endpoint 写到 `.env` 里。

另外，如果历史上出现过“用户在 Memos 已创建，但后端因为 token 生成失败而没入库”的半成品数据，可临时开启：`.env` 中 `MEMOS_ALLOW_RESET_PASSWORD_FOR_EXISTING_USER=true`，让后端在注册时对该用户名执行一次密码重置并补发 token（用完建议关闭）。

## 安全提醒

- 后端只保存 `password_hash`（bcrypt）与 `memos_token`，不会明文存储 App 的登录密码。
- `ADMIN_BASIC_PASSWORD`、`MEMOS_ADMIN_TOKEN` 属于敏感信息，务必只在服务器环境变量或 `.env` 中配置，不要提交到公开仓库。

## 数据迁移（Alembic）

引入 Alembic 后，建议按迁移优先的工作流运行：
uv run alembic -c alembic.ini upgrade head

也可以直接使用仓库根目录的 run.bat / stop.bat 一键启动与停止（默认端口 31031）。

## 新增接口（Settings / TODO / Sync）

鉴权方式：Authorization: Bearer <memos_token>

Settings:
- GET  /api/v1/settings
- PUT  /api/v1/settings/{key}
- DELETE /api/v1/settings/{key}

TODO Lists:
- GET    /api/v1/todo/lists
- POST   /api/v1/todo/lists
- PATCH  /api/v1/todo/lists/{list_id}
- DELETE /api/v1/todo/lists/{list_id}
- POST   /api/v1/todo/lists/reorder

TODO Items:
- GET    /api/v1/todo/items
- POST   /api/v1/todo/items
- POST   /api/v1/todo/items/bulk
- PATCH  /api/v1/todo/items/{item_id}
- DELETE /api/v1/todo/items/{item_id}

RRULE Occurrences:
- GET    /api/v1/todo/occurrences?item_id=...&from=YYYY-MM-DDTHH:mm:ss&to=YYYY-MM-DDTHH:mm:ss
- POST   /api/v1/todo/occurrences
- POST   /api/v1/todo/occurrences/bulk
- DELETE /api/v1/todo/occurrences/{occurrence_id}

Sync:
- GET  /api/v1/sync/pull?cursor=0&limit=200
- POST /api/v1/sync/push

RRULE 约定：tzid 固定 Asia/Shanghai；dtstart_local/recurrence_id_local 为 YYYY-MM-DDTHH:mm:ss（无 offset）；后端不展开 RRULE，由客户端展开并通过 occurrences 记录单次例外。

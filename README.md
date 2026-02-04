# 心流云服务后端（Flow Backend）

> 当前版本：以 `pyproject.toml` 为准（示例：`0.4.1`）

Flow Backend 是「心流」客户端的云端后端服务，提供：

1. 用户体系与鉴权：Bearer Token（移动端/脚本）+ Cookie Session（Web SPA）。
2. 云端数据能力：笔记 / 待办 / 设置 / 附件 / 分享 / 通知 / 修订（冲突保留）等。
3. 多端离线同步：v1 + v2 同步接口与冲突处理约定。
4. 可选对接 Memos：注册时创建 Memos 用户并签发 Token；并提供“本地 Notes ↔ Memos”双向同步能力。
5. 管理后台（Admin）：用户管理、设备活跃度追踪等运维能力。

仓库结构：

- 后端（FastAPI）：`src/flow_backend/`
- 用户前端（Next.js）：`web/`（可双端口开发，也可静态导出后由后端同源托管）

---

## 1. 功能总览

### 1.1 鉴权与安全能力

- Bearer Token：`Authorization: Bearer <token>`
  - 当前实现中，Bearer Token **就是用户的 `memos_token`**（保存在本服务数据库中）。
- Cookie Session（Web SPA）：
  - httpOnly Cookie（浏览器 JS 读不到 Cookie 本体）
  - 写请求（POST/PUT/PATCH/DELETE）强制 CSRF（默认 header：`X-CSRF-Token`）
- 限流：登录/注册/Admin 登录均做“尽力而为”的限流（可通过 `.env` 调整）。
- Request ID：支持客户端传入 `X-Request-Id`，服务端在响应头回显（排障必备）。
- 设备追踪：支持通过 header 上报设备 ID/名称，用于管理后台展示最近活跃设备与 IP。

### 1.2 API 版本（v1 / v2）

本服务提供两套 API：

- v1：`/api/v1/*`（主应用，响应 envelope：`{"code":200,"data":...}`）
- v2：`/api/v2/*`（子应用，独立 OpenAPI，并统一错误格式 `ErrorResponse`）

能力覆盖（细节以 `docs/api.zh-CN.md` 为准）：

- Auth：注册/登录/登出（v1）
- Me：当前用户信息 + CSRF token 重取（v1）
- Settings：用户键值配置（v1）
- TODO：清单/任务/复发（v1 + v2）
- Notes：笔记、标签、搜索、软删除/恢复（主要在 v2）
- Revisions：笔记修订与冲突快照（v2）
- Attachments：附件元数据 + 存储（本地目录或 S3/COS）（v2）
- Shares & Public：分享链接、公开访问、匿名评论（可选验证码 token）（v2）
- Notifications：例如评论 @mention 触发通知（v2）
- Sync：多端离线同步（v1 + v2）

### 1.3 Memos 集成（可选）

- 注册时可通过 `MEMOS_ADMIN_TOKEN` 自动在 Memos 创建同名用户，并签发永久 token。
- Notes 与 Memos 双向同步：
  - Memos 作为权威源：当远端与本地同时修改，远端胜出，本地保留 `CONFLICT` 修订用于找回
  - 通过远端内容 hash 与映射表识别对应关系（减少“依赖时钟一致”的问题）
- Memos API 兼容性：
  - 支持用环境变量覆写 endpoint 列表，适配不同 Memos 版本

---

## 2. 服务入口与文档

默认端口：`31031`

- 健康检查：`GET /health`
- 管理后台：`GET /admin`（未登录会跳转登录页）
- v1 OpenAPI：
  - `GET /openapi.json`
  - `GET /docs`
  - `GET /redoc`
- v2 OpenAPI（子应用）：
  - `GET /api/v2/openapi.json`
  - `GET /api/v2/docs`
  - `GET /api/v2/redoc`
  - `GET /api/v2/health`

更完整的客户端对接文档（v1 + v2，含同步协议/冲突处理/分享/附件等）：

- `docs/api.zh-CN.md`
- 架构说明与路线图：`plan.md`
- 客户端对接总指南：`to_app_plan.md`

前端说明：

- `web/README.md`
- `docs/web-dev-and-deploy.md`（专题：Web 联调与部署形态）

---

## 3. 快速开始（推荐：Linux/macOS + uv）

### 3.1 前置依赖

- Python `>=3.11`
- `uv`（Python 环境与依赖管理）
- （可选）Node.js：仅在你需要运行 `web/` 前端或 E2E 时需要

### 3.2 初始化环境变量

```bash
cp .env.example .env
```

本地开发常用推荐值（可以直接写进 `.env` 或临时导出环境变量）：

- `DATABASE_URL=sqlite:///./dev.db`
- `DEV_BYPASS_MEMOS=true`（本地不对接 Memos，直接生成假 token，便于纯后端联调）

### 3.3 安装依赖 & 运行迁移

```bash
uv sync
uv run alembic -c alembic.ini upgrade head
```

（可选）开发依赖 + 代码质量检查：

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format .
uv run pytest
```

### 3.4 启动服务

```bash
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

验证：

- `http://localhost:31031/health`
- `http://localhost:31031/admin`
- `http://localhost:31031/docs`

---

## 4. Web 前端联调（Next.js）

本仓库包含用户前端：`web/`。本地开发常见两种模式：

### 4.1 推荐：Next rewrites 同源（最省心，无需处理 CORS）

目标：浏览器访问 `http://localhost:3000`，同时 `/api/v1/*` 与 `/api/v2/*` 通过 Next rewrites 代理到后端 `31031`。

终端 A（后端）：

```bash
uv sync
uv run uvicorn flow_backend.main:app --host 127.0.0.1 --port 31031 --reload
```

终端 B（前端）：

```bash
cd web
npm ci
npm run dev
```

默认代理规则见：`web/next.config.ts`

- 关闭代理：`NEXT_DISABLE_BACKEND_PROXY=1`
- 覆写后端地址：`BACKEND_BASE_URL=http://localhost:31031`

### 4.2 Cookie 会话 + CSRF（必读）

当你使用 Cookie Session 鉴权时：

- 安全方法（GET/HEAD/OPTIONS）不要求 CSRF
- 写方法（POST/PUT/PATCH/DELETE）必须携带 `X-CSRF-Token`

CSRF token 的获取方式：

- 登录/注册响应：`data.csrf_token`
- SPA 刷新后：调用 `GET /api/v1/me` 获取 `data.csrf_token`

前端已在 `web/src/lib/api/client.ts` 内自动注入写请求的 `X-CSRF-Token`（前提是客户端保存/恢复了 token）。

### 4.3 直接跨域访问（不推荐，但有时需要）

当 Web 与 API 不同源时（例如 `localhost:3000` -> `localhost:31031`），如果你想使用 Cookie Session，需要：

- 后端设置 `CORS_ALLOW_ORIGINS` 为明确 allowlist（不能是 `*`），例如：
  - `CORS_ALLOW_ORIGINS=http://localhost:3000`
- 浏览器请求必须 `credentials: "include"`

（更多细节见 `docs/web-dev-and-deploy.md`）

---

## 5. 生产部署

### 5.1 Docker Compose（一键部署 API）

1）准备 `.env`：

```bash
cp .env.example .env
```

生产建议（关键项）：

- `ENVIRONMENT=production`（开启生产安全校验，并禁用 v2 debug 路由）
- `DATABASE_URL=postgresql+psycopg://...`（生产禁止 sqlite）
- `CORS_ALLOW_ORIGINS` 必须是明确列表（生产禁止 `*`）
- 必须设置强随机值（生产安全校验会拦截默认占位符）：
  - `ADMIN_BASIC_PASSWORD`
  - `ADMIN_SESSION_SECRET`
  - `USER_SESSION_SECRET`
  - `SHARE_TOKEN_SECRET`
- Memos 对接时必须设置：
  - `MEMOS_BASE_URL`
  - `MEMOS_ADMIN_TOKEN`

2）启动（首次会自动构建镜像并执行 Alembic 迁移）：

SQLite（演示/本地）：

```bash
docker compose up -d --build
```

PostgreSQL（推荐）：启用 `postgres` profile（会同时启动内置 postgres 容器）：

```bash
docker compose --profile postgres up -d --build
```

3）查看日志：

```bash
docker compose logs -f api
```

4）访问：

- 健康检查：`http://localhost:31031/health`
- 管理后台：`http://localhost:31031/admin`

停止：

```bash
docker compose down
```

### 5.2 反向代理（推荐：一个公网 Origin）

若你计划使用 Cookie Session（Web），强烈建议用 Nginx/Caddy/Traefik 在最外层提供**单一公网 origin**：

- `/` -> Web（静态站或 Next server）
- `/api/v1/*`、`/api/v2/*`、`/admin` -> 后端

并在后端开启：

- `TRUST_X_FORWARDED_PROTO=true`（TLS 终止在反代时，确保 Secure Cookie 正确）
- `TRUST_X_FORWARDED_FOR=true`（仅在可信反代后启用，用于真实 client IP 与限流/设备统计）

### 5.3 同源静态站（后端托管 `web/out`）

后端启动时会“尽力”挂载静态导出目录到 `/`（仅当存在 `index.html`）：

- 默认目录：仓库内 `web/out`
- 环境变量：
  - 禁用：`FLOW_DISABLE_WEB_STATIC=1`
  - 覆写目录：`FLOW_WEB_OUT_DIR=/abs/path/to/out`

本地构建导出：

```bash
cd web
npm ci
npm run build
```

然后启动后端访问：

- Web：`http://localhost:31031/`
- API：`http://localhost:31031/api/v1/...`、`/api/v2/...`

注意：仓库自带的 `Dockerfile` 默认不会把 `web/out` 打进镜像；若你希望容器内同源托管静态站点，建议：

1. 在镜像构建阶段构建 `web/out` 并 COPY 进镜像，或
2. 通过 volume 把宿主机构建好的 `web/out` 挂载到容器中，并设置 `FLOW_WEB_OUT_DIR`

---

## 6. 环境变量速查（.env）

完整示例见 `.env.example`，这里列“最常用且最关键”的：

- 基础：
  - `ENVIRONMENT=development|production`
  - `DATABASE_URL=sqlite:///./dev.db`（本地）或 `postgresql+psycopg://...`（生产）
  - `LOG_LEVEL=INFO`
- Memos：
  - `MEMOS_BASE_URL`
  - `MEMOS_ADMIN_TOKEN`（注册自动创建用户时必需）
  - `MEMOS_CREATE_USER_ENDPOINTS`、`MEMOS_CREATE_TOKEN_ENDPOINTS`（不同 Memos 版本适配）
  - `MEMOS_ALLOW_RESET_PASSWORD_FOR_EXISTING_USER`（修复半成品用户用，默认 false）
  - `DEV_BYPASS_MEMOS=true|false`（本地开发兜底，生产必须 false）
- CORS / 反代：
  - `CORS_ALLOW_ORIGINS=*`（开发）或 `http://a.com,https://b.com`（生产）
  - `TRUST_X_FORWARDED_FOR=true|false`
  - `TRUST_X_FORWARDED_PROTO=true|false`
- 管理后台：
  - `ADMIN_BASIC_USER`
  - `ADMIN_BASIC_PASSWORD`
  - `ADMIN_SESSION_SECRET`
- 用户 Cookie Session（生产环境必配）：
  - `USER_SESSION_SECRET`
  - `USER_SESSION_COOKIE_NAME`（默认 `flow_session`）
  - `USER_CSRF_HEADER_NAME`（默认 `X-CSRF-Token`）
- 分享：
  - `PUBLIC_BASE_URL`（生成分享链接的外部访问基准 URL）
  - `SHARE_TOKEN_SECRET`
- 附件：
  - `ATTACHMENTS_LOCAL_DIR`（本地存储目录）
  - `ATTACHMENTS_MAX_SIZE_BYTES`
  - S3/COS（可选）：`S3_ENDPOINT_URL`、`S3_BUCKET`、`S3_ACCESS_KEY_ID`、`S3_SECRET_ACCESS_KEY` 等

---

## 7. 测试

### 7.1 后端单测

```bash
uv sync --extra dev
uv run pytest
```

### 7.2 E2E（Playwright）

```bash
cd web
npx playwright test
```

Playwright 会：

- 执行 `npm run build`（静态导出）
- 执行 `alembic upgrade head`
- 启动后端并在同源下跑浏览器用例

---

## 8. 常见问题（Troubleshooting）

- Web UI 404（同源静态托管）：确认存在 `web/out/index.html`（运行 `cd web && npm run build`）。
- 429 / 登录注册被限流：本地并发注册/登录可能触发；可在 `.env` 临时调低/关闭 `AUTH_*_RATE_LIMIT_*`（E2E 会自动覆写为 0）。
- SQLite `database is locked`：避免多个进程同时写同一个 sqlite 文件；停掉占用 DB 的进程后重试。
- 502（注册对接 Memos 失败）：优先用 Postman 在当前 Memos 实例上调通创建用户/签发 token 流程，并把正确 endpoint 写入：
  - `MEMOS_CREATE_USER_ENDPOINTS`
  - `MEMOS_CREATE_TOKEN_ENDPOINTS`
- Cookie Session 跨域不生效：检查 `CORS_ALLOW_ORIGINS` 是否为明确 allowlist（不能 `*`），以及浏览器请求是否 `credentials: "include"`。

---

## 9. Windows 一键启动（可选）

仓库提供 `run.bat` / `stop.bat`（默认端口 `31031`）。Windows 用户可直接使用；Linux/macOS 建议用上文 `uv run uvicorn ...` 的方式启动。

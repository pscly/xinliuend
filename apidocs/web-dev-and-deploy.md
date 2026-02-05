# Web 本地联调与部署（同站点 Cookie 会话 / CSRF）

最后更新：2026-02-05

本文解释如何在本仓库中运行后端 + `web/` 前端进行本地联调，以及如何在生产环境部署成“同站点 / 最好同源”的形态，从而让 **Cookie Session 鉴权 + CSRF** 最稳定、最省心。

仓库默认端口（本地）：

- 后端（FastAPI）：`http://localhost:31031`
- Web（Next dev server）：`http://localhost:3000`

---

## 1) 推荐本地联调：Next rewrites 同源（无需 CORS）

目标：浏览器始终访问 `http://localhost:3000`，但把 `/api/v1/*` 通过 Next rewrites 代理到后端 `http://localhost:31031`。

### 1.1 启动后端（SQLite + 本地开发绕过）

在仓库根目录：

Linux/macOS（bash）：

```bash
cp -f .env.example .env

# 稳定的本地默认值
export DATABASE_URL="sqlite:///./.data/dev.db"
export DEV_BYPASS_MEMOS="true"

uv sync
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

Windows（PowerShell）：

```powershell
Copy-Item .env.example .env -Force

# Stable local defaults
$env:DATABASE_URL = "sqlite:///./.data/dev.db"
$env:DEV_BYPASS_MEMOS = "true"

uv sync
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

验证：

- `http://localhost:31031/health`
- `http://localhost:31031/admin`（后端渲染的管理后台页面）

### 1.2 启动 Web（Next.js）

新开一个终端，在仓库根目录执行：

Linux/macOS（bash）：

```bash
cd web
npm ci

# 可选：显式指定 rewrites 目标后端（默认就是 http://localhost:31031）
# export BACKEND_BASE_URL="http://localhost:31031"

npm run dev
```

Windows（PowerShell）：

```powershell
cd web
npm ci

# Optional: point rewrites to a non-default backend base URL
# $env:BACKEND_BASE_URL = "http://localhost:31031"

npm run dev
```

打开：

- Web：`http://localhost:3000`
- API（被代理）：`http://localhost:3000/api/v1/...`

### 1.3 为什么这种模式下 Cookie 最稳定

`web/next.config.ts` 通过 rewrites 把：

- `/api/v1/*` -> `http://localhost:31031/api/v1/*`

从浏览器角度看，API 就是“同源”（仍然是 `localhost:3000`），因此：

- 不需要配置 CORS（也不会遇到复杂的 preflight/credentials 问题）。
- 后端返回的 `Set-Cookie` 会写入 host 为 `localhost` 的 cookie（**cookie 不依赖端口**）。
- 前端可以稳定使用相对路径请求，例如 `/api/v1/me`。

重要：`/admin` **不会**被 Next 代理。它是后端渲染页面，本地应访问：

- `http://localhost:31031/admin`

---

## 2) Cookie Session + CSRF（必读）

后端同时支持两种鉴权模式：

- Bearer Token：`Authorization: Bearer <token>`（移动端/脚本推荐；不需要 CSRF）
- Cookie Session：httpOnly session cookie（Web SPA 常用；**写请求必须带 CSRF header**）

### 2.1 Session Cookie 关键参数

默认值见 `src/flow_backend/config.py`：

- Cookie 名称：`flow_session`（`USER_SESSION_COOKIE_NAME`）
- Cookie 属性：`HttpOnly`、`SameSite=Lax`、`Path=/`
- `Secure`：当你使用 HTTPS（或反代后启用 `TRUST_X_FORWARDED_PROTO=true`）时会自动启用

### 2.2 CSRF 规则

当你通过 Cookie Session 鉴权时：

- 安全方法（`GET`/`HEAD`/`OPTIONS`）：不要求 CSRF
- 写方法（`POST`/`PUT`/`PATCH`/`DELETE`）：必须携带 CSRF header

Header 名称可配置，默认：

- `X-CSRF-Token`（`USER_CSRF_HEADER_NAME`）

CSRF token 的获取方式：

- `POST /api/v1/auth/login` -> `csrf_token`
- `POST /api/v1/auth/register` -> `csrf_token`

### 2.3 SPA 刷新后的 CSRF 重新获取（rehydration）

因为 session cookie 是 httpOnly，前端 JS 无法直接读取 cookie。

因此页面刷新后，需要通过 API 重新拿到 CSRF：

- `GET /api/v1/me` -> `csrf_token`

推荐客户端流程：

1) 登录/注册成功后，把 `csrf_token` 存在内存（或 sessionStorage）。
2) SPA 启动时（或内存丢失 CSRF 时），调用 `GET /api/v1/me` 重新获取 `csrf_token`。
3) 对每个写请求（POST/PUT/PATCH/DELETE）都带上：`X-CSRF-Token: <csrf_token>`。

### 2.4 Logout（登出）端点注意事项

使用：

- `POST /api/v1/auth/logout`

规则：

- 幂等：即使已经登出也返回 ok。
- 如果当前请求携带了有效 cookie-session，会要求 CSRF（防止跨站强制登出）。
- 如果你使用的是 Bearer Token 鉴权，则该端点不需要 CSRF。

---

## 3) 本地备选：不走 Next 代理，直接跨域（CORS + cookies）

当你需要验证“真实跨域行为”（或你计划把 Web 与 API 部署到不同 origin）时，可以使用这个模式。

### 3.1 关闭 Next rewrites

在运行 `npm run dev` 的终端里设置环境变量：

Linux/macOS（bash）：

```bash
export NEXT_DISABLE_BACKEND_PROXY="1"
```

Windows（PowerShell）：

```powershell
$env:NEXT_DISABLE_BACKEND_PROXY = "1"
```

注意：

- 关闭 rewrites 后，浏览器请求相对路径 `/api/v1/...` 只会打到 Web origin（`localhost:3000`），不会到后端。
- 跨域模式下，前端请求必须显式指向后端 origin，例如 `http://localhost:31031/api/v1/...`。

### 3.2 配置后端 CORS（为了跨域 Cookie Session）

后端使用 Starlette `CORSMiddleware`，并根据 `CORS_ALLOW_ORIGINS` 决定是否允许跨域携带 cookie：

- 如果 `CORS_ALLOW_ORIGINS='*'`：`allow_credentials` 会被强制为 `false`（跨域 cookie 不会工作）
- 如果 `CORS_ALLOW_ORIGINS` 是明确 allowlist（逗号分隔、且不包含 `*`）：会启用 `allow_credentials=true`

示例：允许本地 Web origin：

Linux/macOS（bash）：

```bash
# 关键：需要 cookie 时，CORS_ALLOW_ORIGINS 不能是 '*'
export CORS_ALLOW_ORIGINS="http://localhost:3000"

uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

Windows（PowerShell）：

```powershell
# IMPORTANT: no '*' when you need cookies.
$env:CORS_ALLOW_ORIGINS = "http://localhost:3000"

uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

浏览器端 `fetch` 要求：

- 必须带 `credentials: "include"`（仓库默认的 `web/src/lib/api/client.ts` 已处理）
- Cookie-session + 写请求：必须带 `X-CSRF-Token`

常见坑：

- host 必须一致：`http://localhost:3000` 与 `http://127.0.0.1:3000` 是不同 origin。
- Cookie `SameSite=Lax` 更适合“同站点”部署（例如同域不同端口/子域）。如果是完全跨站点（不同顶级域名），cookie 鉴权大概率行不通（除非调整 cookie 策略）。

---

## 4) 生产部署形态（务必保证 /admin 由后端接管）

关键要求：`/admin` 是后端渲染的 HTML 管理后台，必须 **不要**被前端 SPA/静态站接管。

### 4.1 推荐：反向代理（一个公网 origin）

在 Nginx/Caddy/Traefik 前置反代，让浏览器只看到一个公网 origin：

- `/` -> Web（Next 运行或静态文件）
- `/api/v1/*` -> 后端
- `/admin` -> 后端（**不要让前端覆盖**）

收益：

- 无 CORS
- Cookie Session 最稳定
- TLS 可以在反代层终止

如果 TLS 在反代层终止，后端建议启用：

- `TRUST_X_FORWARDED_PROTO=true`（让后端正确设置 `Secure` cookie）

更完整的部署指南见：`apidocs/deploy.zh-CN.md`。

### 4.2 静态导出（SPA） vs 运行 Next Server

如果你希望纯静态 SPA，可以使用 Next static export（build-time HTML + assets）并由任意静态服务器托管。

需要注意：

- 静态导出不支持 Next 的某些 server-only 特性（例如 server 侧 `cookies()`/`headers()` 依赖）
- 更推荐前端用客户端请求 + cookie-session（`credentials: "include"`）

如果你运行 Next server（`npm run build` + `npm run start`），通常仍建议在前面放一个反向代理，用于保证 `/admin` 与 `/api/*` 正确路由到后端。

### 4.3 单服务同源：后端托管 `web/out`（最省心）

仓库支持一种“无需外部反代也能同源”的形态：

- Web 使用 Next 静态导出，产物在 `web/out/`
- 只跑后端服务：后端会 best-effort 把 `web/out` 挂载到 `/`

步骤 1：构建静态导出

Linux/macOS（bash）：

```bash
cd web
npm ci
npm run build
```

Windows（PowerShell）：

```powershell
cd web
npm ci
npm run build
```

期望输出：

- `web/out/`（例如 `web/out/index.html`）

步骤 2：运行后端

Linux/macOS（bash）：

```bash
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031
```

Windows（PowerShell）：

```powershell
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031
```

步骤 3：访问

- Web UI：`http://localhost:31031/`
- API：`http://localhost:31031/api/v1/...`
- Admin：`http://localhost:31031/admin`

备注：

- 路由优先级已保证：`/api/*` 与 `/admin` 会先注册，再挂载静态站点。
- 静态挂载是 best-effort：仅当 `web/out/index.html` 存在时才会挂载。
- `npm run build` 时 Next 可能提示 rewrites 在 `output: 'export'` 下被忽略（正常；rewrites 主要用于 `npm run dev`）。
- 禁用静态挂载：`FLOW_DISABLE_WEB_STATIC=1`
- 覆盖导出目录：`FLOW_WEB_OUT_DIR=/abs/or/relative/path`

---

## 5) 环境变量速查（本地 + E2E 稳定性）

后端（本地/CI 常用）：

- `DATABASE_URL=sqlite:///./.data/dev.db`
- `DEV_BYPASS_MEMOS=true`（仅本地开发）

后端（跨域 Cookie Session 才需要）：

- `CORS_ALLOW_ORIGINS=http://localhost:3000`（明确 allowlist；不要用 `*`）

Web（Next rewrites）：

- `BACKEND_BASE_URL=http://localhost:31031`（仅影响 Next rewrites 目标）
- `NEXT_DISABLE_BACKEND_PROXY=1`（关闭 rewrites）
- `NEXT_PUBLIC_APP_ORIGIN=http://localhost:3000`（部署时作为“应用自身 origin”提示）

---

## 6) 快速手工自测（可复制粘贴）

以下示例假设你使用“推荐本地联调模式”（API 通过 `localhost:3000` rewrites 代理）。

登录并保存 cookie：

Linux/macOS（bash）：

```bash
curl -c .tmp.cookies.txt -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"pass1234"}' \
  http://localhost:3000/api/v1/auth/login
```

Windows（PowerShell）：

```powershell
curl -c .tmp.cookies.txt -H "Content-Type: application/json" `
  -d '{\"username\":\"demo\",\"password\":\"pass1234\"}' `
  http://localhost:3000/api/v1/auth/login
```

刷新后重新获取 CSRF token（cookie-session）：

Linux/macOS（bash）：

```bash
curl -b .tmp.cookies.txt http://localhost:3000/api/v1/me
```

Windows（PowerShell）：

```powershell
curl -b .tmp.cookies.txt http://localhost:3000/api/v1/me
```

登出（如果 cookie-session 有效，需要 CSRF）：

Linux/macOS（bash）：

```bash
# 把 <csrf> 替换为 /api/v1/me 或 login 响应里的 csrf_token
curl -b .tmp.cookies.txt -H "X-CSRF-Token: <csrf>" -X POST \
  http://localhost:3000/api/v1/auth/logout
```

Windows（PowerShell）：

```powershell
# Replace <csrf> with the token from /api/v1/me or login response
curl -b .tmp.cookies.txt -H "X-CSRF-Token: <csrf>" -X POST http://localhost:3000/api/v1/auth/logout
```

---

## 7) Troubleshooting（常见问题）

- `http://localhost:31031/` 返回 404：你可能还没构建静态导出。执行 `cd web && npm ci && npm run build` 并确认 `web/out/index.html` 存在。
- Cookie 不生效 / 登录循环：请保持 host 一致。`localhost` 与 `127.0.0.1` 是不同 cookie host。
- `/admin` 页面不对：请访问后端 origin：`http://localhost:31031/admin`（它不是前端静态导出的一部分）。


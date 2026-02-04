# 部署指南（Docker Compose + 宝塔 Nginx）

最后更新：2026-02-04

本文面向“把服务跑起来”的运维/开发同学，目标是：**Web + API + /admin 统一一个公网 Origin**，从而让 Cookie Session / CSRF 最稳定、CORS 最简单。

> 结论先行：推荐用 Docker Compose 部署后端（镜像内已内置 `web/out` 静态导出），再用宝塔 Nginx 统一反代到后端端口即可。

---

## 0. 概念与约定（必读）

本项目现在是“后端 + Web 前端”同仓库形态。要把 Cookie Session（Web 登录态）部署稳定，关键是理解下面几条约定。

### 0.1 同源 / 跨域是什么（为什么强烈推荐同源）

- **同源（推荐）**：浏览器看到的只有一个公网 origin（例如 `https://u.pscly.cn`），Web UI 与 API 都在这个 origin 下：
  - `/`：Web UI
  - `/api/*`：API
  - `/admin`：后端管理后台
  - 优点：Cookie 最稳定、无需 CORS、前端请求可以一直用相对路径 `/api/...`。
- **跨域（不推荐）**：Web UI 与 API 是不同 origin（不同域名/端口/协议）。
  - 要用 Cookie Session 时，必须配置 CORS allowlist + `credentials: include`，还会受到 `SameSite` 策略影响，运维成本更高。

对移动端/桌面端（非浏览器）客户端同样建议：

- 直接把 **Flow Backend 的公网 origin** 作为客户端 Base URL（例如 `https://xl.pscly.cc`），请求路径按 `/api/v1/...`、`/api/v2/...` 拼接即可（详见 `to_app_plan.md`）。

### 0.2 路由分工：/admin 为什么不会和前端冲突

约定的路由职责：

- `/api/v1/*`、`/api/v2/*`：后端 API
- `/admin`：**后端渲染**的运维管理后台（Jinja/模板页）
- `/`：用户 Web UI（Next.js 静态导出）

当前仓库的 `web/` **没有实现** `/admin` 路由；前端只在设置页提供跳转链接到后端 `/admin`，并提供一个“应用内管理设置页”路径：`/settings/admin`（不占用 `/admin`）。

为什么同源形态下不会冲突：

- 后端先注册 `/api/*` 与 `/admin`，再把静态站 mount 到 `/`，因此 `/admin` 永远由后端优先命中，不会被静态站覆盖。

为什么 Nginx 静态直出形态下也能不冲突：

- 你必须把 `location /admin` 与 `location /api/` 写在 `location /`（`try_files ... /index.html`）之前，避免被 SPA fallback 吃掉。

### 0.3 鉴权快速记忆：Bearer vs Cookie Session（以及 CSRF）

- **Bearer Token**（移动端/脚本推荐）：`Authorization: Bearer <token>`，无 CSRF。
- **Cookie Session**（Web SPA）：httpOnly Cookie；**写请求必须带 CSRF header**（默认 `X-CSRF-Token`）。
- 只要你做了“同源”，通常就不需要专门折腾跨域 CORS；跨域 Cookie 的复杂度会显著上升。

### 0.4 数据持久化约定（你要备份哪里）

容器内持久化目录统一收敛到：

- `/app/.data`

Docker Compose 默认 bind mount：

- 宿主机 `./data` -> 容器 `/app/.data`

因此：

- SQLite（仅本地/演示）建议写到：`sqlite:///./.data/dev.db`
- 附件/本地对象存储建议写到：`.data/attachments`
- 备份/迁移时，优先关注宿主机 `./data/` 目录（以及数据库若使用外置 PostgreSQL 则按库备份）。

---

## 1. 推荐形态：同源（后端托管 `web/out`）

该仓库的 `web/` 使用 Next.js 静态导出（`output: "export"`），产物在 `web/out/`。

后端在启动时会“尽力”挂载该目录到 `/`（仅当存在 `index.html`），并保持路由优先级：

- `/api/v1/*`、`/api/v2/*`：后端 API
- `/admin`：后端渲染的管理后台（**不要让前端覆盖**）
- `/`：静态 Web UI（同源）

### 1.1 目录建议（宿主机）

推荐把仓库放在：

```text
~/dockers/xinliuend/
  docker-compose.yml
  .env
  data/              # 宿主机持久化目录（compose bind mount）
```

其中 `docker-compose.yml` 默认会把宿主机 `./data` 映射到容器 `/app/.data`：

- 附件/本地对象存储默认落在：`/app/.data/attachments`
- SQLite（仅本地演示）可落在：`/app/.data/dev.db`

### 1.2 启动（Docker Compose）

```bash
cd ~/dockers/xinliuend
cp .env.example .env
mkdir -p data

# SQLite（演示/本地）
docker compose up -d --build

# PostgreSQL（推荐；启用 postgres profile）
docker compose --profile postgres up -d --build
```

访问（未加反代时）：

- Web：`http://<server-ip>:31031/`
- API：`http://<server-ip>:31031/api/v1/...`、`/api/v2/...`
- Admin：`http://<server-ip>:31031/admin`

> 说明：生产环境不建议直接暴露 31031，请用 Nginx 统一入口并启用 HTTPS。

### 1.3 关键环境变量（反代/TLS 场景必读）

当你在 Nginx 上终止 TLS（浏览器访问 https，但后端收到的是 http）时：

- 后端建议开启：`TRUST_X_FORWARDED_PROTO=true`
  - 作用：让后端正确判断外部是 HTTPS，从而设置 `Secure` Cookie
- 仅在可信反代后开启：`TRUST_X_FORWARDED_FOR=true`
  - 作用：使用真实 client IP 做限流/设备统计

同时建议把分享链接外部基准设置正确：

- `PUBLIC_BASE_URL=https://你的域名`

---

## 2. 宝塔 Nginx 反代示例（一个公网 Origin）

你提到的宝塔 Nginx 主配置路径通常是：

- `/www/server/nginx/conf/nginx.conf`

不同宝塔版本/站点可能拆分到 vhost 文件；以下给出一个“单站点反代到后端端口”的示例，你可以按实际站点配置位置落地。

### 2.1 示例：全站反代到后端（最简单）

```nginx
server {
    listen 80;
    server_name u.pscly.cn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name u.pscly.cn;

    # 证书路径请按宝塔实际生成的证书文件填写
    # ssl_certificate     /path/to/fullchain.pem;
    # ssl_certificate_key /path/to/privkey.pem;

    # 附件上传：按需调大（需 >= 后端 ATTACHMENTS_MAX_SIZE_BYTES 对应大小）
    client_max_body_size 50m;

    location / {
        proxy_pass http://127.0.0.1:31031;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

对应后端 `.env` 建议：

```bash
TRUST_X_FORWARDED_PROTO=true
TRUST_X_FORWARDED_FOR=true
PUBLIC_BASE_URL=https://u.pscly.cn
```

优点：

- 配置最少：Web/UI/API/Admin 全部同源
- Cookie Session 最稳定，无需纠结 CORS

---

## 3. 可选：Nginx 静态直出 `web/out`，API/Admin 走反代

当你希望静态资源由 Nginx 直接服务（更高性能、更可控缓存）时，可以让 Nginx 提供 `/`，而把 `/api/*` 与 `/admin` 反代到后端。

前提：

- 你需要在宿主机生成并持有 `web/out/`（例如在服务器执行 `cd web && npm ci && npm run build`），或通过 CI 把 `web/out` 同步到服务器目录。

示例（请把 `root` 改成你实际的绝对路径）：

```nginx
server {
    listen 443 ssl http2;
    server_name u.pscly.cn;

    # ssl_certificate / ssl_certificate_key ...

    location /api/ {
        proxy_pass http://127.0.0.1:31031;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /admin {
        proxy_pass http://127.0.0.1:31031;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        root /root/dockers/1auto/xinliuend/web/out;
        try_files $uri $uri/ /index.html;
    }
}
```

注意：

- `/admin` 必须走后端渲染（不要被 `try_files ... /index.html` 吃掉）
- 仍建议开启 `TRUST_X_FORWARDED_PROTO=true`

---

## 4. 构建加速 / 拉取限流（可选）

如果服务器拉取基础镜像出现网络问题或 Docker Hub 限流，可以通过 `docker-compose.yml` 的 build args 做最小改动的切换：

- `NODE_IMAGE`：Node 基础镜像（用于构建 `web/out`）
- `PYTHON_IMAGE`：Python 基础镜像（运行后端）
- `NPM_REGISTRY`：npm registry（用于 `npm ci`）
- `PIP_INDEX_URL` / `PIP_TRUSTED_HOST`：pip/uv 下载源（用于 Python 依赖）

用法示例（二选一）：

1）临时环境变量（一次性）：

```bash
NODE_IMAGE=你的镜像加速地址/node:20-alpine \
NPM_REGISTRY=https://你的-npm-镜像 \
docker compose up -d --build
```

2）写入 `.env`（长期）：

```bash
# 追加到 .env（注意：这是 compose 变量插值，不是后端运行时配置）
NODE_IMAGE=你的镜像加速地址/node:20-alpine
NPM_REGISTRY=https://你的-npm-镜像
```

---

## 5. 部署规范（Checklist）

### 5.1 目录与文件规范（推荐落盘位置）

推荐目录结构：

```text
~/dockers/xinliuend/
  docker-compose.yml
  .env
  data/
```

规范要点：

- `data/` 必须存在且可写（否则附件/SQLite 会失败）。
- `data/` 属于运行数据，不应提交到 git；备份时重点关注该目录。

### 5.2 生产 `.env` 必改项（最低限度）

建议至少确认这些：

- `ENVIRONMENT=production`
- `PUBLIC_BASE_URL=https://你的域名`
- 生产环境务必替换为强随机值（默认占位符会被安全校验拦截）：
  - `ADMIN_BASIC_PASSWORD`
  - `ADMIN_SESSION_SECRET`
  - `USER_SESSION_SECRET`
  - `SHARE_TOKEN_SECRET`
- Memos 集成若启用：
  - `MEMOS_BASE_URL`
  - `MEMOS_ADMIN_TOKEN`
- `DEV_BYPASS_MEMOS`：生产必须为 `false`
- `CORS_ALLOW_ORIGINS`：生产建议写成明确 allowlist（即使你同源，也可以只允许你的域名）

### 5.3 反代规范（TLS 终止在 Nginx）

- Nginx 必须设置：`X-Forwarded-Proto: $scheme`
- 后端建议开启：`TRUST_X_FORWARDED_PROTO=true`（让 Secure Cookie 判断正确）
- 仅在可信反代后开启：`TRUST_X_FORWARDED_FOR=true`
- 按需设置：`client_max_body_size`（上传附件用）

### 5.4 验收清单（上线后 1 分钟自检）

- `/health` 返回 `{"ok": true}`
- `/` 能打开 Web UI（不是 404）
- `/admin` 能打开后端管理后台（不是前端页面）

### 5.5 常见误区（排障最快的几条）

- **`/admin` 打开的是前端页面**：Nginx 静态直出模式下，`location /` 抢先匹配了；把 `location /admin` 放到 `location /` 之前。
- **跨域 Cookie 不生效**：`CORS_ALLOW_ORIGINS='*'` 时 cookies 不能跨域；需要明确 allowlist 且前端 `credentials: "include"`。
- **HTTPS 下 Cookie 没有 Secure / 登录状态不稳**：TLS 终止在反代，但没开 `TRUST_X_FORWARDED_PROTO=true` 或没传 `X-Forwarded-Proto`。

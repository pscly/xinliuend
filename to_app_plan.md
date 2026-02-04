# 客户端对接总指南（to_app_plan.md）

最后更新：2026-02-04

本文面向 Android / iOS / Web 客户端开发，目标是让客户端用最少的分叉成本接入 Flow Backend 的现有能力。

> 重要说明：
>
> - “接口全量字段/同步协议/冲突细节”请以 `apidocs/api.zh-CN.md` 为准。
> - 本文提供：对接路径、关键约定、错误处理、以及常见坑位提示。

---

## 0. 术语与地址

- **Flow Backend**：本仓库提供的后端服务（示例：`https://flow-backend.example.com`）
- **Memos Server（可选）**：外部 Memos 实例（示例：`https://memos.example.com`）
- **Flow Access Token（Bearer）**：客户端调用 Flow Backend 时放在 `Authorization` 里的 token
  - 当前实现中，该 token 存储在服务端数据库字段名为 `memos_token`
  - 若启用了 Memos 集成，该 token 往往也同时是一个可用于 Memos 的 access token（取决于配置）

生产环境示例（仅示例，实际以你的部署域名为准）：

- `https://xl.pscly.cc`（推荐一个公网 origin：Web UI + API + /admin 同域）

---

## 1. 推荐对接路线（分阶段，最稳妥）

### 阶段 A：先把“登录态”打通（必须）

目标：用户用账号密码在 Flow Backend 注册/登录，拿到 Bearer token，并安全持久化。

- 注册：`POST /api/v1/auth/register`
- 登录：`POST /api/v1/auth/login`
- 登出：`POST /api/v1/auth/logout`

服务端成功响应（v1 envelope）：

```json
{
  "code": 200,
  "data": {
    "token": "<flow_access_token>",
    "server_url": "https://memos.example.com",
    "csrf_token": "<csrf>"
  }
}
```

字段解释：

- `token`：客户端后续调用 Flow Backend 的 Bearer token（必须保存）
- `csrf_token`：仅当你使用 Cookie Session（Web SPA）时需要；移动端一般可忽略
- `server_url`：当前实现中为 `MEMOS_BASE_URL`（偏兼容字段）
  - 如果你的客户端仍保留“直连 Memos（旧模式）”，可把它作为默认 Memos 地址
  - 如果你的客户端只调用 Flow Backend，可忽略该字段

### 阶段 B：逐步切换业务接口到 Flow Backend（推荐）

建议新客户端/新版本把数据能力逐步迁移到 Flow Backend 的 v2 接口：

- Notes：`/api/v2/notes*`
- Attachments：`/api/v2/notes/{note_id}/attachments`、`/api/v2/attachments/{id}`
- TODO：`/api/v2/todo/*`
- Sync：`/api/v2/sync/*`
- Shares/Public/Notifications/Revisions：按需启用

### 阶段 C：可选对接 Memos（不强制）

如果你希望“Flow Backend ↔ Memos”双向同步：

- 这是服务端能力，客户端照常调用 Flow Backend
- Memos 只作为外部集成（注册创建用户、或 Notes 同步）

---

## 2. Base URL 与鉴权

### 2.1 Base URL

移动端/桌面端客户端（App）推荐只配置一个地址：Flow Backend 的**公网 origin**，例如：

- `FLOW_BACKEND_BASE_URL=https://xl.pscly.cc`（示例）

然后按固定前缀拼接：

- v1：`{FLOW_BACKEND_BASE_URL}/api/v1/...`
- v2：`{FLOW_BACKEND_BASE_URL}/api/v2/...`
- 健康检查：`{FLOW_BACKEND_BASE_URL}/health`

> 建议：客户端把 Base URL 标准化（去掉末尾 `/`），避免出现双斜杠 `//api/v1/...`。

如果你的客户端仍保留“直连 Memos（旧模式）”，则可能需要同时配置两个 URL：

1) `FLOW_BACKEND_BASE_URL`（必需）：Flow 后端地址
2) `MEMOS_BASE_URL`（可选）：仅当你仍保留“直连 Memos”模式才需要

### 2.2 Bearer Token（移动端推荐）

除注册/登录/公开分享等接口外，调用 Flow Backend 时统一使用：

```http
Authorization: Bearer <token>
```

其中 `<token>` 来自：

- `POST /api/v1/auth/register` → `data.token`
- `POST /api/v1/auth/login` → `data.token`

### 2.3 Cookie Session + CSRF（Web SPA 才需要）

Web SPA 如果采用 Cookie Session：

- Cookie 为 httpOnly，前端 JS 读不到
- 对写请求（POST/PUT/PATCH/DELETE）必须带 CSRF header（默认 `X-CSRF-Token`）

CSRF token 获取：

- 登录/注册响应：`data.csrf_token`
- SPA 刷新后：`GET /api/v1/me` → `data.csrf_token`

移动端一般不建议走 Cookie Session，直接 Bearer 即可。

### 2.4 移动端典型请求示例（建议照抄）

下面以生产域名 `https://xl.pscly.cc` 为例，展示最常见的 v1/v2 调用方式。

#### 2.4.1 登录（v1）

请求：

```http
POST https://xl.pscly.cc/api/v1/auth/login
Content-Type: application/json
X-Request-Id: <uuid>
X-Device-Id: <stable-device-id>      # 可选但推荐
X-Device-Name: <device-model/name>   # 可选但推荐

{"username":"demo","password":"pass1234"}
```

响应（成功时，v1 envelope）：

```json
{
  "code": 200,
  "data": {
    "token": "<flow_access_token>",
    "server_url": "https://memos.example.com",
    "csrf_token": "<csrf>"
  }
}
```

移动端处理要点：

- **保存 `data.token`**（后续所有受保护接口都要带 `Authorization: Bearer ...`）
- `csrf_token` 一般可忽略（主要给 Web Cookie Session 用）

#### 2.4.2 调用 v2 业务接口（Bearer）

示例：获取 v2 健康检查：

```http
GET https://xl.pscly.cc/api/v2/health
Authorization: Bearer <flow_access_token>
X-Request-Id: <uuid>
```

示例：拉取 Notes 列表（v2）：

```http
GET https://xl.pscly.cc/api/v2/notes?limit=50&offset=0
Authorization: Bearer <flow_access_token>
X-Request-Id: <uuid>
```

示例：拉取 TODO 列表（v2）：

```http
GET https://xl.pscly.cc/api/v2/todo/items?limit=200&offset=0
Authorization: Bearer <flow_access_token>
X-Request-Id: <uuid>
```

示例：获取当前用户（v1）：

```http
GET https://xl.pscly.cc/api/v1/me
Authorization: Bearer <flow_access_token>
X-Request-Id: <uuid>
```

你也可以用 OpenAPI 快速生成/校验客户端对接：

- v1 OpenAPI：`GET https://xl.pscly.cc/openapi.json`
- v2 OpenAPI：`GET https://xl.pscly.cc/api/v2/openapi.json`

> 提示：v1/v2 的“成功/错误格式”不同，客户端实现时建议按 path 前缀做解包与错误解析分流（详见本文第 4 章与 `apidocs/api.zh-CN.md`）。

---

## 3. 通用请求头约定（强烈建议全部客户端都加上）

### 3.1 X-Request-Id（排障必备）

客户端每个请求建议生成一个 `X-Request-Id`（uuid/雪花/随机字符串均可）：

```http
X-Request-Id: 2a8f0c6a-...
```

服务端会在响应头回显同名 header，用于日志定位。

### 3.2 设备信息（用于管理后台设备活跃度）

客户端建议上报：

- 设备 ID（尽量稳定）：`X-Flow-Device-Id` 或 `X-Device-Id`
- 设备名称（展示用）：`X-Flow-Device-Name` 或 `X-Device-Name`

---

## 4. 错误处理（必须按 v1/v2 区分）

### 4.1 v1（/api/v1）错误格式

v1 成功响应是 `{"code":200,"data":...}`，但错误多数是 FastAPI 默认：

- `{"detail":"..."}`
- 或 `{"detail": {...} }`

### 4.2 v2（/api/v2）错误格式：统一 ErrorResponse

v2 所有非 2xx 基本都返回：

```json
{
  "error": "validation_error|unauthorized|forbidden|conflict|rate_limited|...",
  "message": "human readable message",
  "request_id": "..."
}
```

客户端建议策略：

1. 永远展示/上报 `request_id`（或响应头 `X-Request-Id`）
2. 遇到 `409 conflict`：
   - 优先看 `details.server_snapshot` 是否存在
   - 能自动合并则合并后重试；否则提示用户处理冲突
3. 遇到 `429 rate_limited`：
   - 读取响应头 `Retry-After`（秒）
   - 退避（backoff）+ 抖动（jitter）后重试

---

## 5. 数据同步（离线/多端）

同步是最容易踩坑的模块，推荐做法：

1. 客户端本地维护一份离线数据与操作队列
2. 周期性执行：
   - Pull：拉取服务端变更（cursor/分页）
   - Push：上送本地变更（事件/增量）
3. 冲突时：
   - 不要无脑覆盖
   - 根据服务端返回的 `server_snapshot`（如果有）做合并或提示用户

关键字段（LWW）：

- 多数写入接口都需要 `client_updated_at_ms`
- 客户端必须保证它单调递增（至少同一条记录的更新要递增）

注意：

- v2 同步中，若资源已 tombstone（软删除），upsert 会被拒绝为 conflict，需要显式 restore（具体见 `apidocs/api.zh-CN.md` 的 v2 Sync 章节）。

---

## 6. Notes / Attachments / TODO（接口选择建议）

### 6.1 Notes（推荐走 v2）

基础能力（示例）：

- 创建：`POST /api/v2/notes`
- 列表：`GET /api/v2/notes?limit=...&offset=...`
- 更新：`PATCH /api/v2/notes/{note_id}`
- 删除：`DELETE /api/v2/notes/{note_id}?client_updated_at_ms=...`
- 恢复：`POST /api/v2/notes/{note_id}/restore`

### 6.2 Attachments（v2）

- 上传到某条 note：
  - `POST /api/v2/notes/{note_id}/attachments`（multipart/form-data，字段名 `file`）
- 下载：
  - `GET /api/v2/attachments/{attachment_id}`

注意：

- 单文件上限由后端 `ATTACHMENTS_MAX_SIZE_BYTES` 控制（超过返回 413）

### 6.3 TODO（v1/v2 并存，推荐新客户端走 v2）

- v1 中部分时间字段使用“本地时间字符串”：
  - `YYYY-MM-DDTHH:mm:ss`（无时区 offset）
- v2 支持 `tzid`（默认 `Asia/Shanghai`，可通过后端配置）

---

## 7. 安全与隐私（客户端必须遵守）

- 不要在日志里打印 token / cookie / CSRF
- 所有请求必须走 HTTPS（生产）
- 建议对账号/密码输入做基础校验与节流，避免误触触发限流（429）
- 错误提示要用户可理解，不要直接把服务端堆栈/内部信息展示给用户

---

## 8. QA / 自测验收清单（建议）

1. 注册/登录：成功后能用 Bearer token 调用任意受保护接口（例如 `GET /api/v1/me` 或 `GET /api/v2/notes`）。
2. 限流：连续错误登录触发 429 时，客户端按 `Retry-After` 正确退避。
3. 同步：两台设备交替修改同一条数据时能正确处理 409 conflict（合并/提示）。
4. 设备追踪：携带 device headers 后，Admin 能看到设备活跃度变化（以页面为准）。
5. 附件：上传/下载正常；超过大小上限返回 413 且客户端提示合理。

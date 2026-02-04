# 项目说明与路线图：心流云服务（Flow Cloud / Flow Backend）

最后更新：2026-02-04

本文用于替代早期的 “Auth Only” 规划，面向项目维护者/客户端开发者，给出：

1. 当前已实现能力（以代码为准）
2. 系统架构与关键设计约定
3. 开发/部署建议与风险点
4. 后续路线图（可选增强，不代表已交付）

> 说明：完整 API 细节与同步协议请看 `apidocs/api.zh-CN.md`。本文更偏“宏观架构与工程化说明”。

---

## 1. 总体目标（现在的项目在解决什么问题）

Flow Backend 不是单纯的“注册/登录换 token”，而是一个完整的云端后端：

- 统一用户体系与鉴权（移动端/脚本用 Bearer，Web 用 Cookie Session）
- 支持笔记 / 待办 / 设置 / 附件 / 分享 / 通知 / 修订（冲突保留）
- 支持多端离线同步（v1 + v2 两套协议/接口）
- 可选对接 Memos：
  - 注册阶段可自动在 Memos 创建用户并签发永久 token
  - Notes 可与 Memos 双向同步（Memos 作为权威源）
- 提供 Admin 控制台（运维管理/设备追踪/禁用账号等）

---

## 2. 系统架构（组件关系）

### 2.1 逻辑组件

```text
Android / iOS / Web SPA
        |
        | HTTPS (Bearer Token / Cookie Session)
        v
Flow Backend (FastAPI)
  |-- 数据库：SQLite（本地）/ PostgreSQL（生产）
  |-- 对象存储：本地目录（默认）/ S3 或 COS（可选）
  |-- Admin 控制台（Jinja2 模板渲染）
  |
  +-- [可选] Memos 集成：
       - 注册：创建用户/签发 token
       - Notes：双向同步（远端权威）
```

### 2.2 仓库结构（你应该从哪里看起）

- 后端代码：`src/flow_backend/`
  - v1：主应用（`/api/v1`）
  - v2：子应用（`/api/v2`，独立 OpenAPI）
- 前端代码：`web/`
  - 本地开发可用 Next rewrites 代理后端（同源体验更好）
  - 生产可静态导出到 `web/out` 并由后端同源托管（可选）
- 文档：
  - API 总文档：`apidocs/api.zh-CN.md`
  - Web 联调/部署专题：`docs/web-dev-and-deploy.md`

---

## 3. 核心模块与能力地图（按“你能用什么”来分类）

### 3.1 鉴权（Auth / Session / CSRF）

接口（v1）：

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/me`（刷新 CSRF token 的“取票口”）

鉴权方式：

1) Bearer Token（移动端/脚本推荐）

```
Authorization: Bearer <token>
```

2) Cookie Session（Web SPA 推荐）

- Cookie 为 httpOnly，JS 不可读
- 写请求需要 CSRF header（默认 `X-CSRF-Token`）
- CSRF token 在登录/注册时下发；页面刷新后可通过 `/api/v1/me` 重取

关键设计点：

- 当前实现中，Bearer Token 使用的是用户的 `memos_token` 字段（因此“token”既可用于后端鉴权，也可能用于 Memos，取决于你是否启用 Memos 集成）。
- `DEV_BYPASS_MEMOS=true` 时会生成 `dev-...` 假 token，仅用于开发测试（不可用于 Memos）。

### 3.2 v1 / v2 API 组织方式

- v1（主应用）：更偏“早期协议/兼容层”，响应 envelope 统一为 `{"code":200,"data":...}`
- v2（子应用）：更偏“新能力与长期演进”，具有：
  - 独立 OpenAPI
  - 统一错误格式 `ErrorResponse`
  - 更清晰的资源模型（Notes / Attachments / Shares / Public / Notifications / Revisions / TODO / Sync）

### 3.3 Notes（笔记）与搜索

v2 Notes 以 Flow Backend 自己的数据库为主存：

- CRUD：创建/列表/详情/更新/删除/恢复
- Tags：标签与笔记关联（服务端维护 Tag 表与 NoteTag 关系）
- Search：按关键字/标签过滤（具体查询能力见 API 文档与实现）
- Revisions：保存 NORMAL/CONFLICT 修订，尤其用于冲突找回

### 3.4 TODO（待办）

TODO 同时存在 v1 与 v2：

- v1：历史兼容与同步协议的早期形态
- v2：更规范的资源与错误结构，并支持 `tzid`（默认 `Asia/Shanghai`，可配置）

复发任务约定：

- v1 对 RRULE 的部分字段使用本地时间字符串（固定格式 `YYYY-MM-DDTHH:mm:ss`）
- 服务端不展开 RRULE（由客户端展开），服务端只提供 occurrences 记录“单次例外/完成/取消”等

### 3.5 Sync（离线同步）

同步设计理念：

- **LWW（Last-Write-Wins）**：多数资源以 `client_updated_at_ms` 作为“新旧”判断
- **钳制超前时间**：服务端会对明显超前的客户端时间做一定限制，降低“未来时间把所有数据覆盖”的风险
- **冲突可恢复**：v2 中常见冲突会给出 `details.server_snapshot`，让客户端提示/合并
- **软删除与 tombstone**：某些资源被软删除后，sync upsert 会被拒绝为 conflict，需要显式 restore

强烈建议：

- 客户端严格遵循 `apidocs/api.zh-CN.md` 中对 `client_updated_at_ms`、cursor、tombstone 的约定。

### 3.6 Attachments（附件）

v2 支持附件上传/下载：

- 上传：`POST /api/v2/notes/{note_id}/attachments`（multipart/form-data）
- 下载：`GET /api/v2/attachments/{attachment_id}`

存储后端：

- 默认本地目录（`ATTACHMENTS_LOCAL_DIR`）
- 可选 S3 / COS（配置 `S3_*` 一组环境变量）

限制：

- `ATTACHMENTS_MAX_SIZE_BYTES` 控制单文件大小上限（返回 413）

### 3.7 Shares / Public（分享与公开访问）

v2 提供分享能力：

- 私有接口（需要鉴权）：创建/管理 share
- 公开接口（匿名访问）：通过 share token 访问笔记、附件、评论等

安全约定：

- **不存明文 share token**：服务端存 token 前缀 + HMAC
- 可配置分享有效期、撤销等
- 匿名评论可选择是否需要 captcha token（当前实现为“占位策略”，生产环境只校验 presence）

### 3.8 Notifications（通知）

v2 提供通知能力（例如：公开评论中的 @mention 触发通知）。

### 3.9 Admin 控制台（运维）

Admin 形态：

- 后端渲染 HTML（Jinja2 模板）
- 独立会话 Cookie（`ADMIN_SESSION_*`）
- 表单提交具备 CSRF token 校验

能力（以当前页面为准）：

- 登录/退出
- 用户列表、禁用/启用、密码重置/创建账号等运维操作
- 设备与 IP 活跃度跟踪（依赖客户端上报 device headers，或至少有 IP）

---

## 4. 关键设计约定（踩坑点集中说明）

### 4.1 多租户（Tenant）与软删除

绝大多数业务表都带 `user_id`，并使用：

- `deleted_at`：软删除（需要恢复时用 restore）
- `client_updated_at_ms`：并发控制/LWW
- `created_at` / `updated_at`：服务端维护的时间戳

### 4.2 时间与时区

- 默认 tzid：`DEFAULT_TZID`（默认 `Asia/Shanghai`）
- v1 使用“本地时间字符串”字段时不带 offset（固定长度 19）
- v2 更偏向显式 tzid 与更清晰的 schema

### 4.3 环境变量与生产安全校验

当 `ENVIRONMENT=production` 时会启用启动时校验（Fail Fast），典型要求：

- 不允许 `DATABASE_URL=sqlite...`
- 不允许 `CORS_ALLOW_ORIGINS=*`
- 必须设置高强度随机值（禁止占位符）：
  - `ADMIN_BASIC_PASSWORD`
  - `ADMIN_SESSION_SECRET`
  - `USER_SESSION_SECRET`
  - `SHARE_TOKEN_SECRET`
- 不允许 `DEV_BYPASS_MEMOS=true`
- 若启用 Memos 对接：必须提供 `MEMOS_BASE_URL` 与 `MEMOS_ADMIN_TOKEN`

### 4.4 反向代理信任边界

只有在“可信反代之后”才建议启用：

- `TRUST_X_FORWARDED_FOR=true`
- `TRUST_X_FORWARDED_PROTO=true`

否则会有伪造 IP / 伪造 https 导致 cookie 策略异常的风险。

---

## 5. 开发与部署建议（工程实践）

### 5.1 本地开发

- 推荐：`uv + SQLite`
- 迁移优先：`uv run alembic -c alembic.ini upgrade head`

### 5.2 Web 本地联调

推荐用 Next rewrites 做同源代理（cookie auth 体验最好）：

- Web：`http://localhost:3000`
- API：`http://localhost:31031`（浏览器侧通过 rewrites 看起来仍是同源）

### 5.3 生产部署

- 最简单：`docker compose up -d --build`
- 推荐形态：反向代理提供单一公网 origin（`/` 给 Web、`/api/*` 和 `/admin` 给后端）

---

## 6. 路线图（可选增强，不代表已交付）

以下是按“价值/风险”排序的可选增强项：

1. Public 匿名评论接入真实验证码提供商（目前仅为占位策略，生产只校验 presence）
2. 进一步统一 v1 错误格式（目前 v1 多为 FastAPI 默认 `detail`，v2 为 `ErrorResponse`）
3. 更完善的观测性：结构化日志、trace/span、指标（限流命中、同步耗时、附件吞吐等）
4. Token 轮换与安全策略（例如强制登出、设备撤销、token 过期策略可配置）
5. 更丰富的搜索能力（全文索引、标签/时间/状态组合过滤）

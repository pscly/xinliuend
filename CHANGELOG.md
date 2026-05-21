# Changelog

## 0.10.0 - 2026-05-21

### Added

- 新增 `scripts/build_release_bundle.sh`：自动打包后端发布包，统一产出部署压缩包、SHA-256 校验文件、构建元数据 JSON 与快速启动说明。
- 新增 `.github/workflows/release.yml`：
  - `main` 分支每次通过 CI 后自动生成一条 **main snapshot 预发布**；
  - 推送 `v*` 标签后自动生成一条 **正式 Release**；
  - 手动触发时也可补发当前提交的发布包。

### Changed

- 版本号从 `0.9.0` 升级到 `0.10.0`，用于标记“自动发布与可下载交付”这一轮能力增强。
- README 补充 GitHub Releases 下载说明，并把当前版本展示同步到 `0.10.0`。

### Documentation

- OpenAPI 快照会随本次版本提升同步导出，避免 `apidocs/openapi-v1*.json` 继续停留在旧版本号。

### Delivery

- 以后每次 `main` 成功通过 CI，都能在 `https://github.com/pscly/xinliuend/releases` 看到新的可下载结果；你无需再去 Actions 里翻产物。

## 0.9.0 - 2026-05-17

### Added

- **邮箱找回密码端到端流程**：
  - 新增 `POST /api/v1/auth/forgot-password` 与 `POST /api/v1/auth/reset-password`，输入邮箱即可通过邮件链接重置密码；
  - 新增 `POST /api/v1/me/email/request` 与 `POST /api/v1/me/email/confirm`，用户在 `/settings/email` 自助绑定邮箱（6 位数字验证码）；
  - 新表 `email_verification_tokens`、`password_reset_tokens`，token 仅以 SHA-256 哈希形式落库；
  - 重置/绑定邮件使用同款 HTML + 纯文本模板，模板位于 `src/flow_backend/templates/emails/`；
  - 默认限流：`auth_forgot_password=5/IP/5min`、`auth_reset_password=20/IP/5min`、`email_bind_request=5/IP/5min`、`email_bind_confirm=10/IP/5min`，均可在 `.env` 覆写。
- **管理员后台 SMTP 设置（运行时可编辑，无需重启）**：
  - 新增 `GET /admin/smtp`、`POST /admin/smtp`、`POST /admin/smtp/test`；
  - SMTP 密码使用现有 `USER_PASSWORD_ENCRYPTION_KEY`（Fernet）加密存储；
  - 同时支持 SSL（端口 465）与 STARTTLS（端口 587）；
  - 配置缺失时回退 `.env` 字段（`EMAIL_HOST/PORT/USERNAME/PASSWORD/FROM_ADDRESS/FROM_NAME/USE_SSL/USE_STARTTLS`）。
- **`site_settings` 通用键值表 + service**，带 30 秒进程内缓存，写入即失效。
- **前端**：
  - 新增公开页面 `/forgot-password` 与 `/reset-password`；
  - 新增鉴权页面 `/settings/email`；
  - 登录页加「忘记密码？」入口；
  - `MeResponse` 与 `useAuth().user` 新增 `email` / `emailVerified` 字段。
- **管理员强制写入 Memos Token 备用入口**：在 `/admin/users/{id}` 的「更新 Token」表单加「强制写入（不校验）」复选框（`force=1`），便于 Memos 升级后救急。

### Fixed

- **修复升级版 Memos 校验导致 502** —— 新版 Memos 把 user resource name 从 `users/<id>` 改为 `users/<username>`，导致 `_parse_user_identity` 抛错、上游 502。现在 `MemosCurrentUser` 接受 `user_id=0` 作为「无数字 id」哨兵值，`MemosClient.update_user_password` 优先使用 `users/<username>` URL、回退 `users/<numeric_id>`，`change_password` / admin reset 调用都会带上 username。
- 兼容旧版 Memos 数字 id 的所有现有路径保留。

### Schema migrations

- `20260517_0015_user_email_and_password_reset.py`：`users` 表新增 `email`、`email_verified_at`、`password_changed_at`；创建 `email_verification_tokens`、`password_reset_tokens`、`site_settings` 三张新表。

### Documentation

- README 与 CHANGELOG 同步更新；版本号 `pyproject.toml` 与 `__init__.py` 升至 `0.9.0`。

### Tests

- 新增 38 个测试：
  - `test_memos_client_new_resource_name.py`、`test_admin_force_bind_memos_token.py`（Memos 兼容性 + force 写入）
  - `test_site_settings_and_smtp.py`、`test_email_service.py`、`test_admin_smtp_page.py`（SMTP 配置 + 发邮件）
  - `test_email_binding.py`、`test_forgot_and_reset_password.py`（用户流程 + 反枚举）

## 0.8.0 - 2026-05-10

### Added

- 新增用户自助更新 Memos 凭据能力：`GET /api/v1/me/memos-credential` 查询绑定状态，`PUT /api/v1/me/memos-credential/token` 校验并保存已有 Memos Token / PAT，`POST /api/v1/me/memos-credential/issue-token` 使用当前 App 密码自动登录 Memos 并创建新的 Personal Access Token。
- 写入成功响应会一次性返回新的 Flow Bearer Token，并在 Cookie Session 场景返回轮换后的 CSRF Token，避免 Token 更新后客户端无法继续认证。
- Web `/settings` 新增「Memos 凭据绑定」卡片，支持粘贴 Token 与当前 App 密码自动签发两种模式，成功后展示一次性新 Token 和复制按钮。
- Memos client 增加 `GET /api/v1/auth/me` 校验、`POST /api/v1/auth/signin` 登录、`POST /api/v1/users/{user}/personalAccessTokens` 创建 PAT，并保留旧版 access token 兜底。

### Changed

- 管理后台 Token 修改改为“更新 Token”和“清空 Token”分离；空输入不再误清空，错误统一重定向回来源页面。
- 管理后台 Token 更新复用同一套 Memos Token 校验与用户 ID 自动解析逻辑；管理员后台允许用户名不一致作为运维兜底，并在成功提示中显示风险。
- `users.memos_token` 增加非空唯一索引，允许多个 `NULL`，防止同一 Bearer Token 命中多个用户。

### Documentation

- 更新 README 与 `apidocs/api.zh-CN.md`，补充自助凭据 API、Memos 官方接口依据与 Token 安全说明。
- 重新导出 `apidocs/openapi-v1.json` 与 `apidocs/openapi-v1.dev.json`。

### Tests

- 新增 Memos 凭据 API、Memos client、后台 Token 管理、Token 唯一性、Cookie CSRF 与 Bearer 轮换回归测试。

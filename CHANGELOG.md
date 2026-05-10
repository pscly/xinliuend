# Changelog

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

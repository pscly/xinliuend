# Learnings (frontend-guofeng)

## 2026-02-03 Task: bootstrap
- Notepad initialized.

## 2026-02-03 Task: initial-audit
- Backend already has cookie-session auth + CSRF enforcement in `src/flow_backend/deps.py` (cookie auth requires `X-CSRF-Token` for non-safe methods; Bearer bypasses CSRF).
- `/api/v1/me` exists and returns `{ username, is_admin, csrf_token }` via `src/flow_backend/routers/me.py`.
- `User.is_admin` exists with Alembic migration, and admin UI can toggle it (`src/flow_backend/routers/admin.py`).
- Web frontend scaffold exists under `web/` with Qinglu tokens in `web/src/app/globals.css`, style guide in `web/STYLEGUIDE.md`, i18n + theme toggles, and a Playwright smoke test.
- Playwright currently runs without backend, which causes Next rewrite proxy errors to `/api/v1/me` (test still passes but is noisy/flaky).
- LSP diagnostics are unavailable due to a Bun-on-Windows crash guard; use `uv run pytest` + `npm run build`/`npm run lint` as substitutes.

## 2026-02-03 Task: deploy-export
- Next static export enabled via `web/next.config.ts` (`output: "export"`, `trailingSlash: true`, `images.unoptimized`).
- Backend serves exported UI from `web/out` with `StaticFiles(html=True)` mounted at `/` (only when `web/out/index.html` exists).
- Added `/api/v1/*` fallback route so unknown v1 endpoints return JSON 404 instead of SPA HTML after the `/` mount.
- Playwright is updated to run against backend origin `http://127.0.0.1:31031` and start uvicorn via `uv --directory ..` (works with export mode).
\n## 2026-02-03 CSRF: Cookie-session + SPA (FastAPI)\n- 推荐：双重提交（Double Submit Cookie）变体：服务端在 HttpOnly cookie 里放“签名后的 CSRF token”，同时通过 `/csrf`（或 `/me`）返回“未签名 token”，前端仅存内存并在所有非安全方法请求里带 `X-CSRF-Token`。\n- 关键点：跨域/跨子域场景通常需要 `SameSite=None; Secure` + 严格 CORS allowlist；同站点可用 `SameSite=Lax` 但仍建议对敏感写操作加 CSRF token。\n- 轮换：至少在登录后、会话续期时轮换；如果做“一次性 token”，要考虑并发请求的容错（例如短暂 grace window）。\n- 强制范围：仅对 cookie-session 鉴权的写请求（POST/PUT/PATCH/DELETE）强制 CSRF；Bearer 客户端（`Authorization: Bearer ...`）通常不需要 CSRF。\n- 易踩坑：logout CSRF（强制 POST+token）、`Access-Control-Allow-Origin: *` 与 `allow_credentials=true` 不兼容、`SameSite=None` 必须 `Secure`。\n- 参考：OWASP CSRF Cheat Sheet（https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html）；Starlette cookie/session docs（https://github.com/Kludex/starlette）；fastapi-csrf-protect 实现（https://github.com/aekasitt/fastapi-csrf-protect）。\n

## 2026-02-03 CSRF: Cookie-session + SPA (FastAPI)（正确换行）
- 上一段出现了字面量 `\n`（写入时转义不当），请忽略；本段为正确格式。
- 推荐：双重提交（Double Submit Cookie）变体：服务端在 HttpOnly cookie 里放签名 token，同时通过 `/csrf`（或 `/me`）返回未签名 token；前端仅存内存并在写请求里带 `X-CSRF-Token`。
- 强制范围：仅对 cookie-session 鉴权的 POST/PUT/PATCH/DELETE 强制 CSRF；Bearer（`Authorization: Bearer ...`）默认不需要。
- Cookie 侧：跨域/跨子域→`SameSite=None; Secure` + 严格 CORS allowlist；同站点→优先 `SameSite=Lax`（仍对敏感写操作做 CSRF）。
- 轮换：至少登录后/会话续期时轮换；若做一次性 token 要处理并发（grace window/重试）。
- 易踩坑：logout CSRF（强制 POST+token）；`Access-Control-Allow-Origin:*` 不能与 `allow_credentials=true` 同用；`SameSite=None` 必须 `Secure`。
- 参考：OWASP（https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html）；Starlette docs（https://github.com/Kludex/starlette）；fastapi-csrf-protect（https://github.com/aekasitt/fastapi-csrf-protect）。

## 2026-02-03 Task: deploy-same-origin-static-export
- `web/next.config.ts` enables `output: "export"` + `trailingSlash: true` so routes export as `/route/index.html` under `web/out/`.
- Backend mounts `web/out` at `/` via `StaticFiles(html=True)` only when `web/out/index.html` exists, and it is mounted after `/api/*` + `/admin` routes to preserve precedence.
- Opt-out: `FLOW_DISABLE_WEB_STATIC=1`; override directory: `FLOW_WEB_OUT_DIR=...`.

## 2026-02-03 Task: deploy-same-origin-static-export (API 404 precedence)
- Mounting a SPA/static app at `/` will catch *unknown* `/api/v1/*` paths unless you add a v1 catch-all that returns JSON 404. Fix: add `@app.api_route(f"{settings.api_prefix}/{{path:path}}", ...)` that raises `HTTPException(404, "Not Found")`.

## 2026-02-03 Task: lint-playwright-artifacts
- ESLint flat config (`globalIgnores`) should ignore volatile Playwright output dirs like `test-results/**` and `playwright-report/**` to avoid intermittent ENOENT/lint instability.

## 2026-02-03 Notes v2: detect 409 conflict (web)
- Use `apiFetch` (not `apiFetchJson`) so you can inspect non-2xx responses and branch on `res.status === 409`.
- v2 error body is JSON: `{ error, message, details? }`; for Notes conflicts, `details.server_snapshot` contains the authoritative `Note` to merge/retry against.

## 2026-02-03 Todo v1: type来源
- v1 Todo 类型定义来自后端契约：`src/flow_backend/routers/todo.py`（响应字段/包裹 `{ code, data }`）与 `src/flow_backend/schemas_todo.py`（请求 payload 形状），落地于 `web/src/features/todo/types.ts`。

## 2026-02-03 Task: task7-search-dashboard
- `/search` 两种模式：
  - Query 模式：notes 调 v2 `GET /api/v2/notes?q=...`；todos 先调 v1 `GET /api/v1/todo/items` 再在客户端按 `title/note` 做大小写不敏感包含匹配。
  - Tag 模式：notes 调 v2 `GET /api/v2/notes?tag=...`；todos 调 v1 `GET /api/v1/todo/items?tag=...`（服务端 JSON filter）。
- `/search` 支持从 URL `?q=` / `?tag=` hydrate（客户端读取并初始化 state），并通过 tag chip 触发 tag 模式。
- Dashboard（`/`）的“今日待办”按后端约定固定 `Asia/Shanghai`（UTC+8）计算当天 `from/to`（`YYYY-MM-DDTHH:mm:ss`），再用 `rrule` 展开 occurrences，并通过 v1 occurrences endpoint 合并单次例外状态。
- 为了后续“把 .sisyphus 草稿/笔记一起上传”，已移除 `.gitignore` 对 `.sisyphus/boulder.json` 与 `.sisyphus/notepads/` 的忽略规则。

## 2026-02-03 Task: eslint-no-explicit-any (notes-conflict.spec.ts)
- Replaced `any` JSON placeholder with a narrow `RegisterJson` using `unknown` values to satisfy `@typescript-eslint/no-explicit-any` without changing runtime behavior.

## 2026-02-03 Task: task8-public-share-comments
- Share create `share_url` should point to UI route `{PUBLIC_BASE_URL}/share?token=...` (API for data stays under `/api/v2/public/...`).
- Public share comments: keep share semantics consistent (`revoked -> 404`, `expired -> 410`, deleted note -> 404) by resolving share token then validating note existence.
- Anonymous governance is best modeled as per-share booleans on `note_shares` (`allow_anonymous_comments`, `anonymous_comments_require_captcha`).
- Captcha placeholder: accept `X-Captcha-Token: test-pass` in non-production for deterministic tests; otherwise enforce presence (until a real provider is wired).
- Public-facing write endpoints (comment create + public attachment upload) should apply best-effort IP rate limiting via `extract_client_ip` + `enforce_rate_limit`.

## 2026-02-03 Task: notes-create-share-link-ui
- Authenticated share creation should use `apiFetch` (cookie + CSRF header injection) against `POST /api/v2/notes/{note_id}/shares`.
- Add minimal `data-testid` hooks for stable automation: `create-share` (button) and `share-url` (readonly input).

## 2026-02-03 Task: share-comments-e2e
- When the UI doesn't expose `share_id`, capture it by gating on the `POST /api/v2/notes/{note_id}/shares` response (`page.waitForResponse(...)`) and parsing JSON.
- For authenticated API calls that must include cookies (e.g. `PATCH /api/v2/shares/{share_id}/comment-config`), use `page.evaluate(fetch...)` with `credentials: "include"` and `X-CSRF-Token` from `GET /api/v1/me`.
- For anonymous validation, use a fresh `browser.newContext()` and visit the returned `share_url` directly; keep captcha deterministic via typing `test-pass` into the UI field so the page sends `X-Captcha-Token`.

## 2026-02-03 Task: task9-notifications-center
- Notification model lives in `src/flow_backend/models_notifications.py` with `read_at` as the unread/read toggle; list + unread-count are implemented as DB counts filtered on `read_at IS NULL`.
- Mention trigger is implemented in `src/flow_backend/v2/routers/public.py` after comment creation succeeds (no extra services): parse usernames via `@([A-Za-z0-9]{1,64})`, dedupe per comment, then create per-recipient `notifications` rows.
- v2 endpoints added:
  - `GET /api/v2/notifications?unread_only=...&limit=...&offset=...`
  - `GET /api/v2/notifications/unread-count`
  - `POST /api/v2/notifications/{notification_id}/read`
- Tests follow the existing pattern: temp SQLite DB + `alembic upgrade head` + httpx `ASGITransport`.

## 2026-02-03 Task: notifications-ui
- Added `/notifications` as a client page under the authenticated app shell; it fetches `GET /api/v2/notifications` and supports an `unread_only` toggle.
- Mark-as-read uses `POST /api/v2/notifications/{id}/read` via `apiFetch` (CSRF included) and then dispatches `window.dispatchEvent(new Event("notifications:changed"))` so `AppShell` can refresh the unread badge.

## 2026-02-03 Task: notifications-mention-e2e
- Stable selectors used for locale-agnostic Playwright: `data-testid="nav-notifications"` + `data-testid="notif-item"` + share UI `data-testid="create-share"`/`data-testid="share-url"`.
- In export mode with `trailingSlash: true`, share route may be `/share/?token=...`; match with `/\/share\/?\?token=/`.
- Mark-as-read assertion: click button by `/|Mark read/` then assert the post-state button is `/|Read/` and unread badge `/|Unread/` disappears.

## 2026-02-03 Task: notifications-mention-e2e (fix note)
- The previous bullet contained accidental control characters; ignore it.
- Correct locale-agnostic assertions: click `/标记已读|Mark read/`, then expect `/已读|Read/` to be disabled and the unread badge `/未读|Unread/` to be absent.

## 2026-02-03 Task: settings-admin-entry
- Admin area lives under `/settings/admin` (user app) and is guarded by `user.isAdmin`; backend `/admin` remains server-rendered with separate login and is only linked out.

## 2026-02-03 Task: evidence-pages
- Evidence screenshot naming: `<page>-<locale>-<theme>.png` (ASCII-only), e.g. `dashboard-zh-light.png`, `notifications-en-dark.png`.

## 2026-02-03 Task: security-regression-e2e
- Stored-XSS regression: share comments and notes preview must render `<img src=x onerror=alert(1)>` as plain text (assert no `img` exists inside the scoped container).
- Cookie-session CSRF regression: direct `fetch()` POST to a write endpoint without `X-CSRF-Token` must be rejected with HTTP 403.

## 2026-02-03 Task: admin-gate-e2e
- For `RequireAdmin`-guarded UI: verify both (1) entry link hidden (`data-testid="settings-admin-link"`) and (2) direct visit to `/settings/admin` redirects to `/` (use `waitForURL` with trailing-slash-tolerant predicate) and the admin page container (`data-testid="settings-admin-page"`) never renders.

## 2026-02-04 Task: plan-finalization
- Plan file checkboxes updated to reflect verified state (8/9/10 + acceptance criteria). Use `uv run pytest`, `npm run lint`, `npx playwright test` as the canonical verification trio when LSP diagnostics are unavailable on Windows.

## 2026-02-03 Task: i18n-theme-toggle-e2e
- Header pills are asserted via locale-agnostic aria-label regexes: language `/^(Language|\u8bed\u8a00):/`, theme `/^(Theme|\u4e3b\u9898):/`.
- Theme toggle assertion: click twice (system -> light -> dark), then wait on `document.documentElement.dataset.theme === "light"` / `"dark"` and verify localStorage `theme-preference` matches.
- Locale toggle assertion: click once and assert `data-testid="nav-notifications"` text flips between `Notifications` and `\u901a\u77e5`, then reload and verify localStorage `locale` persists.

## 2026-02-04 Task: docs-same-origin-export-and-e2e
- Document the two recommended workflows: (1) two-port local dev with Next rewrite proxy; (2) prod-like same-origin by building `web/out` and letting FastAPI mount it at `/`.
- CSRF reminder: cookie-session write requests require `X-CSRF-Token`; frontend obtains it from `GET /api/v1/me` and injects via `web/src/lib/api/client.ts`.
- Playwright E2E: `web/playwright.config.ts` builds the export and starts the backend; uses sqlite `playwright-e2e.db` and overrides env (`DEV_BYPASS_MEMOS`, `DATABASE_URL`, auth rate-limit overrides, `DEVICE_TRACKING_ASYNC=false`). Local runs may reuse an existing server unless `CI=1`.

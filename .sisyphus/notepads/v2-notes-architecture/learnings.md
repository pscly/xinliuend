# Learnings

## 2026-01-30 Session Start
- Initialized work session for v2 notes plan.

## 2026-01-31 Git Branch
- Created and checked out local branch `v2.0` from `main` using `git checkout -b v2.0`.
- Verified current branch via `git branch --show-current` and recorded `git status -sb` output (worktree already had changes: `AGENTS.md` modified, `.sisyphus/` untracked).

## 2026-01-31 Request-Id Middleware
- Implemented ASGI-level `RequestIdMiddleware` in `src/flow_backend/main.py:23`.
- Behavior: reads inbound `X-Request-Id` or generates uuid4; stores in `scope['state']['request_id']`; injects `X-Request-Id` response header.
- Verified: `uv run pytest -q` passes.

## 2026-01-31 Request ID Middleware
- Added an ASGI middleware that accepts inbound `X-Request-Id` (or generates a uuid4), stores it in `request.state.request_id`, and injects `X-Request-Id` into every HTTP response by wrapping `send()` for `http.response.start`.

## 2026-01-31 v2 Mounted Sub-App
- Implemented v2 as a mounted `FastAPI()` sub-app: `app.mount("/api/v2", v2_app)`.
- v2 provides its own schema endpoint at `/api/v2/openapi.json` (default sub-app OpenAPI under mount prefix).
- Added tests for `/api/v2/health` and `/api/v2/openapi.json` (asserts `/health` path exists in the schema).

## 2026-01-31 v2 Notes List Stub
- Added v2 `GET /api/v2/notes` endpoint implemented via a dedicated router.
- Introduced `Note`/`NoteList` Pydantic schemas and used `response_model=NoteList`; current stub returns an empty `items` list.

## 2026-01-31 v2 Routing Skeleton Completion
- Added v2 routers: `GET /api/v2/todo/items`, `GET /api/v2/sync/pull`, `POST /api/v2/sync/push` as minimal stubs.
- Added v2 schemas for `todo`, `sync`, and a unified `ErrorResponse`.
- Implemented v2-only exception handlers that return `ErrorResponse` without changing v1 error responses.
- Updated integration tests to assert:
  - v2 OpenAPI contains `/health` and `/notes`
  - v2 errors use `ErrorResponse` (no top-level `detail`)
  - v1 error responses still contain `detail`
  - `X-Request-Id` response header is present for both v1 and v2 responses
- basedpyright gotcha: `lsp_diagnostics` sometimes required restarting `basedpyright-langserver`; tests must avoid explicit `Any` types (`reportExplicitAny`).

## 2026-01-31 v2 Contract Alignment (Pinned Schemas)
- Aligned the v2 skeleton schemas early to the pinned plan contract to avoid downstream churn once clients start integrating.
- `ErrorResponse` is now flat (`error`, `message`, optional `request_id`, optional `details`) and enforced by v2-only exception handlers.
- List responses (`NoteList`, `TodoItemList`) now include `total`, `limit`, `offset` even when empty.
- Sync responses now match the pinned cursor/changes shape (`SyncPullResponse.cursor/next_cursor/has_more/changes`, `SyncPushResponse.cursor/applied/rejected`).

## 2026-01-31 CI Coverage (Phase 1)
- Phase 1: report-only coverage (generate `coverage.xml` + upload as artifact); no `--cov-fail-under` gate yet.
- Phase 2 sequencing: only add a fail-under gate after "core" modules are defined/populated; start with ~70% gate on core packages, not whole-repo coverage.

## 2026-01-31 Explicit Transaction Boundaries (Device Tracking)
- Removed DB side effects from `get_current_user`; it now only sets `request.state.auth_user_id`.
- Made `record_device_activity()` apply-only (no commit/rollback); commit happens in a separate session owned by middleware/routers.
- Added post-response device tracking middleware that uses a fresh `AsyncSession` and commits in its own transaction; errors are swallowed and logged with `request_id`.
- Added `DEVICE_TRACKING_ASYNC` (default true) so tests can force inline execution with `DEVICE_TRACKING_ASYNC=false`.
- Windows ripgrep note: use `rg --path-separator=/ ... | rg -v "src/flow_backend/routers/"` to match the pinned acceptance check.

## 2026-02-01 v2 Settings Env Keys (share/S3/Memos)
- Confirmed pinned env keys already exist in `src/flow_backend/config.py` (sharing, attachments, S3, Memos note endpoints, device tracking, ENVIRONMENT).
- Updated `.env.example` to include and document: `ENVIRONMENT`, `PUBLIC_BASE_URL`, `SHARE_TOKEN_SECRET`, `ATTACHMENTS_LOCAL_DIR`, `S3_*`, `MEMOS_NOTE_*_ENDPOINTS`, `DEVICE_TRACKING_ASYNC`.
- Gotcha: `lsp_diagnostics` may require restarting `basedpyright-langserver` to pick up updated pyright/basedpyright config.


## 2026-02-01 .env.example Maintenance Conventions (FastAPI + pydantic-settings)
- Treat `.env.example` as the canonical key registry: every setting the app reads should appear here with a short comment describing purpose/format.
- Keep `.env` (real values) untracked via `.gitignore`; only commit `.env.example` with placeholders/safe defaults.
- Prefer sectioned layout (e.g., Database / Docker Compose / Memos / Admin / CORS / Logging / Sync) with 1-2 lines of context per section.
- Defaults vs placeholders:
  - Non-secret, safe dev defaults OK (e.g., `DATABASE_URL=sqlite:///./dev.db`, ports, `LOG_LEVEL=INFO`).
  - Secrets/tokens/passwords should be empty (`VAR=`) if the app can run without them locally, otherwise use a loud placeholder (`*_change_me`, `changethis`) and add a production must change comment.
- Avoid accidental secret commits:
  - Never paste real tokens/credentials into `.env.example` (even if dev), since templates get copied widely.
  - If you need an example shape, use obviously fake values (`https://memos.example.com`, `sk-...`, `********`) and keep them non-functional.
- Document parsing formats for non-scalar values:
  - If a setting expects a list, standardize on one encoding (CSV string or JSON array) and document it right above the key.

References:
- 12-Factor Config (env vars, separation of config from code): https://12factor.net/config
- FastAPI Settings and Environment Variables (pydantic-settings, dotenv support): https://fastapi.tiangolo.com/advanced/settings/
- Pydantic Settings API (`BaseSettings`, `_env_file`, dotenv source): https://docs.pydantic.dev/latest/api/pydantic_settings/
- Example env file organization & placeholders (Full Stack FastAPI Template): https://raw.githubusercontent.com/fastapi/full-stack-fastapi-template/master/.env
- Minimal .env.example example (FastAPI RealWorld app): https://raw.githubusercontent.com/nsidnev/fastapi-realworld-example-app/master/.env.example

## 2026-02-01 Pydantic Settings v2: env keys / aliasing / dotenv
- Official docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Pydantic Settings docs example (BaseSettings + SettingsConfigDict + validation_alias/AliasChoices): https://github.com/pydantic/pydantic-settings/blob/a04b03450e62f583cdaee2d93df693b991aeb319/docs/index.md#L11-L106
- SettingsConfigDict supports env_file/env_prefix/case_sensitive/extra/secrets_dir: https://github.com/pydantic/pydantic-settings/blob/a04b03450e62f583cdaee2d93df693b991aeb319/pydantic_settings/main.py#L45-L76
- Dotenv behavior (quotes/comments; env vars override dotenv): https://github.com/pydantic/pydantic-settings/blob/a04b03450e62f583cdaee2d93df693b991aeb319/docs/index.md#L620-L712
- AliasChoices definition (used by Field(validation_alias=...)): https://github.com/pydantic/pydantic/blob/08b64f7a43f96f02bb0af8d46aba67b3a68d6e88/pydantic/aliases.py#L57-L85
- secrets_dir reads secret files from a directory (docker secrets style): https://github.com/pydantic/pydantic-settings/blob/a04b03450e62f583cdaee2d93df693b991aeb319/pydantic_settings/sources/providers/secrets.py#L25-L79

### Real-world examples of validation_alias=AliasChoices(...)
- cohere-ai/cohere-toolkit settings config + env aliasing: https://github.com/cohere-ai/cohere-toolkit/blob/fdd4371edf164f2c1726a884e421049093c0128e/src/backend/config/settings.py#L12-L19
- cohere-ai/cohere-toolkit Field(validation_alias=AliasChoices(...)): https://github.com/cohere-ai/cohere-toolkit/blob/fdd4371edf164f2c1726a884e421049093c0128e/src/backend/config/settings.py#L70-L96
- lastmile-ai/mcp-agent env aliasing + env_file: https://github.com/lastmile-ai/mcp-agent/blob/f62d849350816588b1c6294e7914bbe4d8b84072/src/mcp_agent/config.py#L295-L389

### Repo recommendation (Task 4b)
- Use UPPER_SNAKE_CASE keys in .env.example; add short comments (type/format + required in prod).
- When renaming env keys, keep backward compatibility via Field(validation_alias=AliasChoices("NEW", "OLD")).
- Consider extra="ignore" so .env can contain future keys without breaking settings construction.

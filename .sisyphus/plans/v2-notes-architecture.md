# v2.0(/api/v2) Notes System + Architecture Optimization Plan

## TL;DR

> **Quick Summary**: Create a v2.0 git branch that introduces `/api/v2` and a first-party “full notes system”, while refactoring the backend into explicit transaction boundaries + service/repository layers + testable sync planners. Add pytest-cov with “core module” coverage gating.
>
> **Deliverables**:
> - `/api/v2` REST-style typed APIs (no `{code,data}` envelope) + unified `ErrorResponse`
> - Notes system: Markdown notes, tags, full-text search, attachments (Tencent Cloud S3), anonymous read-only sharing with expiry, version history, sync
> - Transition: MemosConnector bidirectional sync (Memos authoritative) with conflict-preserving local revisions
> - Engineering: coverage reports + core-module coverage gate in CI

**Estimated Effort**: XL
**Parallel Execution**: YES - 3 waves (some tasks can be parallelized)
**Critical Path**: v2 skeleton + tx boundaries → Notes domain/migrations → Notes APIs/search/storage → Sync planner + tests → MemosConnector bidir sync

## Task Checklist
- [x] 1) Create v2.0 Branch + /api/v2 Routing Skeleton
- [x] 2) Enforce Explicit Transaction Boundaries (remove implicit commits)
- [x] 3) Introduce Service + Repository Layer (thin routers)
- [x] 4) Add pytest-cov + CI Coverage Reporting + Core Gate
- [x] 4b) Expand Settings for v2 Features (share/S3/Memos)
- [x] 5) Notes Data Model + Alembic Migrations (SQLite-first)
- [x] 6) Full-text Search for Notes (SQLite FTS5)
- [x] 7) Attachments: Storage Abstraction + Tencent Cloud (S3-compatible)
- [x] 8) Sharing: Anonymous Read-only Share Links with Expiry
- [x] 9) Version History + Conflict Revisions
- [x] 10) Notes CRUD + Tags Filter (v2 REST APIs)
- [x] 11) Notes Sync (Client <-> Backend) Using Planner + SyncEvent
- [x] 12) MemosConnector: Bidirectional Sync (Memos authoritative)
- [x] 13) TODO Enhancements (server-side tag filter)
- [x] 14) Observability & Ops Hardening
- [x] 15) Remove Hard-coded tzid in v2 (correctness)

---

## Context

### Original Request (condensed)
- “Detailed analysis + better design/optimization” for the current FastAPI backend.
- Create a new git release line “v2.0” with breaking changes isolated under `/api/v2`.
- Long-term: remove Memos dependency and build a first-party notes backend.
- Short-term transition: keep Memos integration and support bidirectional sync, but **Memos is authoritative**.
- Priorities: maintainability, correctness/stability, extensibility.
- Engineering bar: add coverage (pytest-cov) with gating.
- Sharing: anonymous read-only share links with expiry; store only token hashes.
- Conflicts: when Memos wins, preserve local changes as conflict revisions.
- Object storage: Tencent Cloud (S3-compatible).

### What Exists Today (repo findings)
- Framework: FastAPI (`src/flow_backend/main.py`)
- Auth: Bearer token = `User.memos_token` lookup (`src/flow_backend/deps.py:15`) + device tracking side-effect (`src/flow_backend/deps.py:30`)
- **Hidden side effects**: device tracking commits inside helper (`src/flow_backend/device_tracking.py:111`)
- DB: SQLModel + async SQLAlchemy (`src/flow_backend/db.py`, `src/flow_backend/models.py`), Alembic migrations (`alembic/env.py`, `alembic.ini`)
- Sync: `SyncEvent` cursor-based incremental pull/push (`src/flow_backend/routers/sync.py:95`)
- TODO: tag filter is currently a TODO (server ignores `tag`) (`src/flow_backend/routers/todo.py:248`)
- CI: `uv sync --extra dev --frozen` + `ruff` + `pytest` (`.github/workflows/ci.yml:26`)
- Project version is `0.x` (`pyproject.toml:7`) (keep this; do NOT bump to 2.0.0)

### Metis Review (guardrails)
- Keep `/api/v1` behavior stable on main; all breaking changes are `/api/v2` on the v2 branch.
- Do not require live network in CI (no Tencent Cloud, no live Memos). Use mocks/stubs.
- Make field-level authority explicit for Memos transition to avoid sync ping-pong.
- Notes scope is backend-only (no UI/client work unless requested).

---

## Work Objectives

### Core Objective
Deliver a maintainable and testable `/api/v2` backend that supports a full notes system and a Memos transition path, while removing key correctness risks (implicit commits, fat routers) via clear layering and deterministic sync logic.

### Definition of Done (high-level)
- `/api/v2` provides REST-style typed responses with consistent error model.
- Notes system supports CRUD + tags + search + attachments + sharing + revision history + sync.
- Memos transition supports bidirectional sync with Memos authoritative and conflict preservation.
- All tests pass; coverage report produced; core module coverage gate passes.

### Must NOT Have (guardrails)
- No JWT/refresh-token migration.
- No plaintext share tokens stored.
- No implicit `commit()` in dependencies/helpers/repositories.
- No CI steps that require real external network services.
- No semantic version bump to 2.0.0 (keep `0.x` per repo rules).

### v1 vs v2 Scope Boundaries (explicit)
- v1 API surface (`/api/v1`) is kept behavior-compatible (success envelope stays `{code,data}`; errors remain FastAPI default `{"detail": ...}` unless explicitly changed later).
- v1 tzid semantics remain as documented today (RRULE-related tzid fixed `Asia/Shanghai`, and existing hard-coded behavior remains).
- v2 API surface (`/api/v2`) is allowed to be breaking and will implement improved tzid/time handling.
- Internal refactors of v1 code are allowed only if tests confirm identical externally observable behavior.

---

## Key Design Decisions (locked)

### API Versioning
- v2 is isolated under `/api/v2`.
- v2 branch name is “v2.0” (git/release line). Semantic version in `pyproject.toml` stays `0.x`.

### v2 App Isolation (to protect v1)
- Implement v2 as a **mounted sub-app** (a separate `FastAPI()` instance) mounted at `/api/v2`.
- v2-only middleware/exception handling lives on the v2 sub-app.
- v1 remains on the main app and keeps its current envelope style (e.g. `{"code":200,"data":...}`).

### v2 Code Layout (explicit)
To avoid “where should this live?” guesswork:
- Package root is under `src/` in this repo.
- v2 app instance: `src/flow_backend/v2/app.py` (exports `v2_app`)
- v2 routers: `src/flow_backend/v2/routers/*` (notes, sync, attachments, sharing, integrations)
- v2 schemas (request/response contracts): `src/flow_backend/v2/schemas/*`
- Shared domain logic: `src/flow_backend/domain/*`
- Shared use-cases: `src/flow_backend/services/*`
- Shared DB access: `src/flow_backend/repositories/*`
- External connectors: `src/flow_backend/integrations/*`

Initial skeleton file set (Task 1 should create these paths):
- `src/flow_backend/v2/__init__.py`
- `src/flow_backend/v2/routers/__init__.py`
- `src/flow_backend/v2/schemas/__init__.py`
- `src/flow_backend/v2/app.py`
- `src/flow_backend/v2/routers/health.py`
- `src/flow_backend/v2/routers/notes.py` (stub list endpoint)
- `src/flow_backend/v2/routers/todo.py` (stub list endpoint)
- `src/flow_backend/v2/routers/sync.py`
- `src/flow_backend/v2/schemas/errors.py`
- `src/flow_backend/v2/schemas/notes.py`
- `src/flow_backend/v2/schemas/todo.py`
- `src/flow_backend/v2/schemas/sync.py`

Mounting/registration pattern:
- main app (existing `flow_backend.main:app`) mounts `v2_app` at `/api/v2`.
- v2 routers use internal paths like `/notes` (external path becomes `/api/v2/notes`).

### Response Style
- `/api/v2` uses FastAPI `response_model=...` and returns domain resources directly.
- Errors return a unified `ErrorResponse` model with HTTP status codes (no global `{code,data}` envelope).

### ErrorResponse (v2)
Define a minimal, stable schema to prevent ad-hoc errors:
- `error`: short machine string (e.g. `validation_error`, `not_found`, `conflict`, `unauthorized`, `forbidden`, `upstream_error`)
- `message`: human-readable summary
- `request_id`: optional request correlation id
- `details`: optional object/array for field errors or extra context

Mapping rules (v2-only):
- Validation errors → 422 + `error=validation_error`
- Auth missing/invalid → 401 + `error=unauthorized`
- Forbidden → 403 + `error=forbidden`
- Not found → 404 + `error=not_found`
- Expired share token → 410 + `error=gone`
- Conflict (stale update / Memos-authoritative overwrite) → 409 + `error=conflict`

Default mappings (pinned):
- 400 → `bad_request`
- 429 → `rate_limited`
- 502 (upstream, e.g. Memos) → `upstream_error`

Pinned v2 exception handler set (v2 sub-app only):
- `RequestValidationError` → 422 `ErrorResponse`
- `HTTPException` → map status code to `ErrorResponse` (`unauthorized`/`forbidden`/`not_found`/`conflict` etc.)
- generic `Exception` → 500 `ErrorResponse(error="internal_error")` (log with request-id)

Request-Id contract (pinned):
- Accept inbound header: `X-Request-Id` (optional).
- If missing, generate a new uuid4 request id.
- Always return response header: `X-Request-Id`.
- Store it on `request.state.request_id` so middleware/exception handlers can populate:
  - `ErrorResponse.request_id`
  - structured logs.

### Auth
- Keep Bearer token style. Token lookup is per-user (multi-user system exists today; `User` table). (`src/flow_backend/models.py:15`, `src/flow_backend/deps.py:15`)

### Memos Transition
- Bidirectional sync for a period.
- Memos is authoritative.
- When Memos wins, local edits are preserved as conflict revisions.

### Object Storage
- Attachments use Tencent Cloud S3-compatible storage.
- For dev/tests/CI: provide a local backend or stub implementation (no real S3 calls in CI).

### Configuration Surface (new .env keys; pinned)
Add these to `src/flow_backend/config.py` (pydantic-settings) so behavior is not ad-hoc:

Sharing:
- `PUBLIC_BASE_URL` (e.g. `https://api.example.com`) used to compose share URLs
- `SHARE_TOKEN_SECRET` (required in non-dev) used for `HMAC-SHA256`

Pinned defaults for dev/tests:
- In `development`, if `SHARE_TOKEN_SECRET` is missing, use a clearly-insecure default (and log a warning) so local dev/tests are deterministic.
- In tests, set `SHARE_TOKEN_SECRET="test-secret"` via env/fixture to avoid relying on the dev default.

Device tracking:
- `DEVICE_TRACKING_ASYNC` (default: true; tests set false to run inline)

CORS (existing key; enforce in production):
- `CORS_ALLOW_ORIGINS` (comma-separated; must not be `*` in production)
- `CORS_ORIGINS` accepted as an alias for backward compatibility

S3/Tencent Cloud (S3-compatible):
- `S3_ENDPOINT_URL`
- `S3_REGION`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`
- `S3_FORCE_PATH_STYLE` (optional; for S3-compatible providers)

Local attachments backend (dev/tests):
- `ATTACHMENTS_LOCAL_DIR` (default: `.data/attachments`)

Memos notes connector (transition; endpoint overrides):
- `MEMOS_NOTE_LIST_ENDPOINTS` (comma-separated)
- `MEMOS_NOTE_UPSERT_ENDPOINTS` (comma-separated)
- `MEMOS_NOTE_DELETE_ENDPOINTS` (comma-separated)

Rotation note (explicit): rotating `SHARE_TOKEN_SECRET` invalidates existing share links unless key-versioning is implemented (out of scope for v2.0).

### Time & Timezone
- Internally store/compare timestamps in UTC.
- `tzid` is an input/output concern; avoid hard-coding `Asia/Shanghai` inside v2 write paths.
- Provide `settings.default_tzid` as a fallback.

### v2 Notes API Contract (baseline; adjust later if needed)

Notes:
- `POST /api/v2/notes` → 201 `Note`
- `GET /api/v2/notes` → 200 `NoteList` (pagination pinned: `limit` + `offset`; filters: `tag`, `q`, `include_deleted=false`)
  - Ordering (pinned): `updated_at DESC, id DESC`.
  - `total` (pinned): count after applying `tag`/`q`/`include_deleted` filters.
  - `tag` match (pinned): case-insensitive exact match on `tags.name_lower`.
  - `q` behavior (pinned): full-text search on `title + body_md` (SQLite FTS5) and intersects with `tag` if provided.
  - `include_deleted=false` excludes `deleted_at IS NOT NULL` from results and from search index.
- `GET /api/v2/notes/{note_id}` → 200 `Note`
- `PATCH /api/v2/notes/{note_id}` → 200 `Note`
- `DELETE /api/v2/notes/{note_id}` → 204 (soft delete; sets `deleted_at`)
- `DELETE /api/v2/notes/{note_id}` → 204 (soft delete; sets `deleted_at`)
  - Request (pinned): query param `client_updated_at_ms` (required)
  - Conflict rule (pinned): if stale → 409 `ErrorResponse(error="conflict")` + `details.server_snapshot`
- `POST /api/v2/notes/{note_id}/restore` → 200 `Note`
  - Request (pinned): `NoteRestoreRequest { client_updated_at_ms: int }`
  - Conflict rule (pinned): same as PATCH (stale → 409)

Revisions:
- `GET /api/v2/notes/{note_id}/revisions` → 200 `NoteRevisionList`
- `POST /api/v2/notes/{note_id}/revisions/{revision_id}/restore` → 200 `Note`

Search:
- Prefer `GET /api/v2/notes?q=...` for baseline full-text search (SQLite FTS5), rather than a separate route.

Attachments:
- `POST /api/v2/notes/{note_id}/attachments` (multipart) → 201 `Attachment`
- `GET /api/v2/attachments/{attachment_id}` → 200 (stream) (auth required)

Sharing (public):
- `POST /api/v2/notes/{note_id}/shares` → 201 `ShareCreated` (returns plaintext token once)
  - Request (pinned): `ShareCreateRequest { expires_in_seconds?: int }`
  - Default expiry (pinned): 7 days if omitted.
  - Max expiry (pinned): 30 days (validation error if exceeded).
- `DELETE /api/v2/shares/{share_id}` → 204
- `GET /api/v2/public/shares/{share_token}` → 200 `SharedNote`
- `GET /api/v2/public/shares/{share_token}/attachments/{attachment_id}` → 200 (stream)

Sync:
- `GET /api/v2/sync/pull?cursor=0&limit=200` → 200 `SyncPullResponse`
- `POST /api/v2/sync/push` → 200 `SyncPushResponse`

Pinned v2 sync contracts (must-have):
- `SyncMutation`:
  - `resource`: string (pinned set for v2.0: `note`, `todo_item`)
  - `entity_id`: string (uuid)
  - `op`: `upsert` | `delete`
  - `client_updated_at_ms`: int
  - `data`: object (for `upsert` only)

- `SyncPushRequest`:
  - `mutations: list[SyncMutation]`

- `SyncPushResponse` (always HTTP 200 on valid request; per-mutation conflicts are in body):
  - `cursor: int` (latest sync event id)
  - `applied: list[{resource, entity_id}]`
  - `rejected: list[{resource, entity_id, reason, server?}]`

- `SyncPullResponse`:
  - `cursor: int`
  - `next_cursor: int`
  - `has_more: bool`
  - `changes: { notes: list[Note], todo_items: list[TodoItem] }`

Notes sync representation (pinned):
- Deletes are represented as `Note` objects with `deleted_at != null`.

Example `SyncPushRequest`:
```json
{
  "mutations": [
    {
      "resource": "note",
      "entity_id": "b0f1b5d7-2c2f-4c8d-9f58-2f9f0e5b7c4a",
      "op": "upsert",
      "client_updated_at_ms": 1710000000000,
      "data": {
        "title": "Hello",
        "body_md": "# Hello\nworld",
        "tags": ["work"]
      }
    }
  ]
}
```

Todo (v2; for enhancements workstream):
- `GET /api/v2/todo/items?tag=...` → 200 `TodoItemList`
- `POST /api/v2/todo/items` → 201 `TodoItem`
- `PATCH /api/v2/todo/items/{item_id}` → 200 `TodoItem`

Minimal models (field names are part of the contract):
- `Note`: `id`(uuid str), `title`(str), `body_md`(str), `tags`(list[str]), `client_updated_at_ms`(int), `created_at`(ISO UTC), `updated_at`(ISO UTC), `deleted_at`(ISO UTC|null)
- `NoteList`: `items`(list[Note]), `total`(int), `limit`(int), `offset`(int)
- `TodoItem` (v2 minimal): `id`(uuid str), `title`(str), `tags`(list[str]), `client_updated_at_ms`(int), `updated_at`(ISO UTC), `deleted_at`(ISO UTC|null)
- `TodoItemList`: `items`(list[TodoItem]), `total`(int), `limit`(int), `offset`(int)
- `NoteRevision`: `id`, `note_id`, `kind`(`NORMAL`|`CONFLICT`), `snapshot`(NoteSnapshot), `created_at`, `reason`(optional)
- `Attachment`: `id`, `note_id`, `filename`, `content_type`, `size_bytes`, `storage_key`, `created_at`
- `Share`: `id`, `note_id`, `expires_at`, `revoked_at`, `created_at`
- `ShareCreated`: `share_id`, `share_url`, `share_token`
- `SharedNote`: `note` + attachments metadata

Pinned request contracts (to avoid guesswork):
- `NoteCreateRequest`:
  - `id` (optional uuid str; if provided, server uses it for offline/sync; otherwise server generates uuid4)
  - `title` (optional; if missing, derive from first non-empty line of `body_md`)
  - `body_md` (required)
  - `tags` (optional list[str]; default empty)
  - `client_updated_at_ms` (optional; if missing, server sets to `now_ms()`)
- `NotePatchRequest` (all optional, but at least one must be present):
  - `title`
  - `body_md`
  - `tags` (replace semantics: if provided, it replaces the full tag set)
  - `client_updated_at_ms` (required for optimistic concurrency; stale updates return 409 conflict)

- `NoteRestoreRequest`:
  - `client_updated_at_ms` (required; restore is a write and participates in LWW)

Pinned write semantics:
- Notes use LWW on `client_updated_at_ms` (same conceptual model as v1 sync).
- For `PATCH`, if `incoming_ms < existing.client_updated_at_ms` → 409 with `ErrorResponse(error="conflict")` and include `server_snapshot` in `details`.
- Revisions:
  - On every successful update/delete/restore, create a `NoteRevision` snapshot of the previous state.
  - On Memos-authoritative overwrite, create a `CONFLICT` revision containing the local snapshot.

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (`pytest`, `tests/`, CI already runs `uv run pytest`) (`pyproject.toml:25`, `.github/workflows/ci.yml:35`)
- **User wants tests**: YES (add coverage)
- **Framework**: pytest + anyio + pytest-cov

### Coverage Gate Strategy (core modules)
- Add `pytest-cov`.
- Phase 1 (early): produce a coverage report (no gate) to avoid breaking CI before new v2 core packages exist.
- Phase 2 (after Task 3 creates the core packages and core logic moves into them): enable a **core-module gate** at **70%**.

Core modules definition (repo layout under `src/flow_backend`):
- `flow_backend.domain`
- `flow_backend.services`
- `flow_backend.repositories`
- `flow_backend.integrations`

Example commands (agent-executable):
```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .

# Phase 1: report only
uv run pytest -q --cov=flow_backend --cov-report=term-missing

# Phase 2: core-module gate (after packages exist)
uv run pytest -q \
  --cov=flow_backend.domain \
  --cov=flow_backend.services \
  --cov=flow_backend.repositories \
  --cov=flow_backend.integrations \
  --cov-report=term-missing \
  --cov-fail-under=70
```

---

## Execution Strategy

### Parallel Execution Waves

Wave 1 (foundation, can start immediately):
- v2 branch + `/api/v2` skeleton + error model
- Introduce service/repo structure and transaction boundary rules
- Add pytest-cov + CI wiring (report + core gate)

Wave 2 (domain building blocks):
- Notes DB schema + migrations (SQLite-first; future Postgres)
- Notes APIs (CRUD, tags, revisions)
- Object storage abstraction + S3-compatible implementation + share tokens
- Full-text search (SQLite FTS5)

Wave 3 (sync & integration):
- Notes sync model + sync planner pure functions + test matrix
- MemosConnector mapping + bidirectional sync with Memos authoritative + conflict revisions
- Observability (request-id, structured logs, exception handlers)

---

## TODOs

> Implementation + Tests = ONE Task (do not separate).
> Every task must include automated verification.

### 1) Create v2.0 Branch + /api/v2 Routing Skeleton

**What to do**:
- Create git branch `v2.0`.
- Implement v2 as a mounted sub-app (`FastAPI()`), mounted at `/api/v2`.
- Register all v2 routers on the v2 sub-app (not the main app).
- Add `/api/v2/health` endpoint.
- Define `ErrorResponse` and implement **v2-only** exception handling/middleware on the v2 sub-app.
- Install request-id middleware on the main app (covers v1 + mounted v2):
  - Accept `X-Request-Id` or generate uuid4
  - Always return `X-Request-Id`
- Add a minimal v2 notes router stub to make OpenAPI assertions executable:
  - `GET /notes` returns an empty `NoteList` (200)
- Add a minimal v2 todo router stub to support the v2 todo workstream without touching v1:
  - `GET /todo/items` returns an empty `TodoItemList` (200)
- Add a minimal v2 sync router stub so Task 11 has a concrete wiring target:
  - `GET /sync/pull` returns empty `changes`
  - `POST /sync/push` returns empty `applied/rejected`

**Must NOT do**:
- Do not change `/api/v1` response shapes.

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 1)
- Blocks: Tasks 2-14 (v2 work depends on v2 skeleton)

**References**:
- `src/flow_backend/main.py` (router registration pattern)
- `.github/workflows/ci.yml:1` (CI expectations)

**Acceptance Criteria**:
```bash
uv run pytest -q
uv run uvicorn flow_backend.main:app --help
```
And an integration test asserting:
- `GET /api/v2/health` returns 200
- `GET /api/v2/openapi.json` contains v2 routes (e.g. `/notes`)
- A representative v1 error response shape is unchanged (v1 errors remain FastAPI default JSON with `detail`, not `ErrorResponse`)
  - Pinned check: `POST /api/v1/auth/login` with invalid credentials → 401 and JSON contains `detail` key
- `X-Request-Id` response header is present for both v1 and v2 responses

### 2) Enforce Explicit Transaction Boundaries (remove implicit commits)

**What to do**:
- Commit ownership rule (explicit scope):
  - v2 code: only service-layer “use cases” may `commit()`.
  - v1 existing routers: may continue to `commit()` temporarily unless/ until refactored, but **dependencies/helpers/repositories must never commit**.
- Remove `commit()` from device tracking helper; make it pure “apply changes to session” (no commit/rollback).
- Move device tracking persistence out of `get_current_user` dependency path:
  - Update `get_current_user` (`src/flow_backend/deps.py:15`) to only authenticate/authorize and return `User` (no side effects).
  - Also set `request.state.auth_user_id = user.id` (pure in-memory) so middleware can act without re-querying auth.
  - Add a request middleware (main app and/or v2 app) that:
    - reads device headers (`X-Flow-Device-Id`, etc.)
    - uses `request.state.auth_user_id` (set by `get_current_user`) as the single source of truth (no duplicate auth DB lookup)
    - after response completes, uses a fresh `AsyncSession` + its own transaction to persist device tracking (best effort)
- Update auth routes that call tracking directly (`src/flow_backend/routers/auth.py:77`) to use a dedicated service function that commits via its own session (register/login requests cannot rely on middleware because the token is created/returned during the request).

**Pinned implementation mechanism (to avoid guesswork)**:
- Implement an ASGI middleware on the **main app** (so it covers v1 + mounted v2) that, after `call_next(request)` returns a `Response`, attaches a Starlette `BackgroundTask` (or `BackgroundTasks`) to `response.background`.
- The background task runs after the response is sent (covers streaming responses as well).
- Session creation in the task uses the project’s existing async sessionmaker pattern in `src/flow_backend/db.py` (do not reuse the request session).
- Best-effort behavior: swallow exceptions, log warning with request-id.
- Test stability rule (pinned): in tests, run tracking inline (no background) via a settings flag `DEVICE_TRACKING_ASYNC=false` to avoid ASGITransport timing flakiness.
- Config ownership (pinned): Task 2 adds `DEVICE_TRACKING_ASYNC` and a minimal `ENVIRONMENT` (default `development`) to `src/flow_backend/config.py`.

**Files to create/edit (pinned)**:
- `src/flow_backend/deps.py` (remove tracking side effect; set `request.state.auth_user_id`)
- `src/flow_backend/device_tracking.py` (remove internal commit/rollback)
- `src/flow_backend/v2/routers/debug.py` (dev-only tx-fail endpoint)

**References**:
- `src/flow_backend/deps.py:15` (auth dependency triggers tracking)
- `src/flow_backend/device_tracking.py:44` (tracking helper)
- `src/flow_backend/device_tracking.py:111` (implicit commit)
- `tests/test_device_tracking_on_auth.py:1` (existing test expectations for login/register tracking)

**Acceptance Criteria**:
- Static search in repo finds no `await session.commit()` inside dependencies/helpers.
- If middleware approach chosen: a read-only authenticated request still updates device last_seen (via separate transaction), and failures do not partially commit core business data.
- Add tests:
  - If request fails after auth, device tracking does not produce partial committed state.
  - Existing auth tracking tests remain valid (login/register still record device rows via the dedicated service path).

Pinned “read-only request” for device tracking verification:
- Use `GET /api/v1/todo/lists` (Bearer-authenticated) as the deterministic read-only endpoint in tests.

Pinned failure scenario for “no partial commit” verification:
- Add a v2 debug-only route (enabled only when `ENVIRONMENT != production`): `POST /api/v2/debug/tx-fail`.
  - It authenticates via `get_current_user`.
  - It writes a row to an existing business table inside the request session (pinned: `user_settings`) and then raises an exception before commit.
  - Test asserts the business row is NOT persisted after the 5xx response.
```bash
uv run pytest -q -k device_tracking
```

Objective “no implicit commit” check (example):
```bash
rg -n "await session\.commit\(" src/flow_backend -g"*.py" | rg -v "src/flow_backend/routers/"
# Assert: no output
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 1)
- Blocked By: Task 1

### 3) Introduce Service + Repository Layer (thin routers)

**What to do**:
- Create the v2 core packages (even if initially minimal):
  - `src/flow_backend/domain`
  - `src/flow_backend/services`
  - `src/flow_backend/repositories`
  - `src/flow_backend/integrations`
  - Ensure each is a Python package (must include `__init__.py`).
- Create `flow_backend/services/*` and `flow_backend/repositories/*` for business logic + DB access.
- Migrate one existing complex slice first (recommend: sync push) into service + repo.
- Ensure repositories never commit.

Canonical transaction pattern (pinned):
```python
# Router (v1 or v2) passes request-scoped session into service.
async def handler(..., session: AsyncSession = Depends(get_session)):
    return await sync_service.push(session=session, user=user, req=req)

# Service owns commit using a transaction block.
async def push(*, session: AsyncSession, user: User, req: SyncPushRequest) -> SyncPushResponse:
    async with session.begin():
        ...  # repository calls (no commit)
```

**References**:
- `src/flow_backend/routers/sync.py:198` (fat controller candidate)
- `src/flow_backend/routers/todo.py:299` (reusable upsert patterns)

**Acceptance Criteria**:
- `src/flow_backend/routers/sync.py` delegates `push()` to a service function (e.g., `sync_service.push(...)`) and no longer contains the full mutation loop.
- `src/flow_backend/routers/sync.py` contains no `await session.commit()` (commit owned by service/UoW).
- Unit tests can call service functions without ASGI server.
```bash
uv run pytest -q
```

**Recommended Agent Profile**:
- Category: `deep`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 1)
- Blocked By: Task 2

### 4) Add pytest-cov + CI Coverage Reporting + Core Gate

**What to do**:
- Add `pytest-cov` to dev dependencies.
- Update CI in two phases:
  - Phase 1: generate coverage report (no gate yet).
  - Phase 2 (after Task 3 exists + core logic moved): enforce core gate at 70%.

Sequencing rule (pinned):
- Implement Phase 1 immediately when adding `pytest-cov`.
- Enable Phase 2 gate only after Task 3 has landed and at least one non-trivial module exists under each core package (so CI does not fail due to missing modules/paths).
- Export coverage artifacts (e.g., `coverage.xml`) for later trend tracking.

**References**:
- `.github/workflows/ci.yml:26` (current steps)
- `pyproject.toml:25` (dev deps)

**Acceptance Criteria**:
```bash
# Phase 1: report only
uv run pytest -q --cov=flow_backend --cov-report=term-missing

# Phase 2: core-module gate
uv run pytest -q \
  --cov=flow_backend.domain \
  --cov=flow_backend.services \
  --cov=flow_backend.repositories \
  --cov=flow_backend.integrations \
  --cov-report=term-missing \
  --cov-fail-under=70
```

**Recommended Agent Profile**:
- Category: `quick`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 1)
- Blocked By: Task 1

### 4b) Expand Settings for v2 Features (share/S3/Memos)

**What to do**:
- Add the pinned env keys to `src/flow_backend/config.py` (do not add production enforcement here; that is Task 14).
- Ensure defaults are development-friendly (e.g., local attachments dir default), but missing secrets are allowed in development.
- Update `.env.example` to include the new keys (values blank or safe defaults).

**Files to create/edit (pinned)**:
- `src/flow_backend/config.py`
- `.env.example`

**Parallelization**:
- Can Run In Parallel: NO (touches central config)
- Blocked By: Task 1
- Blocks: Tasks 7, 8, 12, 14

**Acceptance Criteria**:
```bash
uv run pytest -q -k settings
```

### 5) Notes Data Model + Alembic Migrations (SQLite-first)

**What to do**:
- Add core tables:
  - `notes` (markdown content)
  - `note_tags` / `tags` (server-side filtering)
  - `note_revisions` (snapshots; includes conflict revisions)
  - `note_shares` (share token hash, expiry)
  - `attachments` + `note_attachments` (metadata, S3 key)
  - `note_remotes` (Memos mapping: provider+remote_id ↔ note_id)
- Ensure all are tenant/user-scoped (existing pattern uses `user_id` in `TenantRow`).
- Revision storage (pinned):
  - Store snapshot as JSON column (e.g., `snapshot_json`) containing `{title, body_md, tags, client_updated_at_ms}`.
  - Attachments are NOT embedded into snapshots (they are referenced via attachment tables).
  - Retention: unbounded in v2.0 (no revision GC); revisit later.
- Tags constraints (pinned):
  - Uniqueness scoped to `(user_id, name_lower)`.
  - Persist `name_original` for display, but matching/filtering uses `name_lower`.
- Add migration scripts and upgrade path.
- Alembic discovery rule (explicit): since `alembic/env.py` imports `flow_backend.models` to load SQLModel metadata, ensure Notes table models are imported by `flow_backend.models`.
  - Recommended: define notes tables in `flow_backend/models_notes.py` and import them in `flow_backend/models.py`.

**References**:
- `src/flow_backend/models.py:77` (TenantRow pattern)
- `src/flow_backend/models.py:150` (SyncEvent pattern for future notes sync)
- `alembic/env.py` (migration bootstrap)

**Acceptance Criteria**:
```bash
uv run alembic -c alembic.ini upgrade head
uv run pytest -q
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Task 3

### 6) Full-text Search for Notes (SQLite FTS5)

**What to do**:
- Implement search for notes on SQLite using FTS5.
- Migration strategy (locked): create FTS5 virtual table and triggers via Alembic `op.execute(...)` raw SQL (SQLite-first).
- Dialect guard (pinned): Alembic revision must detect dialect (e.g., `op.get_bind().dialect.name`).
  - If `sqlite`: apply FTS5 DDL + triggers.
  - If not `sqlite` (e.g., Postgres): NO-OP migration (do not run SQLite-specific SQL).
- FTS schema (pinned):
  - Virtual table `notes_fts(title, body_md, note_id UNINDEXED, user_id UNINDEXED)`.
  - Only index notes where `deleted_at IS NULL`.
  - Triggers maintain the index on insert/update/delete/restore.
- Provide a minimal cross-DB search interface so Postgres can be added later.
- Postgres behavior in v2.0 (pinned): implement a minimal fallback search using `ILIKE` over `title` and `body_md` (no ranking), so `/api/v2/notes?q=...` still works.

**Files to create/edit (pinned)**:
- `src/flow_backend/v2/routers/notes.py` (implement `q` filter)
- `src/flow_backend/services/notes_search_service.py`
- `src/flow_backend/repositories/notes_search_repo.py`
- Alembic revision under `alembic/versions/*` (FTS DDL guarded by dialect)
- Include tests for tokenization and basic ranking expectations (keep minimal; avoid over-promising).

**Acceptance Criteria**:
- Migration creates FTS artifacts.
- Search endpoint returns expected results for seeded notes.
```bash
uv run pytest -q -k notes_search
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Task 5

### 7) Attachments: Storage Abstraction + Tencent Cloud (S3-compatible)

**What to do**:
- Implement `ObjectStorage` interface.
- S3 client choice (locked): use `boto3`/`botocore` for S3-compatible access.
- Async execution tactic (pinned): run `boto3` calls via threadpool (e.g., `anyio.to_thread.run_sync` / `starlette.concurrency.run_in_threadpool`) to avoid blocking the event loop.
- CI mocking (locked): use `botocore.stub.Stubber` (or a fake `ObjectStorage` implementation) so CI never hits real Tencent Cloud.
- Dependency placement (pinned): `boto3` is a runtime dependency (add to `[project].dependencies` in `pyproject.toml`, not only dev extras).
- Provide:
  - local filesystem backend for dev/tests
  - S3-compatible backend for Tencent Cloud (endpoint/region/credentials from env)
- Add upload/download endpoints and ensure note markdown can reference attachments.
- Markdown reference semantics (pinned): backend does **not** rewrite markdown.
  - Clients embed stable URLs returned by the API.
  - Authenticated download: `/api/v2/attachments/{attachment_id}`
  - Public download under share: `/api/v2/public/shares/{share_token}/attachments/{attachment_id}`
- Add garbage-collection policy hooks (at minimum: soft-delete and future GC job placeholder).

Local backend layout (pinned):
- Root dir: `${ATTACHMENTS_LOCAL_DIR}`
- Store objects under: `${ATTACHMENTS_LOCAL_DIR}/{user_id}/{attachment_id}`

**Files to create/edit (pinned)**:
- `src/flow_backend/integrations/storage/object_storage.py` (interface)
- `src/flow_backend/integrations/storage/local_storage.py`
- `src/flow_backend/integrations/storage/s3_storage.py`
- `src/flow_backend/v2/routers/attachments.py`
- `src/flow_backend/v2/schemas/attachments.py`

**Config (env) expectations**:
- All S3 settings must be configurable via `.env` (endpoint, region, bucket, access key, secret key).
- Tencent Cloud should work via an S3-compatible endpoint override.

**Guardrails**:
- CI must not call real S3.

**Acceptance Criteria**:
- Unit tests use stubbed storage backend; no network.
- Upload/download flows pass with local backend.
```bash
uv run pytest -q -k attachments
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Tasks 1, 3, 4b, 5

### 8) Sharing: Anonymous Read-only Share Links with Expiry

**What to do**:
- Endpoint to create share link for a note.
- Store only token hash + optional prefix; never store plaintext token.
  - Hashing strategy (locked): `HMAC-SHA256(share_token_secret, share_token)`.
  - Store: `token_prefix` (e.g., first 8 chars) + `token_hmac_hex` + `expires_at` + `revoked_at`.
  - Validate tokens in constant-time compare.
  - Token format (pinned): `secrets.token_urlsafe(32)`.
- Endpoint to fetch shared note (read-only) with attachments.
  - Share URL composition (pinned): `${PUBLIC_BASE_URL}/api/v2/public/shares/{share_token}`
  - Expiry semantics (pinned): if `expires_in_seconds` omitted, set `expires_at = now + 7 days`.

Deleted/restore semantics for public shares (pinned; security):
- Shares can only be created for non-deleted notes.
- If the underlying note is soft-deleted:
  - `GET /api/v2/public/shares/{share_token}` returns 404 `ErrorResponse(error="not_found")`.
  - public attachment streaming under the share token also returns 404.
- If the note is restored later, the share becomes valid again unless it was revoked/expired.

**Files to create/edit (pinned)**:
- `src/flow_backend/v2/routers/shares.py` (authenticated create/revoke)
- `src/flow_backend/v2/routers/public.py` (public share read + attachment streaming)
- `src/flow_backend/v2/schemas/shares.py`

**Acceptance Criteria**:
- Tests verify plaintext token is not stored.
- Expired token returns 410 (Gone) with `ErrorResponse(error="gone")`.
- Revoked token returns 404 with `ErrorResponse(error="not_found")` (do not reveal existence).
- If the shared note is deleted, public share endpoint returns 404.
```bash
uv run pytest -q -k sharing
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Tasks 1, 4b, 5

### 9) Version History + Conflict Revisions

**What to do**:
- Store revisions on update (snapshot strategy; simple but reliable).
- On Memos-authoritative conflict, create a `CONFLICT` revision containing the local snapshot.
- Provide endpoints to list revisions and restore a revision.

Revision restore semantics (pinned):
- Restore applies to `title`, `body_md`, `tags`, and `client_updated_at_ms` (write op).
- Attachments are NOT restored/rewound (remain as current note attachments), since snapshots do not embed attachments.
- Restore requires `client_updated_at_ms` (same conflict rule as PATCH); stale restore returns 409.
- On restore success:
  - create a new revision snapshot of the pre-restore state
  - apply snapshot fields

**Files to create/edit (pinned)**:
- `src/flow_backend/services/note_revisions_service.py`
- `src/flow_backend/repositories/note_revisions_repo.py`
- `src/flow_backend/v2/routers/revisions.py`
- `src/flow_backend/v2/schemas/revisions.py`

**Acceptance Criteria**:
```bash
uv run pytest -q -k revisions
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Task 5

### 10) Notes CRUD + Tags Filter (v2 REST APIs)

**What to do**:
- Implement `/api/v2/notes` CRUD.
- Tags model (locked): normalized `tags` + `note_tags` tables.
  - API exposes `tags: list[str]` on `Note`.
  - On write: upsert tag names in `tags`, maintain join rows in `note_tags`.
  - On read/list: return tag names as `list[str]`.
- Ensure `response_model` is used everywhere.

**Files to create/edit (pinned)**:
- `src/flow_backend/v2/routers/notes.py` (CRUD + list)
- `src/flow_backend/v2/schemas/notes.py` (requests + responses)
- `src/flow_backend/services/notes_service.py`
- `src/flow_backend/repositories/notes_repo.py`

**Acceptance Criteria**:
- OpenAPI reflects typed schemas.
- Integration tests cover create/update/list/search flows.
```bash
uv run pytest -q -k api_v2_notes
```

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Tasks 1, 5

### 11) Notes Sync (Client ↔ Backend) Using Planner + SyncEvent

**What to do**:
- Extend sync model to include notes changes.
- Build a pure-function sync planner that outputs an apply-plan (upsert/delete/reject + reasons).
  - Planner contract (pinned):
    - Input: `(resource, entity_id, op, incoming_client_updated_at_ms, incoming_payload, server_row_snapshot)`
    - Output: `PlanResult` with:
      - `apply`: list of DB operations (upsert/delete/tombstone) + normalized fields
      - `reject`: optional rejection with `reason_code` + `server_snapshot` (for client reconciliation)
    - Invariants: deterministic; no DB/network; no time() calls (inject `now_ms` / `utc_now`)
  - Minimum conflict matrix (table-driven tests must cover):
    - create (no server row) → apply
    - update newer (incoming_ms >= existing_ms) → apply
    - stale update (incoming_ms < existing_ms) → reject `conflict`
    - delete newer → tombstone apply
    - delete stale → reject `conflict`
    - delete non-existent → apply idempotently
    - update of tombstoned note → reject `conflict` unless restore endpoint path is used
- Service applies plan; writes SyncEvent records.

**Files to create/edit (pinned)**:
- `src/flow_backend/domain/sync_planner.py` (pure planner)
- `src/flow_backend/services/sync_service.py` (session.begin + apply plan)
- `src/flow_backend/repositories/sync_repo.py` (DB I/O, no commit)
- `src/flow_backend/v2/routers/sync.py` (HTTP wiring)
- `src/flow_backend/v2/schemas/sync.py` (SyncPushRequest/Response, SyncPullResponse)

**References**:
- `src/flow_backend/routers/sync.py:95` (current SyncEvent pull/push)

**Acceptance Criteria**:
- Table-driven tests cover conflict matrix.
```bash
uv run pytest -q -k notes_sync
```

**Recommended Agent Profile**:
- Category: `deep`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 3)
- Blocked By: Tasks 5, 10

### 12) MemosConnector: Bidirectional Sync (Memos authoritative)

**What to do**:
- Implement `integrations/memos/*` connector.
- Define stable mapping between Memos entities and local Notes IDs.
  - Add a DB mapping table (example name: `note_remotes`) scoped by `user_id` with:
    - `provider` ("memos"), `remote_id`, `note_id`
    - `remote_updated_at` (or equivalent), optional `remote_etag`
    - `last_synced_at`, optional `last_seen_remote_updated_at`
- Make field-level authority explicit to avoid ping-pong:
  - Memos-authoritative: note `title`, `body_md`, `tags` (default)
  - First-party only: attachments, shares, revision history

**Pinned JSON mapping rules (Memos → Note)**:
- `remote_id`: prefer `id`; else `name`; else `uid`.
- `body_md`: prefer `content`; else `body`; else `markdown`.
- `title`: if remote has `title`, use it; else derive from first non-empty line of `body_md`.
- `tags`: if remote has `tags` as list, use it; else derive by regex `#(\w+)` from `body_md` (minimal fallback).
- `remote_updated_at` extraction order:
  - prefer integer `updatedTs` (seconds) or `updated_at_ms`
  - else parse RFC3339 `updateTime` / `updatedAt`
  - else fallback to created timestamp.

Normalization (pinned):
- Convert remote timestamps into `remote_updated_at_ms` for comparisons.
- Normalize tags to lowercase for DB uniqueness, but preserve original in payload if available.

Auth context for Memos note CRUD (pinned):
- Base URL: `settings.memos_base_url` (global; matches current app behavior returning `server_url`).
- Auth header: `Authorization: Bearer {user.memos_token}` (per-user token).
- Admin token is NOT used for note CRUD (reserved for provisioning flows in existing `MemosClient`).
- Implement idempotency rules (testable):
  - Always pull remote state before applying push for the same note.
  - If remote changed since last_seen_remote_updated_at → treat as conflict (remote wins), create `CONFLICT` revision from local snapshot.
  - If remote unchanged → push local changes; update mapping.
- Implement:
  - pull from Memos into local notes
  - push local notes to Memos
- On conflict: Memos wins; local snapshot stored as conflict revision.
- Ensure idempotency to avoid sync ping-pong.

**Invocation flow (pinned)**:
- Add a dedicated v2 endpoint (example): `POST /api/v2/integrations/memos/sync`.
  - It performs: `pull` then `push` for the authenticated user, with strict timeouts.
  - It returns a summary `{pulled, pushed, conflicts}`.
- Client ↔ backend sync (`/api/v2/sync/*`) remains local-first and does not require Memos to be reachable.
- Conflicts surfaced by Memos sync appear as:
  - `NoteRevision(kind=CONFLICT)` rows
  - note updates recorded as sync events so clients can observe the new state.

**Config (env) expectations**:
- Note CRUD endpoints on Memos may vary by Memos version; use a compatibility strategy similar to token provisioning.
- Allow overriding endpoints via env lists (like existing `MEMOS_CREATE_*_ENDPOINTS`) to keep the connector adaptable.
  - Baseline discovery (pinned): attempt to fetch Memos OpenAPI first:
    - `GET {MEMOS_BASE_URL}/api/v1/openapi.json` (fallback: `/openapi.json`)
    - Derive note/memo CRUD paths from OpenAPI if available.
  - If discovery is unavailable, fallback to env endpoint lists.
  - Initial default fallback (best-effort): list/create at `/api/v1/memos`, update/delete at `/api/v1/memos/{id}`.

**Test doubles (pinned; CI has no live Memos)**:
- Test mechanism (pinned): use `httpx.MockTransport` to return deterministic OpenAPI + memos CRUD responses.
- Injection point (pinned): MemosConnector constructor accepts an optional `httpx.AsyncClient` (or `transport`) so tests can pass `MockTransport` without monkeypatching.
- Mock OpenAPI response includes at least:
  - `paths` with `{"/api/v1/memos": {"get":..., "post":...}, "/api/v1/memos/{id}": {"patch":..., "delete":...}}`
- Mock list response (GET) primary shape (used in tests): `{ "items": [ ... ] }`.
  - Connector may optionally also accept `{ "memos": [ ... ] }` as a compatibility fallback.
- Mock upsert response returns the created/updated memo object including at least the fields used in mapping rules.

**References**:
- `src/flow_backend/memos_client.py` (existing client + compatibility strategy)
- `src/flow_backend/routers/auth.py:40` (Memos client usage)

**Acceptance Criteria**:
- Tests run without external Memos (mock transport).
- Conflict test: local edit + remote change → local becomes conflict revision and local state matches Memos.
```bash
uv run pytest -q -k memos_sync
```

**Recommended Agent Profile**:
- Category: `deep`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 3)
- Blocked By: Tasks 4b, 11

### 13) TODO Enhancements (server-side tag filter)

**What to do**:
- Implement server-side tag filtering for todo items.
- Tags model decision (explicit):
  - v2 notes uses normalized tags (Task 10).
  - v2 todo should use the same normalized tag approach (add `todo_item_tags` join table) to avoid SQLite/Postgres JSON-dialect differences.
  - v1 todo remains unchanged (this task is v2-only).

**DB/Migration steps (pinned)**:
- Add SQLModel table(s) for `todo_item_tags` in a dedicated module (example: `src/flow_backend/models_todo_tags.py`) and import into `src/flow_backend/models.py` so Alembic sees metadata.
- Create an Alembic revision and upgrade head.

Tags source-of-truth + backfill (pinned):
- Source of truth for stored tags remains `todo_items.tags_json` for backward compatibility.
- `todo_item_tags` is a derived/index table used for efficient filtering across SQLite/Postgres.
- Migration backfill requirement: populate `todo_item_tags` from existing `todo_items.tags_json` for all non-deleted items during the Alembic revision (so v2 tag filter works on existing data).
- Ongoing consistency requirement (v2 branch):
  - v2 todo writes update BOTH `tags_json` and `todo_item_tags`.
  - v1 todo writes (if still used) also update `todo_item_tags` to keep derived index in sync, without changing v1 API responses.

**Files to create/edit (pinned)**:
- `src/flow_backend/v2/routers/todo.py` (implement tag filter)
- `src/flow_backend/v2/schemas/todo.py`
- `src/flow_backend/services/todo_service.py`
- `src/flow_backend/repositories/todo_repo.py`

**References**:
- Anti-pattern reference (v1 code to avoid copying into v2): `src/flow_backend/routers/todo.py:248`

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Task 1

**Acceptance Criteria**:
```bash
uv run alembic -c alembic.ini upgrade head
uv run pytest -q -k todo_tag_filter
```

### 14) Observability & Ops Hardening

**What to do**:
- Ensure request-id middleware is present (owned by Task 1) and integrate it into logging/error handling.
- Add structured error logging for exceptions.
- Ensure security-sensitive defaults are safe (CORS, admin secrets) in non-dev.
  - Add `ENVIRONMENT` setting with values: `development` (default) / `production`.
  - In `production`:
    - `ADMIN_BASIC_PASSWORD` must be set and not a placeholder.
    - `SHARE_TOKEN_SECRET` must be set.
    - If attachments enabled, S3 config must be complete.
    - CORS must not default to `*` (require explicit `CORS_ALLOW_ORIGINS`).
      - Compatibility: if `CORS_ORIGINS` is set, treat it as an alias for `CORS_ALLOW_ORIGINS` (but `CORS_ALLOW_ORIGINS` wins if both are set).
  - In `development`: keep permissive defaults for local iteration.

Ownership split (pinned):
- Task 1 installs the minimal request-id middleware.
- Task 14 extends it with structured logging and production validation (do not re-implement a second request-id system).

**Files to create/edit (pinned)**:
- `src/flow_backend/config.py` (add share/S3 settings and enforce production validation; `ENVIRONMENT` + `DEVICE_TRACKING_ASYNC` are introduced in Task 2)
- `src/flow_backend/v2/app.py` (install v2 exception handlers; request-id middleware lives on the main app only)

**Acceptance Criteria**:
- Tests validate error shape and request-id propagation.
- Settings validation tests:
  - `ENVIRONMENT=production` + missing secrets → app fails fast (raises validation error)
  - `ENVIRONMENT=development` → app starts with local defaults
```bash
uv run pytest -q -k observability
```

### 15) Remove Hard-coded tzid in v2 (correctness)

**What to do**:
- Scope boundary (explicit): v1 keeps current hard-coded tzid behavior; v2 corrects it.
- Ensure v2 todo + v2 sync paths do not override tzid with hard-coded literals.
- Centralize time parsing/normalization utilities used by v2 sync and v2 todo.

**References**:
- Anti-pattern references (v1 code to avoid copying into v2):
  - `src/flow_backend/models.py:128` (existing hard-coded default tzid)
  - `src/flow_backend/routers/sync.py:328` (tzid hard-coded in sync push)
  - `src/flow_backend/routers/todo.py:340` (tzid hard-coded in todo upsert)

**Recommended Agent Profile**:
- Category: `unspecified-high`
- Skills: `git-master`

**Parallelization**:
- Can Run In Parallel: YES (Wave 2)
- Blocked By: Task 3

**Acceptance Criteria**:
- Unit tests cover tzid behavior in v2 todo (payload tzid preserved; fallback to `settings.default_tzid`).
- A v1 regression test confirms tzid remains hard-coded in v1 behavior (behavior-compat guardrail).
```bash
uv run pytest -q -k tzid
```

---

## Defaults Applied (explicit)

- Multi-user data model continues (existing `users` table). Notes are scoped to `user_id`.
- Memos authoritative applies to note content and tags by default.
- Attachments and shares are first-party only (not mirrored into Memos unless Memos supports it cleanly); connector may store references/links.
- Search feature scope: minimal cross-DB semantics; advanced tokenization/highlighting is out of scope.

---

## Decisions Needed (if you want to override defaults)

- Attachment constraints: max size, allowed MIME types.
- Retention/GC policy: when notes deleted or shares expire, whether attachments are retained.

---

## Success Criteria (final)

```bash
uv sync --extra dev --frozen
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv run pytest -q \
  --cov=flow_backend.domain \
  --cov=flow_backend.services \
  --cov=flow_backend.repositories \
  --cov=flow_backend.integrations \
  --cov-report=term-missing \
  --cov-fail-under=70
```

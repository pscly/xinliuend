# XinLiu User Frontend (web/)

Next.js (App Router) user frontend scaffold.

Key references:

- Next export config: `web/next.config.ts`
- Backend static mount (serves `web/out` on `/`): `src/flow_backend/main.py`
- Playwright E2E runner (builds export + starts backend): `web/playwright.config.ts`

## Features

- App Router + `src/` directory
- CN/EN i18n (client context) with visible language toggle
- Dark mode (system default + manual toggle, persisted)
- Design tokens via CSS variables (components avoid hardcoded colors)
- Core routes: `/`, `/notes`, `/todos`, `/calendar`, `/search`, `/settings`
- Playwright smoke test that takes light/dark screenshots

## Local dev

Local dev is typically two processes on two ports:

1) Backend API (port 31031):

```powershell
uv run uvicorn flow_backend.main:app --host 127.0.0.1 --port 31031 --reload
```

2) Next dev server (port 3000):

```bash
cd web
npm ci
npm run dev
```

Open http://localhost:3000

## Backend proxy (cookie auth ready)

By default, Next rewrites these paths to the backend on port 31031:

- `/api/v1/*` -> `http://localhost:31031/api/v1/*`

Disable the proxy if you want to handle routing/CORS yourself:

Windows env var examples:

```cmd
set NEXT_DISABLE_BACKEND_PROXY=1
```

```powershell
$env:NEXT_DISABLE_BACKEND_PROXY = "1"
```

Override backend URL:

```cmd
set BACKEND_BASE_URL=http://localhost:31031
```

```powershell
$env:BACKEND_BASE_URL = "http://localhost:31031"
```

### Cookie-session + CSRF notes

When using cookie-session auth, write requests (POST/PUT/PATCH/DELETE) must include
the `X-CSRF-Token` header (Bearer auth does not use CSRF).

- Frontend obtains `csrf_token` from `GET /api/v1/me`.
- Requests sent via the shared API helper (`web/src/lib/api/client.ts`) inject
  `X-CSRF-Token` automatically when a token is present.

If you disable the proxy and call the backend directly from the browser (different
origin), you will also need to handle CORS and `fetch(..., { credentials: "include" })`.

## Prod-like same-origin (static export served by FastAPI)

This repo uses `output: "export"` to produce a fully static site under `web/out/`.
The backend mounts it at `/` (same origin as `/api/*`) when `web/out/index.html` exists.

1) Build the static export:

```bash
cd web
npm ci
npm run build
```

2) Start the backend and open the UI on the backend origin:

- UI: http://localhost:31031/
- API: http://localhost:31031/api/v1/...

Backend env vars:

- `FLOW_DISABLE_WEB_STATIC=1` to disable mounting
- `FLOW_WEB_OUT_DIR=...` to override the directory (defaults to `web/out`)

Note: Next prints warnings that `rewrites` are ignored under `output: "export"`
during `npm run build`. This is expected; rewrites still apply to `npm run dev`.

## E2E (Playwright)

```bash
cd web
npx playwright test
```

What it does (see `web/playwright.config.ts`):

- Runs `npm run build` to generate `web/out` (export mode cannot run via `next start`)
- Runs `alembic upgrade head`
- Starts the backend on `http://127.0.0.1:31031` and runs tests against that origin

Database + env overrides used by the Playwright-launched backend:

- `DATABASE_URL=sqlite:///./playwright-e2e.db`
- `DEV_BYPASS_MEMOS=true`
- Disables auth rate limits for determinism:
  - `AUTH_REGISTER_RATE_LIMIT_PER_IP=0`
  - `AUTH_LOGIN_RATE_LIMIT_PER_IP=0`
  - `AUTH_LOGIN_RATE_LIMIT_PER_IP_USER=0`
  - `ADMIN_LOGIN_RATE_LIMIT_PER_IP=0`
- `DEVICE_TRACKING_ASYNC=false` to avoid background writes on SQLite

Output:

- Screenshots + traces are written under `web/test-results/`.

Tip: by default Playwright will reuse an already running server on port 31031
(`reuseExistingServer`), so stop your local backend first if you want a clean E2E run,
or set `CI=1` to force Playwright to manage the server lifecycle.

## Troubleshooting

- UI 404 on `http://localhost:31031/`: ensure `web/out/index.html` exists (run `npm run build`).
- Flaky auth (429 / Retry-After): local concurrency can trip rate limiting; E2E disables it via env.
- SQLite `database is locked`: ensure only one backend/test process uses the DB; stop the server and retry.
- Windows file locks: if you see errors about files in use (node_modules, `uv.lock`), close other processes and retry.

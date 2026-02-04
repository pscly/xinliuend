# Web Local Dev & Deploy (Same-Site Cookie Auth)

This doc explains how to run the backend + `web/` frontend locally, and how to deploy them in a way that keeps cookie-based auth stable (same-site, preferably same-origin).

Repo defaults (today):

- Backend: `http://localhost:31031`
- Web (Next dev server): `http://localhost:3000`

## 1) Recommended local dev: same-origin via Next rewrites (no CORS)

Goal: browser stays on `http://localhost:3000`, while `/api/v1/*` and `/api/v2/*` are proxied to the backend.

### 1.1 Start backend (SQLite + dev bypass)

In repo root:

```powershell
Copy-Item .env.example .env -Force

# Stable local defaults
$env:DATABASE_URL = "sqlite:///./dev.db"
$env:DEV_BYPASS_MEMOS = "true"

uv sync
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

Verify:

- `http://localhost:31031/health`
- `http://localhost:31031/admin` (backend-rendered admin UI)

### 1.2 Start web (Next.js)

In a new terminal:

```powershell
cd web
npm ci

# Optional: point rewrites to a non-default backend base URL
# $env:BACKEND_BASE_URL = "http://localhost:31031"

npm run dev
```

Open:

- Web: `http://localhost:3000`
- API (proxied): `http://localhost:3000/api/v1/...`

### 1.3 How cookie auth works in this mode

`web/next.config.ts` rewrites:

- `/api/v1/*` -> `http://localhost:31031/api/v1/*`
- `/api/v2/*` -> `http://localhost:31031/api/v2/*`

From the browser's perspective, the API is same-origin (`localhost:3000`). That means:

- No CORS preflight/config needed.
- The backend's `Set-Cookie` is stored for host `localhost` (cookies do not depend on port), and subsequent `/api/...` requests automatically include it.
- The frontend can keep using relative URLs like `/api/v1/me`.

Important: `/admin` is NOT rewritten by Next. It remains backend-rendered and should be visited at `http://localhost:31031/admin` during local dev.

## 2) Cookie session + CSRF (must-read)

Backend supports two auth modes:

- Bearer token: `Authorization: Bearer <memos_token>` (no CSRF).
- Cookie session: httpOnly session cookie (requires CSRF header for state-changing methods).

### 2.1 Session cookie details

Defaults in `src/flow_backend/config.py`:

- Cookie name: `flow_session` (`USER_SESSION_COOKIE_NAME`)
- Cookie is `HttpOnly`, `SameSite=Lax`, `Path=/`
- `Secure` is enabled automatically on HTTPS (or when `TRUST_X_FORWARDED_PROTO=true` behind a reverse proxy)

### 2.2 CSRF rule

When you authenticate via cookie session:

- Safe methods (`GET`, `HEAD`, `OPTIONS`) do NOT require CSRF.
- State-changing methods (`POST`, `PUT`, `PATCH`, `DELETE`) MUST include the CSRF header.

Header name (configurable):

- `X-CSRF-Token` (`USER_CSRF_HEADER_NAME`)

The CSRF token value is returned by:

- `POST /api/v1/auth/login` -> `data.csrf_token`
- `POST /api/v1/auth/register` -> `data.csrf_token`

### 2.3 SPA refresh / CSRF rehydration

Because the session cookie is httpOnly, the SPA cannot read it directly. After a page reload, rehydrate the CSRF token by calling:

- `GET /api/v1/me` -> `data.csrf_token`

Recommended client flow:

1) On login/register success: store `data.csrf_token` in memory (or session storage).
2) On SPA boot (and whenever you lose CSRF in memory): call `GET /api/v1/me` and refresh the CSRF token.
3) For every non-safe request under cookie auth: set header `X-CSRF-Token: <csrf_token>`.

### 2.4 Logout endpoint

Use:

- `POST /api/v1/auth/logout`

Rules:

- Idempotent (OK even if already logged out).
- If a valid cookie-session exists, CSRF is required (prevents cross-site logout).
- If you are using Bearer auth, CSRF is NOT required for this endpoint.

## 3) Local alternative: no Next proxy + direct cross-origin (CORS + cookies)

Use this when you want to test the real browser CORS behavior (or you plan to run web + api on different origins).

### 3.1 Disable Next rewrites

In the terminal where you run `npm run dev`:

```powershell
$env:NEXT_DISABLE_BACKEND_PROXY = "1"
```

Notes:

- With rewrites disabled, calls to relative `/api/v1/...` will hit the web origin (`localhost:3000`) and will NOT reach the backend.
- For cross-origin mode, your frontend requests must target the backend origin explicitly, e.g. `http://localhost:31031/api/v1/...`.

### 3.2 Configure backend CORS for cookie auth

Backend uses Starlette `CORSMiddleware` and derives `allow_credentials` from `CORS_ALLOW_ORIGINS`:

- If `CORS_ALLOW_ORIGINS='*'`: `allow_credentials` is forced to `false` (cookies will not work cross-origin).
- If `CORS_ALLOW_ORIGINS` is an explicit allowlist (comma-separated, no `*`): `allow_credentials=true` is enabled.

Example (allow local web origin):

```powershell
# IMPORTANT: no '*' when you need cookies.
$env:CORS_ALLOW_ORIGINS = "http://localhost:3000"

uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031 --reload
```

Browser fetch requirements:

- `credentials: "include"` (already the default in `web/src/lib/api/client.ts`)
- For cookie-session + non-safe methods: include `X-CSRF-Token`.

Pitfalls:

- Keep hostnames consistent. `http://localhost:3000` and `http://127.0.0.1:3000` are different origins.
- If you run E2E against `http://127.0.0.1:3000`, make sure your CORS allowlist (when needed) includes that exact origin.
- Cookies are `SameSite=Lax` (good for same-site setups like subdomains or different ports under the same site). For truly cross-site deployments, cookie auth will likely not work without changing cookie policy.

## 4) Prod-like deployment shapes (keep /admin backend-rendered)

Key requirement: `/admin` is backend HTML and must NOT be handled by the Next app.

### 4.1 Recommended: reverse proxy (one public origin)

Put Nginx/Caddy/Traefik in front of both services and make the browser see ONE origin.

Routing idea:

- `/` -> Next (either `next start` or static files)
- `/api/v1/*` and `/api/v2/*` -> backend (`flow_backend`)
- `/admin` -> backend (`flow_backend`)  (do NOT let Next shadow it)

Benefits:

- No CORS.
- Cookie auth is simplest.
- You can terminate TLS at the proxy.

When terminating TLS at a proxy, enable in backend:

- `TRUST_X_FORWARDED_PROTO=true` (so Secure cookies are set correctly)

### 4.2 Static export (SPA) vs running a Next server

If you want a pure static SPA, Next can be configured for static export (build-time HTML + assets) and served by any static server.

Trade-offs to keep in mind:

- Static export forbids server-only runtime features (e.g. no server `cookies()`/`headers()` usage in the Next app).
- Prefer client-side cookie auth (`fetch` with `credentials: "include"`).
- If you later enable static export, be careful with Next built-in `i18n` config; route-segment locale patterns are more compatible.

If you run a Next server (`npm run build` + `npm run start`), you still typically want a reverse proxy in front to route `/admin` and `/api/*` to the backend.

### 4.3 Single service (same origin): backend serves `web/out`

This repo supports a production-like layout without an external reverse proxy:

- Build the Next app as a static export (`web/out/`).
- Run ONLY the backend; it serves the exported UI on `/`.

This keeps cookie-session auth simple because the browser sees one origin.

Steps:

1) Build the static export:

```powershell
cd web
npm ci
npm run build
```

Expect output under:

- `web/out/` (e.g. `web/out/index.html`)

2) Run the backend:

```powershell
uv run uvicorn flow_backend.main:app --host 0.0.0.0 --port 31031
```

3) Open:

- Web UI: `http://localhost:31031/`
- API: `http://localhost:31031/api/v1/...` and `http://localhost:31031/api/v2/...`
- Admin (backend-rendered): `http://localhost:31031/admin`

Notes:

- Routing precedence is preserved because `/api/*` and `/admin` are registered before the static mount.
- Static serving is best-effort: the backend only mounts the UI if `web/out/index.html` exists.
- During `npm run build`, Next may warn that `rewrites` are ignored for `output: 'export'` (expected; rewrites are for `npm run dev`).
- Disable static serving explicitly with `FLOW_DISABLE_WEB_STATIC=1`.
- Override the export directory with `FLOW_WEB_OUT_DIR` (absolute or relative path).

## 5) Env vars: local + E2E stability checklist

Backend (common local / CI smoke):

- `DATABASE_URL=sqlite:///./dev.db`
- `DEV_BYPASS_MEMOS=true` (local dev only)

Backend (when running cross-origin without Next proxy):

- `CORS_ALLOW_ORIGINS=http://localhost:3000` (explicit allowlist; no wildcard)

Web:

- `BACKEND_BASE_URL=http://localhost:31031` (only affects Next rewrites)
- `NEXT_DISABLE_BACKEND_PROXY=1` (turn off rewrites)
- `NEXT_PUBLIC_APP_ORIGIN=http://localhost:3000` (server-side fetch base; set in deployments)

## 6) Quick manual sanity checks (copy/paste)

These examples assume the recommended local dev mode (API via `localhost:3000` rewrites).

Login + save cookies:

```powershell
curl -c .tmp.cookies.txt -H "Content-Type: application/json" `
  -d '{"username":"demo","password":"pass1234"}' `
  http://localhost:3000/api/v1/auth/login
```

Get CSRF token after refresh (cookie-session):

```powershell
curl -b .tmp.cookies.txt http://localhost:3000/api/v1/me
```

Logout (requires CSRF when cookie-session is valid):

```powershell
# Replace <csrf> with the token from /api/v1/me or login response
curl -b .tmp.cookies.txt -H "X-CSRF-Token: <csrf>" -X POST http://localhost:3000/api/v1/auth/logout
```

## 7) Troubleshooting

- `http://localhost:31031/` returns 404: you probably didn't build the export yet. Run `cd web && npm ci && npm run build` and confirm `web/out/index.html` exists.
- Cookies not sticking / login loops: keep hostnames consistent. `localhost` and `127.0.0.1` are different cookie hosts.
- `/admin` looks wrong: make sure you're visiting the backend origin (`http://localhost:31031/admin`). It is not part of the Next export.

# Issues (frontend-guofeng)

## 2026-02-03 Task: bootstrap
- TBD.

## 2026-02-03 Task: initial-audit
- Task 3 gap: static export (`output: 'export'`) is not enabled in `web/next.config.ts`, and FastAPI does not serve `web/out` yet (no `StaticFiles` mounts in `src/flow_backend/main.py`).
- E2E gap: `web/tests/smoke.spec.ts` hits `/` without a backend running; Next rewrite proxy logs ECONNREFUSED for `/api/v1/me`.
- Tooling gap: `lsp_diagnostics` is blocked on Windows because Bun v1.3.5 is known to crash; cannot satisfy "project-level LSP clean" until Bun upgraded.

## 2026-02-03 Task: deploy-export
- Next prints warnings that `rewrites` are ignored under `output: 'export'` during `npm run build` (expected; rewrites remain useful for `npm run dev`).
- Backend emits SECURITY WARNING logs in dev if placeholder secrets are used; Playwright run will show these. Consider setting real `.env` values for quieter logs.

## 2026-02-03 Task: deploy-same-origin-static-export
- Static export build can fail if the Next app uses server-only runtime features; keep UI pages compatible with `output: "export"`.
- If `http://localhost:31031/` 404s, check that `web/out/index.html` exists (backend mount is best-effort by design).
- Regression caught by tests: after mounting static at `/`, requests to unknown `/api/v1/*` endpoints can return HTML instead of JSON. Fix: add a v1 catch-all 404 route before the static mount.

## 2026-02-03 Task: share-suspense-build
- Next export build can fail with `useSearchParams() should be wrapped in a suspense boundary at page "/share"` when `useSearchParams` lives in the route entry.
- Fix: keep `web/src/app/share/page.tsx` as a tiny server component that renders a client component inside `<Suspense>`, and move the existing logic into `web/src/app/share/ShareClient.tsx`.

## 2026-02-03 Task: task9-notifications-center
- `lsp_diagnostics` still refuses to start on Windows and reports an internal Bun v1.3.5 crash guard even after installing/using Bun >= 1.3.6; fallback verification is `uv run pytest`.

## 2026-02-04 Task: task10-e2e-stability
- Playwright default parallelism (12 workers) can exceed auth rate limits (429) and cause SQLite `database is locked` during concurrent register/login.
- Fix applied in `web/playwright.config.ts`: force `workers: 1` and set Playwright-launched backend env overrides `AUTH_*_RATE_LIMIT_*=0` + `DEVICE_TRACKING_ASYNC=false`.
- Result: `npx playwright test` passes deterministically on Windows.

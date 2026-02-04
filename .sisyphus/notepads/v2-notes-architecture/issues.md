# Issues

## 2026-01-30 Session Start
- None yet.

## 2026-01-31 basedpyright LSP Staleness
- In this environment, the `basedpyright-langserver` process sometimes kept stale file contents after disk-only edits; restarting the process was required to refresh `lsp_diagnostics`.

## 2026-01-31 Diagnostics Refresh Workaround
- `lsp_diagnostics` can keep reporting pre-edit warnings/errors until `basedpyright-langserver` is restarted (e.g., via `taskkill`).

## 2026-01-31 Ruff E402 in v2 Routers
- Root cause: module docstring was placed after `from __future__ import annotations`, making subsequent imports appear "not at top of file".
- Fix pattern: ensure exactly one module docstring is the first statement, then put `from __future__ import annotations` immediately after, then all other imports.

## 2026-01-31 PytestUnhandledThreadExceptionWarning (aiosqlite)
- On Windows + anyio/asyncio, cached `AsyncEngine` connections can leave an `aiosqlite` worker thread alive past the per-test event loop teardown.
- Symptom: `PytestUnhandledThreadExceptionWarning` with `RuntimeError: Event loop is closed` coming from `aiosqlite.core._connection_worker_thread`.
- Fix: add a function-scope autouse fixture in `tests/conftest.py` that disposes the cached engine after each test (and depends on `anyio_backend` so it tears down before the loop fixture).
- Keep `pytest_sessionfinish` as a final safety net.

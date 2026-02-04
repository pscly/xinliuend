# Issues

## 2026-02-02
- (init) API/doc audit notepad created.

## 2026-02-02 (2)
- P0: `docs/api.zh-CN.md` 413 error example code mismatch: docs show `http_413`, but v2 runtime maps 413 to `payload_too_large` (see `src/flow_backend/v2/app.py`).
- P0: OpenAPI snapshots under `docs/` do not declare optional request header parameter `X-Request-Id` even though `docs/api.zh-CN.md` says clients can send it (currently only response header is documented).
- P1: v2 422 nuance: some validation failures return `validation_error` vs generic `http_422`; clarify this in `docs/api.zh-CN.md` so client error branching is stable.
- P1: Shares `expires_in_seconds` doc gap: default behavior and accepted range are not documented in `docs/api.zh-CN.md`.
- P2: Storage backend doc gap: local vs S3 should be client-transparent; document this guarantee (and any URL/key differences) in `docs/api.zh-CN.md`.

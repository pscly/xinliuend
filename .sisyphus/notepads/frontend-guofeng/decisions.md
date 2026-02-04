# Decisions (frontend-guofeng)

## 2026-02-03 Task: bootstrap
- TBD.

## 2026-02-03 Task: notes-editor-mvp
- Notes editor MVP stays dependency-free: textarea + toolbar that inserts Markdown syntax; optional preview is plain-text.
- Rationale: static export compatibility and low-risk baseline; can swap to MDXEditor/Toast UI later if we need true WYSIWYG.


## 2026-02-03 Task: markdown editor (Next.js App Router + output: export)
- Recommended: `@mdxeditor/editor` (MDXEditor). Markdown is the single source of truth (in/out as string), WYSIWYG-ish UX, plugin-based so we can keep features lean; must be client-only (Next dynamic import with `ssr:false`).
- Alternative (richer but heavier): `@toast-ui/editor` (TOAST UI Editor). Supports markdown + WYSIWYG modes and has an official dark theme; treat as client-only and lazy-load to avoid bloating initial bundles.
- Alternative (lighter/mobile-friendly but less WYSIWYG): `@uiw/react-md-editor`. Textarea-based markdown editor with preview and built-in dark mode support; good fallback if we want minimal dependencies.
- Static export constraint: keep editing UI in client components only; avoid server actions / server-only deps; prefer route-level code-splitting (lazy-load the editor on edit pages).

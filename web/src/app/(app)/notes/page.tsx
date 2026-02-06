"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ReadonlyURLSearchParams } from "next/navigation";
import { useRouter, useSearchParams } from "next/navigation";

import { NotesApiErrorException, createNote, getNote, listNotes, patchNote } from "@/features/notes/notesApi";
import type { Note } from "@/features/notes/types";
import { Page } from "@/features/ui/Page";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";
import { cacheGetNote, cacheListNotes, cacheUpsertNote, cacheUpsertNotes } from "@/lib/offline/notesCache";
import { useOfflineEnabled } from "@/lib/offline/useOfflineEnabled";

type ShareCreateResponse = {
  share_id: string;
  share_url: string;
  share_token: string;
};

function parseShareCreateResponse(v: unknown): ShareCreateResponse | null {
  if (!v || typeof v !== "object") return null;
  const o = v as Record<string, unknown>;
  const share_id = o.share_id;
  const share_url = o.share_url;
  const share_token = o.share_token;
  if (typeof share_id !== "string" || !share_id) return null;
  if (typeof share_url !== "string" || !share_url) return null;
  if (typeof share_token !== "string" || !share_token) return null;
  return { share_id, share_url, share_token };
}

function extractApiErrorMessage(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (parsed && typeof parsed === "object") {
      const p = parsed as Record<string, unknown>;
      const msg = p.message ?? p.error;
      if (typeof msg === "string" && msg.trim()) return msg.trim();
    }
  } catch {
    // Ignore JSON parse failures; fall back to raw text.
  }
  return trimmed;
}

function noteTitle(n: Note, untitled: string): string {
  const t = n.title?.trim();
  if (t) return t;
  const firstLine = n.body_md.split("\n")[0]?.trim();
  return firstLine ? firstLine.slice(0, 80) : untitled;
}

function noteSnippet(n: Note): string {
  const s = n.body_md.replace(/\s+/g, " ").trim();
  if (!s) return "";
  return s.length > 110 ? `${s.slice(0, 110)}…` : s;
}

function buildNotesHref(current: ReadonlyURLSearchParams, noteId?: string): string {
  const sp = new URLSearchParams(current.toString());
  if (noteId) sp.set("id", noteId);
  else sp.delete("id");
  const qs = sp.toString();
  return qs ? `/notes?${qs}` : "/notes";
}

export default function NotesPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedId = searchParams.get("id") ?? "";
  const { user } = useAuth();
  const { locale, t } = useI18n();
  const { offlineEnabled } = useOfflineEnabled();
  const offlineUserKey = user?.username ?? null;

  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(null);

  const [notes, setNotes] = useState<Note[]>([]);
  const [notesLoading, setNotesLoading] = useState(true);
  const [notesError, setNotesError] = useState<string | null>(null);

  const [noteLoading, setNoteLoading] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [note, setNote] = useState<Note | null>(null);

  const [editorBody, setEditorBody] = useState("");
  const [editorMode, setEditorMode] = useState<"markdown" | "rich">("markdown");
  const [showPreview, setShowPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [conflictSnapshot, setConflictSnapshot] = useState<Note | null>(null);
  const [creating, setCreating] = useState(false);

  const [shareCreating, setShareCreating] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareCopied, setShareCopied] = useState(false);

  // Prevent stale request writes when switching selection quickly.
  const loadTokenRef = useRef(0);

  const refreshNotesList = useCallback(async () => {
    setNotesError(null);
    setNotesLoading(true);
    try {
      if (offlineEnabled && offlineUserKey) {
        try {
          const cached = await cacheListNotes(offlineUserKey);
          if (cached.length) {
            cached.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
            setNotes(cached);
          }
        } catch {
          // Best-effort: cache should not block online refresh.
        }
      }

      const res = await listNotes({ limit: 100, offset: 0 });
      setNotes(res.items);
      if (offlineEnabled && offlineUserKey) {
        await cacheUpsertNotes(offlineUserKey, res.items);
      }
    } catch (e) {
      setNotesError(e instanceof Error ? e.message : t("notes.error.loadNotes"));
    } finally {
      setNotesLoading(false);
    }
  }, [offlineEnabled, offlineUserKey, t]);

  useEffect(() => {
    void refreshNotesList();
  }, [refreshNotesList]);

  const applyEditorTransform = useCallback(
    (fn: (text: string, start: number, end: number) => { nextText: string; nextStart: number; nextEnd: number }) => {
      const el = textareaRef.current;
      const selectionStart = el?.selectionStart;
      const selectionEnd = el?.selectionEnd;

      setEditorBody((prev) => {
        const start = selectionStart ?? prev.length;
        const end = selectionEnd ?? prev.length;
        const res = fn(prev, start, end);
        pendingSelectionRef.current = { start: res.nextStart, end: res.nextEnd };
        return res.nextText;
      });
      setSaved(false);
      setConflictSnapshot(null);

      // Apply cursor/selection after React updates the textarea value.
      requestAnimationFrame(() => {
        const sel = pendingSelectionRef.current;
        const nextEl = textareaRef.current;
        if (!sel || !nextEl) return;
        nextEl.focus();
        nextEl.setSelectionRange(sel.start, sel.end);
        pendingSelectionRef.current = null;
      });
    },
    [],
  );

  const insertWrap = useCallback(
    (before: string, after: string, placeholder: string) => {
      applyEditorTransform((text, start, end) => {
        const selected = text.slice(start, end);
        const inner = selected || placeholder;
        const inserted = `${before}${inner}${after}`;
        const nextText = `${text.slice(0, start)}${inserted}${text.slice(end)}`;
        const innerStart = start + before.length;
        const innerEnd = innerStart + inner.length;
        return { nextText, nextStart: innerStart, nextEnd: innerEnd };
      });
    },
    [applyEditorTransform],
  );

  const insertPrefixAtLine = useCallback(
    (prefix: string) => {
      applyEditorTransform((text, start, end) => {
        const lineStart = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
        const nextText = `${text.slice(0, lineStart)}${prefix}${text.slice(lineStart)}`;
        return { nextText, nextStart: start + prefix.length, nextEnd: end + prefix.length };
      });
    },
    [applyEditorTransform],
  );

  const insertLink = useCallback(() => {
    applyEditorTransform((text, start, end) => {
      const selected = text.slice(start, end);
      const label = selected || t("notes.link.placeholderText");
      const url = "https://";
      const inserted = `[${label}](${url})`;
      const nextText = `${text.slice(0, start)}${inserted}${text.slice(end)}`;
      const urlStart = start + 1 + label.length + 2;
      const urlEnd = urlStart + url.length;
      const nextStart = selected ? urlStart : start + 1;
      const nextEnd = selected ? urlEnd : start + 1 + label.length;
      return { nextText, nextStart, nextEnd };
    });
  }, [applyEditorTransform, t]);

  useEffect(() => {
    setSaved(false);
    setActionError(null);
    setConflictSnapshot(null);
    setShareError(null);
    setShareUrl(null);
    setShareCopied(false);

    if (!selectedId) {
      setNote(null);
      setEditorBody("");
      setNoteError(null);
      setNoteLoading(false);
      return;
    }

    // Avoid editing the previous note while the new selection loads.
    setNote(null);
    setEditorBody("");

    const token = ++loadTokenRef.current;
    setNoteLoading(true);
    setNoteError(null);

    void (async () => {
      let seededFromCache = false;
      try {
        if (offlineEnabled && offlineUserKey) {
          try {
            const cached = await cacheGetNote(offlineUserKey, selectedId);
            if (cached && loadTokenRef.current === token) {
              seededFromCache = true;
              setNote(cached);
              setEditorBody(cached.body_md);
            }
          } catch {
            // Ignore cache errors; fall back to network.
          }
        }

        const loaded = await getNote(selectedId);
        if (loadTokenRef.current !== token) return;
        setNote(loaded);
        setEditorBody(loaded.body_md);
        if (offlineEnabled && offlineUserKey) {
          await cacheUpsertNote(offlineUserKey, loaded);
        }
      } catch (e) {
        if (loadTokenRef.current !== token) return;
        if (!seededFromCache) {
          setNote(null);
          setEditorBody("");
        }
        setNoteError(e instanceof Error ? e.message : t("notes.error.loadNote"));
      } finally {
        if (loadTokenRef.current === token) {
          setNoteLoading(false);
        }
      }
    })();
  }, [offlineEnabled, offlineUserKey, selectedId, t]);

  const isDirty = useMemo(() => {
    if (!note) return editorBody.trim().length > 0;
    return editorBody !== note.body_md;
  }, [editorBody, note]);

  function selectNote(nextId: string) {
    setSaved(false);
    setActionError(null);
    setConflictSnapshot(null);
    router.replace(buildNotesHref(searchParams, nextId), { scroll: false });
  }

  async function onCreate() {
    setCreating(true);
    setSaved(false);
    setActionError(null);
    setConflictSnapshot(null);

    try {
      const created = await createNote({ body_md: t("notes.newNoteTemplate"), client_updated_at_ms: Date.now() });
      await refreshNotesList();
      router.replace(buildNotesHref(searchParams, created.id), { scroll: false });
      setNote(created);
      setEditorBody(created.body_md);
      if (offlineEnabled && offlineUserKey) {
        await cacheUpsertNote(offlineUserKey, created);
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t("notes.error.createNote"));
    } finally {
      setCreating(false);
    }
  }

  async function onSave() {
    if (!note || saving) return;
    setSaving(true);
    setSaved(false);
    setActionError(null);
    setConflictSnapshot(null);

    try {
      const updated = await patchNote(note.id, { body_md: editorBody, client_updated_at_ms: Date.now() });
      setNote(updated);
      await refreshNotesList();
      setSaved(true);
      if (offlineEnabled && offlineUserKey) {
        await cacheUpsertNote(offlineUserKey, updated);
      }
    } catch (e) {
      if (e instanceof NotesApiErrorException && e.data.kind === "notes_conflict" && e.data.serverSnapshot) {
        setConflictSnapshot(e.data.serverSnapshot);
      } else {
        setActionError(e instanceof Error ? e.message : t("notes.error.saveNote"));
      }
    } finally {
      setSaving(false);
    }
  }

  const canEdit = Boolean(selectedId) && !noteLoading;

  async function onCreateShare() {
    if (!selectedId || shareCreating) return;
    setShareCreating(true);
    setShareError(null);
    setShareCopied(false);

    try {
      const res = await apiFetch(`/api/v1/notes/${encodeURIComponent(selectedId)}/shares`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const raw = await res.text().catch(() => "");
        const msg = extractApiErrorMessage(raw);
        if (res.status === 401 || res.status === 403) {
          throw new Error(msg ? `${t("notes.error.notAuthorizedPrefix")}${msg}` : t("notes.error.notAuthorizedGeneric"));
        }
        throw new Error(
          msg
            ? `${t("notes.error.createSharePrefix")}${msg}`
            : `${t("notes.error.createShareGeneric")} (${res.status})`
        );
      }

      const json = (await res.json()) as unknown;
      const parsed = parseShareCreateResponse(json);
      if (!parsed) throw new Error(t("notes.error.shareResponseInvalid"));
      setShareUrl(parsed.share_url);
    } catch (e) {
      setShareUrl(null);
      setShareError(e instanceof Error ? e.message : t("notes.error.createShareLink"));
    } finally {
      setShareCreating(false);
    }
  }

  async function onCopyShareUrl() {
    if (!shareUrl) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(shareUrl);
      } else {
        const el = document.createElement("textarea");
        el.value = shareUrl;
        el.setAttribute("readonly", "true");
        el.style.position = "fixed";
        el.style.left = "-9999px";
        el.style.top = "0";
        document.body.appendChild(el);
        el.select();
        document.execCommand("copy");
        document.body.removeChild(el);
      }
      setShareCopied(true);
    } catch {
      setShareCopied(false);
      setShareError(t("notes.share.copyFailed"));
    }
  }

  function onOpenShareUrl() {
    if (!shareUrl) return;
    window.open(shareUrl, "_blank", "noopener,noreferrer");
  }

  const selectedInList = useMemo(() => {
    return selectedId ? notes.find((n) => n.id === selectedId) ?? null : null;
  }, [notes, selectedId]);

  return (
    <Page titleKey="page.notes.title">
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(220px, 320px) 1fr",
          minHeight: 560,
          borderTop: "1px solid var(--color-border)",
          background: "color-mix(in srgb, var(--color-surface-2) 58%, transparent)",
        }}
      >
        <aside
          style={{
            borderRight: "1px solid var(--color-border)",
            background: "color-mix(in srgb, var(--color-surface) 86%, transparent)",
            display: "grid",
            gridTemplateRows: "auto 1fr",
            minHeight: 0,
          }}
          >
            <div
              style={{
                padding: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              borderBottom: "1px solid var(--color-border)",
              background: "color-mix(in srgb, var(--color-surface-2) 40%, transparent)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                {t("nav.notes")}
              </div>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                {notesLoading
                  ? t("common.loading")
                  : locale === "zh-CN"
                    ? `${notes.length}${t("notes.sidebar.itemsUnit")}`
                    : `${notes.length} ${t("notes.sidebar.itemsUnit")}`}
              </div>
            </div>
            <button
              data-testid="notes-new"
              type="button"
              onClick={onCreate}
              disabled={creating}
              style={{
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-1)",
                background: "var(--color-surface)",
                color: "var(--color-text)",
                padding: "8px 10px",
                fontFamily: "var(--font-body)",
                cursor: creating ? "not-allowed" : "pointer",
              }}
            >
              {creating ? t("common.creating") : t("common.new")}
            </button>
          </div>

          <div style={{ overflowY: "auto", minHeight: 0 }}>
            {notesError ? (
              <div style={{ padding: 12, color: "var(--color-text)", fontSize: 13 }}>
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", padding: 10, background: "var(--color-surface-2)" }}>
                  {notesError}
                </div>
              </div>
            ) : null}

            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {notes.map((n) => {
                const active = n.id === selectedId;
                return (
                  <li key={n.id}>
                    <button
                      type="button"
                      onClick={() => selectNote(n.id)}
                      style={{
                        width: "100%",
                        textAlign: "left",
                        padding: "10px 12px",
                        border: "none",
                        borderBottom: "1px solid var(--color-border)",
                        background: active ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "transparent",
                        color: "var(--color-text)",
                        cursor: "pointer",
                        fontFamily: "var(--font-body)",
                      }}
                    >
                      <div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.25, marginBottom: 4 }}>
                        {noteTitle(n, t("notes.untitled"))}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.4 }}>
                        {noteSnippet(n) || t("common.empty")}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>

        <section style={{ display: "grid", gridTemplateRows: "auto 1fr auto", minWidth: 0, minHeight: 0 }}>
          <div
            style={{
              padding: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              borderBottom: "1px solid var(--color-border)",
              background: "color-mix(in srgb, var(--color-surface) 86%, transparent)",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                {t("notes.editor.title")}
              </div>
              <div style={{ fontSize: 13, color: "var(--color-text)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {noteLoading
                  ? t("common.loading")
                  : selectedInList
                    ? noteTitle(selectedInList, t("notes.untitled"))
                    : selectedId
                      ? selectedId
                      : t("notes.editor.noSelection")}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <button
                  type="button"
                  onClick={() => setEditorMode("markdown")}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: editorMode === "markdown" ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "var(--color-surface)",
                    color: "var(--color-text)",
                    padding: "6px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: "pointer",
                  }}
                >
                  {t("notes.editor.mode.markdown")}
                </button>
                <button
                  type="button"
                  onClick={() => setEditorMode("rich")}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: editorMode === "rich" ? "color-mix(in srgb, var(--color-accent) 14%, var(--color-surface))" : "var(--color-surface)",
                    color: "var(--color-text)",
                    padding: "6px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: "pointer",
                  }}
                >
                  {t("notes.editor.mode.rich")}
                </button>
              </div>

              {saved ? <span style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{t("common.saved")}</span> : null}
              <button
                data-testid="notes-save"
                type="button"
                onClick={onSave}
                disabled={!note || saving || !isDirty}
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-1)",
                  background: note && isDirty ? "var(--color-accent)" : "var(--color-surface)",
                  color: note && isDirty ? "var(--color-accent-contrast)" : "var(--color-text-muted)",
                  padding: "8px 12px",
                  fontFamily: "var(--font-body)",
                  cursor: !note || saving || !isDirty ? "not-allowed" : "pointer",
                }}
              >
                {saving ? t("common.saving") : t("common.save")}
              </button>
            </div>
          </div>

          <div style={{ padding: 12, minHeight: 0, display: "grid", gridTemplateRows: "auto 1fr", gap: 10 }}>
            <div style={{ display: "grid", gap: 10 }}>
              {editorMode === "rich" ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    padding: 10,
                    background: "color-mix(in srgb, var(--color-surface-2) 52%, transparent)",
                  }}
                >
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
                    <button type="button" disabled={!canEdit} onClick={() => insertPrefixAtLine("# ")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      H1
                    </button>
                    <button type="button" disabled={!canEdit} onClick={() => insertWrap("**", "**", "加粗文字")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.bold")}
                    </button>
                    <button type="button" disabled={!canEdit} onClick={() => insertWrap("*", "*", "斜体文字")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.italic")}
                    </button>
                    <button type="button" disabled={!canEdit} onClick={insertLink} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.link")}
                    </button>
                    <button type="button" disabled={!canEdit} onClick={() => insertPrefixAtLine("- ")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.list")}
                    </button>
                    <button type="button" disabled={!canEdit} onClick={() => insertWrap("`", "`", "代码")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.code")}
                    </button>
                    <button type="button" disabled={!canEdit} onClick={() => insertWrap("```\n", "\n```", "代码\n")} style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", background: "var(--color-surface)", color: "var(--color-text)", padding: "6px 10px", fontFamily: "var(--font-body)", cursor: canEdit ? "pointer" : "not-allowed" }}>
                      {t("notes.rich.codeBlock")}
                    </button>
                  </div>

                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--color-text-muted)", cursor: "pointer", userSelect: "none" }}>
                    <input type="checkbox" checked={showPreview} onChange={(e) => setShowPreview(e.target.checked)} />
                    {t("notes.editor.previewToggle")}
                  </label>
                </div>
              ) : null}

              {selectedId ? (
                <div
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    padding: 10,
                    background: "color-mix(in srgb, var(--color-surface-2) 52%, transparent)",
                    display: "grid",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                        {t("notes.share.title")}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--color-text)", marginTop: 4 }}>
                        {t("notes.share.subtitle")}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      <button
                        data-testid="create-share"
                        type="button"
                        onClick={onCreateShare}
                        disabled={!selectedId || shareCreating}
                        style={{
                          border: "1px solid var(--color-border)",
                          borderRadius: "var(--radius-1)",
                          background: "var(--color-surface)",
                          color: "var(--color-text)",
                          padding: "8px 10px",
                          fontFamily: "var(--font-body)",
                          cursor: !selectedId || shareCreating ? "not-allowed" : "pointer",
                        }}
                      >
                        {shareCreating
                          ? t("common.creating")
                          : shareUrl
                            ? t("notes.share.recreate")
                            : t("notes.share.create")}
                      </button>
                      {shareUrl ? (
                        <button
                          type="button"
                          onClick={onOpenShareUrl}
                          style={{
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius-1)",
                            background: "var(--color-surface)",
                            color: "var(--color-text)",
                            padding: "8px 10px",
                            fontFamily: "var(--font-body)",
                            cursor: "pointer",
                          }}
                        >
                          {t("common.open")}
                        </button>
                      ) : null}
                      {shareUrl ? (
                        <button
                          type="button"
                          onClick={onCopyShareUrl}
                          style={{
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius-1)",
                            background: "var(--color-surface)",
                            color: "var(--color-text)",
                            padding: "8px 10px",
                            fontFamily: "var(--font-body)",
                            cursor: "pointer",
                          }}
                        >
                          {shareCopied ? t("common.copied") : t("notes.share.copy")}
                        </button>
                      ) : null}
                    </div>
                  </div>

                  {shareError ? (
                    <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", padding: 10, background: "var(--color-surface)", fontSize: 13 }}>
                      {shareError}
                    </div>
                  ) : null}

                  {shareUrl ? (
                    <input
                      data-testid="share-url"
                      type="text"
                      readOnly
                      value={shareUrl}
                      onFocus={(e) => e.currentTarget.select()}
                      style={{
                        width: "100%",
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-1)",
                        background: "var(--color-surface)",
                        color: "var(--color-text)",
                        padding: "10px 12px",
                        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                        fontSize: 12,
                      }}
                    />
                  ) : null}
                </div>
              ) : null}

              {conflictSnapshot ? (
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", padding: 10, background: "color-mix(in srgb, var(--color-accent-gold) 14%, var(--color-surface-2))" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                        {t("notes.conflict.title")}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--color-text)", marginTop: 4 }}>{t("notes.conflict.subtitle")}</div>
                    </div>
                    <button
                      data-testid="notes-use-server-version"
                      type="button"
                      onClick={() => {
                        setNote(conflictSnapshot);
                        setEditorBody(conflictSnapshot.body_md);
                        setConflictSnapshot(null);
                        setSaved(false);
                        setActionError(null);
                      }}
                      style={{
                        border: "1px solid var(--color-border)",
                        borderRadius: "var(--radius-1)",
                        background: "var(--color-surface)",
                        color: "var(--color-text)",
                        padding: "8px 10px",
                        fontFamily: "var(--font-body)",
                        cursor: "pointer",
                      }}
                    >
                      {t("notes.conflict.useServer")}
                    </button>
                  </div>
                </div>
              ) : null}

              {noteError ? (
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", padding: 10, background: "var(--color-surface-2)", fontSize: 13 }}>
                  {noteError}
                </div>
              ) : null}
              {actionError ? (
                <div style={{ border: "1px solid var(--color-border)", borderRadius: "var(--radius-1)", padding: 10, background: "var(--color-surface-2)", fontSize: 13 }}>
                  {actionError}
                </div>
              ) : null}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: editorMode === "rich" && showPreview ? "1fr 1fr" : "1fr",
                gap: 12,
                minHeight: 0,
              }}
            >
              <textarea
                ref={textareaRef}
                value={editorBody}
                onChange={(e) => {
                  setEditorBody(e.target.value);
                  setSaved(false);
                  setConflictSnapshot(null);
                }}
                placeholder={selectedId ? "" : t("notes.textarea.placeholderNoSelection")}
                disabled={!selectedId || noteLoading}
                style={{
                  width: "100%",
                  height: "100%",
                  minHeight: 360,
                  resize: "none",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-1)",
                  background: "var(--color-surface)",
                  color: "var(--color-text)",
                  padding: 12,
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                  fontSize: 13,
                  lineHeight: 1.6,
                }}
              />

              {editorMode === "rich" && showPreview ? (
                <div
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "color-mix(in srgb, var(--color-surface-2) 46%, transparent)",
                    padding: 12,
                    overflow: "auto",
                  }}
                >
                  <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)", marginBottom: 10 }}>{t("notes.rich.previewPlainText")}</div>
                  <pre
                    style={{
                      margin: 0,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                      fontSize: 13,
                      lineHeight: 1.6,
                      color: "var(--color-text)",
                    }}
                  >
                    {editorBody}
                  </pre>
                </div>
              ) : null}
            </div>
          </div>

          <div style={{ padding: 12, borderTop: "1px solid var(--color-border)", color: "var(--color-text-muted)", fontSize: 12 }}>
            {note ? `id=${note.id}` : selectedId ? `id=${selectedId}` : t("notes.footer.tip")}
          </div>
        </section>
      </div>
    </Page>
  );
}

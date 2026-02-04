"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { listNotes } from "@/features/notes/notesApi";
import type { Note, NoteList } from "@/features/notes/types";
import { getTodoItems } from "@/features/todo/todoApi";
import type { TodoItem, TodoItemsResponse } from "@/features/todo/types";
import { Page } from "@/features/ui/Page";

function normalizeQuery(v: string): string {
  return v.trim().replace(/\s+/g, " ");
}

function normalizeTag(v: string): string {
  // Keep it simple: one tag, trimmed; avoid whitespace-only tags.
  return v.trim();
}

function toErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

function includesCaseInsensitive(haystack: string, needle: string): boolean {
  if (!needle) return true;
  return haystack.toLocaleLowerCase().includes(needle.toLocaleLowerCase());
}

function notePreview(bodyMd: string, maxLen = 180): string {
  const s = bodyMd.trim().replace(/\s+/g, " ");
  if (!s) return "";
  return s.length <= maxLen ? s : `${s.slice(0, maxLen)}...`;
}

function ChipButton({
  label,
  title,
  onClick,
}: {
  label: string;
  title?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid var(--color-border)",
        background: "var(--color-surface)",
        color: "var(--color-text)",
        cursor: "pointer",
        lineHeight: 1,
      }}
    >
      <span style={{ fontSize: 13 }}>{label}</span>
    </button>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>{title}</div>
      {subtitle ? <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{subtitle}</div> : null}
    </div>
  );
}

export default function SearchPage() {
  const [queryDraft, setQueryDraft] = useState<string>("");
  const [tagDraft, setTagDraft] = useState<string>("");

  const [query, setQuery] = useState<string>("");
  const [tag, setTag] = useState<string>("");

  const normalizedTag = useMemo(() => normalizeTag(tag), [tag]);
  const normalizedQuery = useMemo(() => normalizeQuery(query), [query]);
  const effectiveQuery = normalizedTag ? "" : normalizedQuery;

  const [notes, setNotes] = useState<Note[]>([]);
  const [notesTotal, setNotesTotal] = useState<number>(0);
  const [notesLoading, setNotesLoading] = useState<boolean>(false);
  const [notesError, setNotesError] = useState<string | null>(null);

  const [todos, setTodos] = useState<TodoItem[]>([]);
  const [todosLoading, setTodosLoading] = useState<boolean>(false);
  const [todosError, setTodosError] = useState<string | null>(null);

  const runIdRef = useRef<number>(0);
  const skeletonKeys = useMemo(() => ["a", "b", "c"], []);

  // Hydrate initial state from URL (?q= / ?tag=) on client only.
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const q0 = sp.get("q") ?? "";
    const t0 = sp.get("tag") ?? "";
    setQueryDraft(q0);
    setQuery(q0);
    setTagDraft(t0);
    setTag(t0);
  }, []);

  // Debounce query input so typing doesn't spam requests.
  useEffect(() => {
    const h = window.setTimeout(() => {
      setQuery(queryDraft);
    }, 250);
    return () => window.clearTimeout(h);
  }, [queryDraft]);

  useEffect(() => {
    const runId = ++runIdRef.current;

    const activeTag = normalizedTag;
    const activeQuery = effectiveQuery;

    if (!activeTag && !activeQuery) {
      setNotes([]);
      setNotesTotal(0);
      setNotesLoading(false);
      setNotesError(null);

      setTodos([]);
      setTodosLoading(false);
      setTodosError(null);
      return;
    }

    setNotesLoading(true);
    setNotesError(null);
    setTodosLoading(true);
    setTodosError(null);

    const notesPromise = (async () => {
      try {
        const res: NoteList = await listNotes(
          activeTag
            ? { tag: activeTag, limit: 50, offset: 0 }
            : { q: activeQuery, limit: 20, offset: 0 }
        );
        if (runIdRef.current !== runId) return;
        setNotes(res.items);
        setNotesTotal(res.total);
      } catch (err) {
        if (runIdRef.current !== runId) return;
        setNotes([]);
        setNotesTotal(0);
        setNotesError(toErrorMessage(err));
      } finally {
        if (runIdRef.current === runId) {
          setNotesLoading(false);
        }
      }
    })();

    const todosPromise = (async () => {
      try {
        const res: TodoItemsResponse = await getTodoItems(
          activeTag
            ? { tag: activeTag, include_deleted: false, limit: 200 }
            : { include_deleted: false, limit: 200 }
        );
        if (runIdRef.current !== runId) return;
        const items = res.data.items;
        if (activeTag) {
          setTodos(items);
          return;
        }

        const qLower = activeQuery.toLocaleLowerCase();
        setTodos(items.filter((it) => includesCaseInsensitive(it.title, qLower) || includesCaseInsensitive(it.note, qLower)));
      } catch (err) {
        if (runIdRef.current !== runId) return;
        setTodos([]);
        setTodosError(toErrorMessage(err));
      } finally {
        if (runIdRef.current === runId) {
          setTodosLoading(false);
        }
      }
    })();

    void Promise.all([notesPromise, todosPromise]);
  }, [effectiveQuery, normalizedTag]);

  const onApplyTag = () => {
    setTag(tagDraft);
  };

  const onClearTag = () => {
    setTag("");
    setTagDraft("");
  };

  const onPickTag = (t: string) => {
    setTagDraft(t);
    setTag(t);
  };

  const activeLabel = normalizedTag
    ? `Tag: ${normalizedTag}`
    : normalizedQuery
      ? `Query: ${normalizedQuery}`
      : "";

  return (
    <Page titleKey="page.search.title">
      <div style={{ display: "grid", gap: 16, padding: "16px 16px 20px" }}>
        <div
          style={{
            display: "grid",
            gap: 12,
            padding: 14,
            border: "1px solid var(--color-border)",
            borderRadius: 14,
            background: "var(--color-surface)",
          }}
        >
          <div style={{ display: "grid", gap: 10 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>Search</div>
              <input
                value={queryDraft}
                onChange={(e) => setQueryDraft(e.target.value)}
                placeholder={normalizedTag ? "(Tag filter active)" : "Search notes + todos"}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  borderRadius: 12,
                  border: "1px solid var(--color-border)",
                  background: "transparent",
                  color: "var(--color-text)",
                  outline: "none",
                }}
              />
            </label>

            <div style={{ display: "grid", gap: 6 }}>
              <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>Tag filter</div>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                {normalizedTag ? (
                  <ChipButton label={`#${normalizedTag}  x`} title="Clear tag filter" onClick={onClearTag} />
                ) : null}
                <input
                  value={tagDraft}
                  onChange={(e) => setTagDraft(e.target.value)}
                  placeholder="Type tag (optional)"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      onApplyTag();
                    }
                  }}
                  style={{
                    flex: "1 1 220px",
                    minWidth: 160,
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: "1px solid var(--color-border)",
                    background: "transparent",
                    color: "var(--color-text)",
                    outline: "none",
                  }}
                />
                <button
                  type="button"
                  onClick={onApplyTag}
                  style={{
                    padding: "10px 12px",
                    borderRadius: 12,
                    border: "1px solid var(--color-border)",
                    background: "transparent",
                    color: "var(--color-text)",
                    cursor: "pointer",
                  }}
                >
                  Apply
                </button>
              </div>
              {normalizedTag ? (
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  Tag mode uses tag endpoints for both notes and todos.
                </div>
              ) : null}
            </div>
          </div>

          {activeLabel ? (
            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>Active: {activeLabel}</div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              Tip: paste a URL like <code>?q=meeting</code> or <code>?tag=work</code>.
            </div>
          )}
        </div>

        <div style={{ display: "grid", gap: 14 }}>
          <div
            style={{
              padding: 14,
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
            }}
          >
            <SectionTitle
              title="Notes"
              subtitle={notesLoading ? "Loading..." : notesError ? "Error" : `${notes.length}${notesTotal ? ` / ${notesTotal}` : ""}`}
            />
            {notesError ? (
              <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 13 }}>{notesError}</div>
            ) : null}
            {!notesLoading && !notesError && notes.length === 0 ? (
              <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 13 }}>No matching notes.</div>
            ) : null}
            <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
              {notesLoading
                ? skeletonKeys.map((k) => (
                    <div
                      key={`notes-skeleton-${k}`}
                      className="skeleton"
                      style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }}
                    />
                  ))
                : notes.map((n) => (
                    <div
                      key={n.id}
                      style={{
                        border: "1px solid var(--color-border)",
                        borderRadius: 12,
                        padding: 12,
                        display: "grid",
                        gap: 8,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                        <Link
                          href={`/notes?id=${encodeURIComponent(n.id)}`}
                          style={{
                            color: "var(--color-accent)",
                            fontWeight: 700,
                            textDecoration: "none",
                            fontSize: 14,
                            lineHeight: 1.2,
                          }}
                        >
                          {n.title || "(Untitled)"}
                        </Link>
                        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{n.updated_at.slice(0, 10)}</div>
                      </div>
                      {n.body_md ? (
                        <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{notePreview(n.body_md)}</div>
                      ) : null}
                      {n.tags.length ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {n.tags.slice(0, 10).map((t) => (
                            <ChipButton key={t} label={`#${t}`} title={`Filter by tag: ${t}`} onClick={() => onPickTag(t)} />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
            </div>
          </div>

          <div
            style={{
              padding: 14,
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
            }}
          >
            <SectionTitle title="Todos" subtitle={todosLoading ? "Loading..." : todosError ? "Error" : String(todos.length)} />
            {todosError ? (
              <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 13 }}>{todosError}</div>
            ) : null}
            {!todosLoading && !todosError && todos.length === 0 ? (
              <div style={{ marginTop: 10, color: "var(--color-text-muted)", fontSize: 13 }}>No matching todos.</div>
            ) : null}
            <div style={{ marginTop: 10, display: "grid", gap: 10 }}>
              {todosLoading
                ? skeletonKeys.map((k) => (
                    <div
                      key={`todos-skeleton-${k}`}
                      className="skeleton"
                      style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }}
                    />
                  ))
                : todos.map((it) => (
                    <div
                      key={it.id}
                      style={{
                        border: "1px solid var(--color-border)",
                        borderRadius: 12,
                        padding: 12,
                        display: "grid",
                        gap: 8,
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                        <div style={{ fontSize: 14, fontWeight: 700, color: "var(--color-text)" }}>{it.title}</div>
                        <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{it.updated_at.slice(0, 10)}</div>
                      </div>
                      {it.note ? (
                        <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{notePreview(it.note, 160)}</div>
                      ) : null}
                      {it.tags.length ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                          {it.tags.slice(0, 10).map((t) => (
                            <ChipButton key={`${it.id}:${t}`} label={`#${t}`} title={`Filter by tag: ${t}`} onClick={() => onPickTag(t)} />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
            </div>
          </div>
        </div>
      </div>
    </Page>
  );
}

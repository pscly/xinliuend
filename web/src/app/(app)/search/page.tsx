"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { listNotes } from "@/features/notes/notesApi";
import type { Note, NoteList } from "@/features/notes/types";
import { getTodoItems } from "@/features/todo/todoApi";
import type { TodoItem, TodoItemsResponse } from "@/features/todo/types";
import { Page } from "@/features/ui/Page";
import { InkButton } from "@/features/ui/InkButton";
import { InkTextField } from "@/features/ui/InkField";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./SearchPage.module.css";

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
    <InkButton type="button" size="sm" pill title={title} onClick={onClick}>
      {label}
    </InkButton>
  );
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className={styles.sectionTitle}>
      <div className={styles.sectionTitleMain}>{title}</div>
      {subtitle ? <div className={styles.sectionTitleSub}>{subtitle}</div> : null}
    </div>
  );
}

export default function SearchPage() {
  const { locale, t } = useI18n();
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
        const items = res.items;
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
    ? `${t("search.active.tagPrefix")}${normalizedTag}`
    : normalizedQuery
      ? `${t("search.active.queryPrefix")}${normalizedQuery}`
      : "";

  return (
    <Page titleKey="page.search.title">
      <div className={styles.content}>
        <div className={styles.filters}>
          <div className={styles.filtersGrid}>
            <InkTextField
              label={t("search.query.label")}
              data-testid="search-query-input"
              value={queryDraft}
              onChange={(e) => setQueryDraft(e.target.value)}
              placeholder={normalizedTag ? t("search.query.placeholderTagActive") : t("search.query.placeholder")}
            />

            <div className={styles.filtersGrid}>
              <div className={styles.fieldLabel}>{t("search.tag.label")}</div>
              <div className={styles.tagRow}>
                {normalizedTag ? <ChipButton label={`#${normalizedTag}  x`} title={t("search.tag.clear")} onClick={onClearTag} /> : null}

                <input
                  data-testid="search-tag-input"
                  value={tagDraft}
                  onChange={(e) => setTagDraft(e.target.value)}
                  placeholder={t("search.tag.placeholder")}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      onApplyTag();
                    }
                  }}
                  className={`${styles.input} ${styles.tagInputGrow}`}
                />

                <InkButton data-testid="search-apply-tag" type="button" onClick={onApplyTag} variant="ghost">
                  {t("common.apply")}
                </InkButton>
              </div>

              {normalizedTag ? <div className={styles.hint}>{t("search.tag.modeHint")}</div> : null}
            </div>
          </div>

          {activeLabel ? (
            <div className={styles.hint}>
              {t("search.active.prefix")}
              {activeLabel}
            </div>
          ) : (
            <div className={styles.hint}>{t("search.tip")}</div>
          )}
        </div>

        <div className={styles.sections}>
          <div className={styles.panel}>
            <SectionTitle
              title={t("search.section.notes")}
              subtitle={
                notesLoading
                  ? t("common.loadingDots")
                  : notesError
                    ? t("search.subtitle.error")
                    : locale === "zh-CN"
                      ? `${notes.length}${notesTotal ? ` / ${notesTotal}` : ""} 条`
                      : `${notes.length}${notesTotal ? ` / ${notesTotal}` : ""}`
              }
            />
            {notesError ? <div className={styles.sectionMsg}>{notesError}</div> : null}
            {!notesLoading && !notesError && notes.length === 0 ? <div className={styles.sectionMsg}>{t("search.empty.notes")}</div> : null}
            <div className={styles.results}>
              {notesLoading
                ? skeletonKeys.map((k) => (
                    <div
                      key={`notes-skeleton-${k}`}
                      className="skeleton"
                      style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }}
                    />
                  ))
                : notes.map((n) => (
                    <div key={n.id} className={styles.resultCard}>
                      <div className={styles.cardTop}>
                        <Link href={`/notes?id=${encodeURIComponent(n.id)}`} className={styles.noteLink}>
                          {n.title || t("common.untitled")}
                        </Link>
                        <div className={styles.date}>{n.updated_at.slice(0, 10)}</div>
                      </div>
                      {n.body_md ? <div className={styles.preview}>{notePreview(n.body_md)}</div> : null}
                      {n.tags.length ? (
                        <div className={styles.chips}>
                          {n.tags.slice(0, 10).map((tag) => (
                            <ChipButton key={tag} label={`#${tag}`} title={`${t("search.tag.filterByTagTitlePrefix")}${tag}`} onClick={() => onPickTag(tag)} />
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ))}
            </div>
          </div>

          <div className={styles.panel}>
            <SectionTitle
              title={t("search.section.todos")}
              subtitle={
                todosLoading
                  ? t("common.loadingDots")
                  : todosError
                    ? t("search.subtitle.error")
                    : locale === "zh-CN"
                      ? `${todos.length} 项`
                      : String(todos.length)
              }
            />
            {todosError ? <div className={styles.sectionMsg}>{todosError}</div> : null}
            {!todosLoading && !todosError && todos.length === 0 ? <div className={styles.sectionMsg}>{t("search.empty.todos")}</div> : null}
            <div className={styles.results}>
              {todosLoading
                ? skeletonKeys.map((k) => (
                    <div
                      key={`todos-skeleton-${k}`}
                      className="skeleton"
                      style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }}
                    />
                  ))
                : todos.map((it) => (
                    <div key={it.id} className={styles.resultCard}>
                      <div className={styles.cardTop}>
                        <div className={styles.todoTitle}>{it.title}</div>
                        <div className={styles.date}>{it.updated_at.slice(0, 10)}</div>
                      </div>
                      {it.note ? <div className={styles.preview}>{notePreview(it.note, 160)}</div> : null}
                      {it.tags.length ? (
                        <div className={styles.chips}>
                          {it.tags.slice(0, 10).map((tag) => (
                            <ChipButton key={`${it.id}:${tag}`} label={`#${tag}`} title={`${t("search.tag.filterByTagTitlePrefix")}${tag}`} onClick={() => onPickTag(tag)} />
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

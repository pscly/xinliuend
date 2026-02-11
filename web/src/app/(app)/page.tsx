"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listMemosNotes } from "@/features/memos/memosNotesApi";
import { listNotes } from "@/features/notes/notesApi";
import type { Note } from "@/features/notes/types";

import { expandRruleToLocalIds } from "@/features/todo/recurrence";
import { getTodoItems, getTodoOccurrences } from "@/features/todo/todoApi";
import type { LocalDateTimeString, TodoItem, TodoOccurrence } from "@/features/todo/types";

import { Page } from "@/features/ui/Page";
import { useI18n } from "@/lib/i18n/useI18n";
import { useMemosFeedEnabled } from "@/lib/memos/useMemosFeedEnabled";
import { InkButton } from "@/features/ui/InkButton";

import styles from "./HomePage.module.css";

const SHANGHAI_OFFSET_MS = 8 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function formatUtcMsToShanghaiLocal(utcMs: number): LocalDateTimeString {
  const localMs = utcMs + SHANGHAI_OFFSET_MS;
  const d = new Date(localMs);
  const yyyy = d.getUTCFullYear();
  const mm = pad2(d.getUTCMonth() + 1);
  const dd = pad2(d.getUTCDate());
  const hh = pad2(d.getUTCHours());
  const mi = pad2(d.getUTCMinutes());
  const ss = pad2(d.getUTCSeconds());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}:${ss}`;
}

function getShanghaiTodayStartUtcMs(nowUtcMs: number): number {
  // Convert "now" into Shanghai wall-clock Y/M/D, then re-interpret that
  // wall-clock midnight as UTC milliseconds (fixed UTC+8 per backend contract).
  const localMs = nowUtcMs + SHANGHAI_OFFSET_MS;
  const d = new Date(localMs);
  const yyyy = d.getUTCFullYear();
  const month = d.getUTCMonth() + 1;
  const day = d.getUTCDate();
  return Date.UTC(yyyy, month - 1, day, 0, 0, 0) - SHANGHAI_OFFSET_MS;
}

function buildShanghaiTodayRange(nowUtcMs: number): { dateLocal: string; from: LocalDateTimeString; to: LocalDateTimeString } {
  const startUtcMs = getShanghaiTodayStartUtcMs(nowUtcMs);
  const from = formatUtcMsToShanghaiLocal(startUtcMs);
  const to = formatUtcMsToShanghaiLocal(startUtcMs + DAY_MS - 1000);
  return { dateLocal: from.slice(0, 10), from, to };
}

function normalizeErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return "未知错误";
  }
}

type RecurringReadyItem = TodoItem & {
  rrule: string;
  dtstart_local: LocalDateTimeString;
};

function isRecurringReadyItem(it: TodoItem): it is RecurringReadyItem {
  if (!it.is_recurring) return false;
  if (!it.rrule || !it.dtstart_local) return false;
  if (it.deleted_at) return false;
  return true;
}

function isOccurrenceDone(occ: TodoOccurrence | undefined): boolean {
  if (!occ) return false;
  if (occ.completed_at_local) return true;
  return occ.status_override === "done";
}

type TodayOccurrenceRow = {
  key: string;
  itemId: string;
  recurrenceIdLocal: LocalDateTimeString;
  title: string;
  timeLocal: string;
  done: boolean;
};

type HomeRecentNoteItem = {
  id: string;
  title: string;
  body_md: string;
  updated_at: string;
  source: "local" | "memos";
  linkedLocalNoteId: string | null;
};

function normalizeUpdatedAt(value: string | null | undefined): string {
  if (!value) return "1970-01-01T00:00:00+00:00";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "1970-01-01T00:00:00+00:00";
  return d.toISOString();
}

function mergeHomeRecentNotes(localItems: Note[], memosItems: Awaited<ReturnType<typeof listMemosNotes>>["items"]): HomeRecentNoteItem[] {
  const locals: HomeRecentNoteItem[] = localItems.map((n) => ({
    id: n.id,
    title: n.title,
    body_md: n.body_md,
    updated_at: normalizeUpdatedAt(n.updated_at),
    source: "local",
    linkedLocalNoteId: n.id,
  }));

  const memos: HomeRecentNoteItem[] = memosItems.map((m) => ({
    id: `memos:${m.remote_id}`,
    title: m.title,
    body_md: m.body_md,
    updated_at: normalizeUpdatedAt(m.updated_at),
    source: "memos",
    linkedLocalNoteId: m.linked_local_note_id,
  }));

  return [...locals, ...memos]
    .sort((a, b) => {
      const diff = Date.parse(b.updated_at) - Date.parse(a.updated_at);
      if (diff !== 0) return diff;
      return a.id.localeCompare(b.id);
    })
    .slice(0, 5);
}

export default function HomePage() {
  const { locale, t } = useI18n();
  const { memosFeedEnabled, updateMemosFeedEnabled } = useMemosFeedEnabled();
  const [initialNowMs] = useState(() => Date.now());
  const shanghaiToday = useMemo(() => buildShanghaiTodayRange(initialNowMs), [initialNowMs]);

  const [todayRows, setTodayRows] = useState<TodayOccurrenceRow[]>([]);
  const [todayTotal, setTodayTotal] = useState<number>(0);
  const [todayLoading, setTodayLoading] = useState<boolean>(true);
  const [todayError, setTodayError] = useState<string | null>(null);
  const [todayWarning, setTodayWarning] = useState<string | null>(null);

  const [notes, setNotes] = useState<HomeRecentNoteItem[]>([]);
  const [notesLoading, setNotesLoading] = useState<boolean>(true);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [memosNotesError, setMemosNotesError] = useState<string | null>(null);

  const todayRunIdRef = useRef<number>(0);
  const notesRunIdRef = useRef<number>(0);

  const loadToday = useCallback(async () => {
    const runId = ++todayRunIdRef.current;
    setTodayLoading(true);
    setTodayError(null);
    setTodayWarning(null);

    try {
      const itemsResp = await getTodoItems({ include_deleted: false, limit: 200 });
      if (todayRunIdRef.current !== runId) return;

      const recurring = itemsResp.items.filter(isRecurringReadyItem);

      const seeds: Array<{ item: RecurringReadyItem; recurrenceIds: LocalDateTimeString[] }> = [];
      for (const it of recurring) {
        try {
          const ids = expandRruleToLocalIds(
            { rrule: it.rrule, dtstart_local: it.dtstart_local },
            { from: shanghaiToday.from, to: shanghaiToday.to }
          );
          if (ids.length) seeds.push({ item: it, recurrenceIds: ids });
        } catch {
          // Best-effort: ignore invalid recurrence config rather than failing the whole dashboard.
        }
      }

      const overrideResults = await Promise.allSettled(
        seeds.map((s) => getTodoOccurrences({ item_id: s.item.id, from: shanghaiToday.from, to: shanghaiToday.to }))
      );
      if (todayRunIdRef.current !== runId) return;

      const overrideByKey = new Map<string, TodoOccurrence>();
      let overrideFailures = 0;
      for (const r of overrideResults) {
        if (r.status !== "fulfilled") {
          overrideFailures += 1;
          continue;
        }
        for (const occ of r.value.items) {
          overrideByKey.set(`${occ.item_id}::${occ.recurrence_id_local}`, occ);
        }
      }

      const allRows: TodayOccurrenceRow[] = [];
      for (const s of seeds) {
        for (const rid of s.recurrenceIds) {
          const key = `${s.item.id}::${rid}`;
          const override = overrideByKey.get(key);
          const title = override?.title_override ?? s.item.title;
          allRows.push({
            key,
            itemId: s.item.id,
            recurrenceIdLocal: rid,
            title,
            timeLocal: rid.slice(11, 16),
            done: isOccurrenceDone(override),
          });
        }
      }

      allRows.sort((a, b) => {
        const t = a.recurrenceIdLocal.localeCompare(b.recurrenceIdLocal);
        if (t !== 0) return t;
        return a.title.localeCompare(b.title);
      });

      setTodayTotal(allRows.length);
      setTodayRows(allRows.slice(0, 10));

      if (overrideFailures > 0) {
        setTodayWarning(
          locale === "zh-CN"
            ? `部分覆盖项加载失败（${overrideFailures}/${overrideResults.length}），已尽量展示可用结果。`
            : `Some overrides failed to load (${overrideFailures}/${overrideResults.length}). Showing best-effort results.`
        );
      }
    } catch (err: unknown) {
      if (todayRunIdRef.current !== runId) return;
      setTodayRows([]);
      setTodayTotal(0);
      setTodayError(normalizeErrorMessage(err));
    } finally {
      if (todayRunIdRef.current === runId) {
        setTodayLoading(false);
      }
    }
  }, [locale, shanghaiToday.from, shanghaiToday.to]);

  const loadNotes = useCallback(async () => {
    const runId = ++notesRunIdRef.current;
    setNotesLoading(true);
    setNotesError(null);
    setMemosNotesError(null);

    try {
      const localPromise = listNotes({ limit: 20, offset: 0 });
      const memosPromise = memosFeedEnabled ? listMemosNotes({ limit: 20, offset: 0 }) : null;

      const localRes = await localPromise;
      let memosItems: Awaited<ReturnType<typeof listMemosNotes>>["items"] = [];
      if (memosPromise) {
        try {
          const memosRes = await memosPromise;
          memosItems = memosRes.items;
        } catch (memosErr: unknown) {
          if (notesRunIdRef.current !== runId) return;
          setMemosNotesError(normalizeErrorMessage(memosErr));
        }
      }

      if (notesRunIdRef.current !== runId) return;

      setNotes(mergeHomeRecentNotes(localRes.items, memosItems));
    } catch (err: unknown) {
      if (notesRunIdRef.current !== runId) return;
      setNotes([]);
      setNotesError(normalizeErrorMessage(err));
    } finally {
      if (notesRunIdRef.current === runId) {
        setNotesLoading(false);
      }
    }
  }, [memosFeedEnabled]);

  useEffect(() => {
    void loadToday();
  }, [loadToday]);

  useEffect(() => {
    void loadNotes();
  }, [loadNotes]);

  const quickLinks = useMemo(
    () =>
      [
        { href: "/notes", title: t("nav.notes"), subtitle: t("home.quickLinks.notes.subtitle") },
        { href: "/todos", title: t("nav.todos"), subtitle: t("home.quickLinks.todos.subtitle") },
        { href: "/calendar", title: t("nav.calendar"), subtitle: t("home.quickLinks.calendar.subtitle") },
        { href: "/search", title: t("nav.search"), subtitle: t("home.quickLinks.search.subtitle") },
        { href: "/settings", title: t("nav.settings"), subtitle: t("home.quickLinks.settings.subtitle") },
      ] as const,
    [t]
  );

  return (
    <Page titleKey="page.home.title" subtitleKey="page.home.subtitle">
      <div className={styles.content}>
        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div className={styles.panelTitle}>{t("home.quickLinks.title")}</div>
            <div className={styles.panelSubtitle}>{t("home.quickLinks.subtitle")}</div>
          </div>

          <div className={styles.quickLinksGrid}>
            {quickLinks.map((l) => (
              <Link key={l.href} href={l.href} className={styles.quickLink}>
                <div className={styles.quickLinkTop}>
                  <div className={styles.quickLinkTitle}>{l.title}</div>
                  <div className={styles.quickLinkAction}>{t("common.open")}</div>
                </div>
                <div className={styles.quickLinkHint}>{l.subtitle}</div>
              </Link>
            ))}
          </div>
        </section>

        <div className={styles.twoColumn}>
          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div style={{ display: "grid", gap: 2 }}>
                <div className={styles.panelTitle}>{t("home.today.title")}</div>
                <div className={styles.panelSubtitle}>{shanghaiToday.dateLocal}</div>
              </div>
              <InkButton
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  void loadToday();
                }}
                disabled={todayLoading}
              >
                {todayLoading ? t("common.loading") : t("common.refresh")}
              </InkButton>
            </div>

            {todayError ? (
              <div role="alert" className={styles.panelSubtitle}>
                {t("home.today.failedPrefix")}
                {todayError}
              </div>
            ) : null}

            {todayWarning && !todayError ? <div className={styles.panelSubtitle}>{todayWarning}</div> : null}

            {!todayLoading && !todayError && todayRows.length === 0 ? (
              <div className={styles.panelSubtitle}>{t("home.today.noOccurrences")}</div>
            ) : null}

            <div className={styles.rows}>
              {todayLoading ? (
                <>
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                </>
              ) : (
                todayRows.map((row) => (
                  <div key={row.key} className={`${styles.row} ${row.done ? styles.rowDone : ""}`}>
                    <div className={styles.rowLeft}>
                      <div className={styles.rowTime}>{row.timeLocal}</div>
                      <div
                        title={row.title}
                        className={`${styles.rowTitle} ${row.done ? styles.rowTitleDone : ""}`}
                      >
                        {row.title}
                      </div>
                    </div>
                    {row.done ? <div className={styles.donePill}>{t("common.done")}</div> : null}
                  </div>
                ))
              )}
            </div>

            {!todayLoading && !todayError && todayTotal > 10 ? (
              <div className={styles.panelSubtitle}>
                {locale === "zh-CN" ? `仅展示前 10 条，共 ${todayTotal} 条。` : `Showing 10 / ${todayTotal} occurrences.`}
              </div>
            ) : null}
          </section>

          <section className={styles.panel}>
            <div className={styles.panelHeader}>
              <div className={styles.panelTitle}>{t("home.recentNotes.title")}</div>
              <div className={styles.panelHeaderRight}>
                <label className={styles.toggle}>
                  <input
                    data-testid="home-memos-feed-enabled"
                    type="checkbox"
                    checked={memosFeedEnabled}
                    onChange={(e) => updateMemosFeedEnabled(e.currentTarget.checked)}
                  />
                  <span>{t("home.recentNotes.toggleMemos")}</span>
                </label>
                <InkButton
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    void loadNotes();
                  }}
                  disabled={notesLoading}
                >
                  {notesLoading ? t("common.loading") : t("common.refresh")}
                </InkButton>
              </div>
            </div>

            {notesError ? (
              <div role="alert" className={styles.panelSubtitle}>
                {t("home.recentNotes.failedPrefix")}
                {notesError}
              </div>
            ) : null}

            {memosFeedEnabled && memosNotesError && !notesError ? (
              <div role="alert" className={styles.panelSubtitle}>
                {t("home.recentNotes.memosFailedPrefix")}
                {memosNotesError}
              </div>
            ) : null}

            {!notesLoading && !notesError && notes.length === 0 ? (
              <div className={styles.panelSubtitle}>{t("home.recentNotes.empty")}</div>
            ) : null}

            <div className={styles.rows}>
              {notesLoading ? (
                <>
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                  <div
                    className="skeleton"
                    style={{ height: 44, borderRadius: "var(--radius-1)", border: "1px solid var(--color-border)" }}
                  />
                </>
              ) : (
                notes.map((n) => {
                  const title = n.title || t("common.untitled");
                  const snippet = n.body_md.trim().replace(/\s+/g, " ");
                  const content = (
                    <>
                      <div className={styles.noteTop}>
                        <div title={title} className={styles.noteTitle}>
                          {title}
                        </div>
                        <div className={styles.noteMeta}>
                          <span
                            className={`${styles.sourceBadge} ${
                              n.source === "memos" ? styles.sourceBadgeMemos : ""
                            }`}
                          >
                            {n.source === "memos"
                              ? t("home.recentNotes.source.memos")
                              : t("home.recentNotes.source.local")}
                          </span>
                          <div className={styles.noteDate}>{n.updated_at.slice(0, 10)}</div>
                        </div>
                      </div>
                      {snippet ? (
                        <div className={styles.noteSnippet}>
                          {snippet.slice(0, 180)}
                          {snippet.length > 180 ? "..." : ""}
                        </div>
                      ) : null}
                    </>
                  );

                  if (n.linkedLocalNoteId) {
                    return (
                      <Link
                        key={n.id}
                        href={`/notes?id=${encodeURIComponent(n.linkedLocalNoteId)}`}
                        className={styles.noteLink}
                      >
                        {content}
                      </Link>
                    );
                  }

                  return (
                    <div key={n.id} className={styles.noteLink}>
                      {content}
                    </div>
                  );
                })
              )}
            </div>
          </section>
        </div>
      </div>
    </Page>
  );
}

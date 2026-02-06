"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listNotes } from "@/features/notes/notesApi";
import type { Note } from "@/features/notes/types";

import { expandRruleToLocalIds } from "@/features/todo/recurrence";
import { getTodoItems, getTodoOccurrences } from "@/features/todo/todoApi";
import type { LocalDateTimeString, TodoItem, TodoOccurrence } from "@/features/todo/types";

import { Page } from "@/features/ui/Page";
import { useI18n } from "@/lib/i18n/useI18n";

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

export default function HomePage() {
  const { locale, t } = useI18n();
  const [initialNowMs] = useState(() => Date.now());
  const shanghaiToday = useMemo(() => buildShanghaiTodayRange(initialNowMs), [initialNowMs]);

  const [todayRows, setTodayRows] = useState<TodayOccurrenceRow[]>([]);
  const [todayTotal, setTodayTotal] = useState<number>(0);
  const [todayLoading, setTodayLoading] = useState<boolean>(true);
  const [todayError, setTodayError] = useState<string | null>(null);
  const [todayWarning, setTodayWarning] = useState<string | null>(null);

  const [notes, setNotes] = useState<Note[]>([]);
  const [notesLoading, setNotesLoading] = useState<boolean>(true);
  const [notesError, setNotesError] = useState<string | null>(null);

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

    try {
      const res = await listNotes({ limit: 5, offset: 0 });
      if (notesRunIdRef.current !== runId) return;
      setNotes(res.items);
    } catch (err: unknown) {
      if (notesRunIdRef.current !== runId) return;
      setNotes([]);
      setNotesError(normalizeErrorMessage(err));
    } finally {
      if (notesRunIdRef.current === runId) {
        setNotesLoading(false);
      }
    }
  }, []);

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
      <div style={{ display: "grid", gap: 16, padding: "16px 16px 20px" }}>
        <section
          style={{
            padding: 14,
            border: "1px solid var(--color-border)",
            borderRadius: 14,
            background: "var(--color-surface)",
            display: "grid",
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>{t("home.quickLinks.title")}</div>
            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{t("home.quickLinks.subtitle")}</div>
          </div>
          <div
            style={{
              display: "grid",
              gap: 10,
              gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
            }}
          >
            {quickLinks.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                style={{
                  textDecoration: "none",
                  color: "var(--color-text)",
                  borderRadius: 14,
                  border: "1px solid var(--color-border)",
                  background: "color-mix(in srgb, var(--color-surface-2) 58%, transparent)",
                  padding: 12,
                  display: "grid",
                  gap: 4,
                  minHeight: 56,
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                  <div style={{ fontWeight: 750, letterSpacing: "-0.01em" }}>{l.title}</div>
                  <div style={{ fontSize: 12, color: "var(--color-accent)", fontWeight: 700 }}>{t("common.open")}</div>
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{l.subtitle}</div>
              </Link>
            ))}
          </div>
        </section>

        <div
          style={{
            display: "grid",
            gap: 14,
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            alignItems: "start",
          }}
        >
          <section
            style={{
              padding: 14,
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              display: "grid",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ display: "grid", gap: 2 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>{t("home.today.title")}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{shanghaiToday.dateLocal}</div>
              </div>
              <button
                type="button"
                onClick={() => {
                  void loadToday();
                }}
                disabled={todayLoading}
                style={{
                  padding: "8px 10px",
                  borderRadius: 12,
                  border: "1px solid var(--color-border)",
                  background: "transparent",
                  color: "var(--color-text)",
                  cursor: todayLoading ? "not-allowed" : "pointer",
                }}
              >
                {todayLoading ? t("common.loading") : t("common.refresh")}
              </button>
            </div>

            {todayError ? (
              <div role="alert" style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                {t("home.today.failedPrefix")}
                {todayError}
              </div>
            ) : null}

            {todayWarning && !todayError ? (
              <div style={{ fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.4 }}>{todayWarning}</div>
            ) : null}

            {!todayLoading && !todayError && todayRows.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("home.today.noOccurrences")}</div>
            ) : null}

            <div style={{ display: "grid", gap: 10 }}>
              {todayLoading ? (
                <>
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                </>
              ) : (
                todayRows.map((row) => (
                  <div
                    key={row.key}
                    style={{
                      border: "1px solid var(--color-border)",
                      borderRadius: 12,
                      padding: 12,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 12,
                      background: row.done ? "color-mix(in srgb, var(--color-accent) 10%, var(--color-surface))" : "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "baseline", gap: 10, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)", flex: "0 0 auto" }}>{row.timeLocal}</div>
                      <div
                        title={row.title}
                        style={{
                          fontSize: 14,
                          fontWeight: 700,
                          color: "var(--color-text)",
                          textDecoration: row.done ? "line-through" : "none",
                          opacity: row.done ? 0.72 : 1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {row.title}
                      </div>
                    </div>

                    {row.done ? (
                      <div
                        style={{
                          flex: "0 0 auto",
                          padding: "6px 10px",
                          borderRadius: 999,
                          border: "1px solid color-mix(in srgb, var(--color-accent) 56%, var(--color-border))",
                          background: "color-mix(in srgb, var(--color-accent) 16%, transparent)",
                          color: "var(--color-accent)",
                          fontSize: 12,
                          fontWeight: 700,
                          lineHeight: 1,
                        }}
                      >
                        {t("common.done")}
                      </div>
                    ) : null}
                  </div>
                ))
              )}
            </div>

            {!todayLoading && !todayError && todayTotal > 10 ? (
              <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                {locale === "zh-CN" ? `仅展示前 10 条，共 ${todayTotal} 条。` : `Showing 10 / ${todayTotal} occurrences.`}
              </div>
            ) : null}
          </section>

          <section
            style={{
              padding: 14,
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              display: "grid",
              gap: 12,
            }}
          >
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ fontSize: 15, fontWeight: 700, color: "var(--color-text)" }}>{t("home.recentNotes.title")}</div>
              <button
                type="button"
                onClick={() => {
                  void loadNotes();
                }}
                disabled={notesLoading}
                style={{
                  padding: "8px 10px",
                  borderRadius: 12,
                  border: "1px solid var(--color-border)",
                  background: "transparent",
                  color: "var(--color-text)",
                  cursor: notesLoading ? "not-allowed" : "pointer",
                }}
              >
                {notesLoading ? t("common.loading") : t("common.refresh")}
              </button>
            </div>

            {notesError ? (
              <div role="alert" style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
                {t("home.recentNotes.failedPrefix")}
                {notesError}
              </div>
            ) : null}

            {!notesLoading && !notesError && notes.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("home.recentNotes.empty")}</div>
            ) : null}

            <div style={{ display: "grid", gap: 10 }}>
              {notesLoading ? (
                <>
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                  <div className="skeleton" style={{ height: 44, borderRadius: 12, border: "1px solid var(--color-border)" }} />
                </>
              ) : (
                notes.map((n) => (
                  <Link
                    key={n.id}
                    href={`/notes?id=${encodeURIComponent(n.id)}`}
                    style={{
                      border: "1px solid var(--color-border)",
                      borderRadius: 12,
                      padding: 12,
                      display: "grid",
                      gap: 6,
                      textDecoration: "none",
                      color: "var(--color-text)",
                      background: "transparent",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
                      <div
                        title={n.title || t("common.untitled")}
                        style={{
                          fontSize: 14,
                          fontWeight: 750,
                          color: "var(--color-accent)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {n.title || t("common.untitled")}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)", flex: "0 0 auto" }}>{n.updated_at.slice(0, 10)}</div>
                    </div>
                    {n.body_md ? (
                      <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.4 }}>
                        {n.body_md.trim().replace(/\s+/g, " ").slice(0, 180)}
                        {n.body_md.trim().replace(/\s+/g, " ").length > 180 ? "..." : ""}
                      </div>
                    ) : null}
                  </Link>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </Page>
  );
}

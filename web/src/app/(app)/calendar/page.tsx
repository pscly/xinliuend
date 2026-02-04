"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Page } from "@/features/ui/Page";

import {
  deleteTodoOccurrence,
  getTodoItems,
  getTodoOccurrences,
  upsertTodoOccurrence,
} from "@/features/todo/todoApi";
import { expandRruleToLocalIds } from "@/features/todo/recurrence";
import type { LocalDateTimeString, TodoItem, TodoOccurrence } from "@/features/todo/types";

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

function getWeekdayShortFromShanghaiDayStartUtcMs(dayStartUtcMs: number): string {
  const weekday = new Date(dayStartUtcMs + SHANGHAI_OFFSET_MS).getUTCDay();
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return names[weekday] ?? "";
}

type DayMeta = {
  dateLocal: string; // YYYY-MM-DD
  label: string;
};

type OccurrenceRow = {
  key: string;
  itemId: string;
  title: string;
  recurrenceIdLocal: LocalDateTimeString;
  dateLocal: string;
  timeLocal: string;
  done: boolean;
  overrideId: string | null;
};

type DayBucket = DayMeta & {
  rows: OccurrenceRow[];
};

function isOccurrenceDone(occ: TodoOccurrence | undefined): boolean {
  if (!occ) return false;
  if (occ.completed_at_local) return true;
  return occ.status_override === "done";
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

function getRecurringItems(items: TodoItem[]): RecurringReadyItem[] {
  return items.filter(isRecurringReadyItem);
}

function buildShanghai7DayRange(nowUtcMs: number): { from: LocalDateTimeString; to: LocalDateTimeString; days: DayMeta[] } {
  const startUtcMs = getShanghaiTodayStartUtcMs(nowUtcMs);
  const from = formatUtcMsToShanghaiLocal(startUtcMs);
  const to = formatUtcMsToShanghaiLocal(startUtcMs + 7 * DAY_MS - 1000);
  const days: DayMeta[] = [];

  for (let i = 0; i < 7; i += 1) {
    const dayStartUtcMs = startUtcMs + i * DAY_MS;
    const dayStartLocal = formatUtcMsToShanghaiLocal(dayStartUtcMs);
    const dateLocal = dayStartLocal.slice(0, 10);
    const weekday = getWeekdayShortFromShanghaiDayStartUtcMs(dayStartUtcMs);
    days.push({ dateLocal, label: `${weekday} ${dateLocal}` });
  }

  return { from, to, days };
}

function normalizeErr(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function updateRowInBuckets(buckets: DayBucket[], key: string, patch: Partial<Pick<OccurrenceRow, "done" | "overrideId">>): DayBucket[] {
  return buckets.map((b) => ({
    ...b,
    rows: b.rows.map((r) => (r.key === key ? { ...r, ...patch } : r)),
  }));
}

export default function CalendarPage() {
  const [initialNowMs] = useState(() => Date.now());
  const range = useMemo(() => buildShanghai7DayRange(initialNowMs), [initialNowMs]);

  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [busyByKey, setBusyByKey] = useState<Record<string, boolean>>({});
  const [buckets, setBuckets] = useState<DayBucket[]>(() => range.days.map((d) => ({ ...d, rows: [] })));

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const itemsResp = await getTodoItems();
      const recurring = getRecurringItems(itemsResp.data.items);

      const occurrenceRespList = await Promise.all(
        recurring.map((it) => getTodoOccurrences({ item_id: it.id, from: range.from, to: range.to }))
      );
      const overrideByKey = new Map<string, TodoOccurrence>();
      for (const resp of occurrenceRespList) {
        for (const occ of resp.data.items) {
          overrideByKey.set(`${occ.item_id}::${occ.recurrence_id_local}`, occ);
        }
      }

      const dateToIndex = new Map<string, number>();
      range.days.forEach((d, idx) => {
        dateToIndex.set(d.dateLocal, idx);
      });

      const nextBuckets: DayBucket[] = range.days.map((d) => ({ ...d, rows: [] }));
      for (const it of recurring) {
        const recurrenceIds = expandRruleToLocalIds(
          { rrule: it.rrule, dtstart_local: it.dtstart_local },
          { from: range.from, to: range.to }
        );
        for (const rid of recurrenceIds) {
          const dateLocal = rid.slice(0, 10);
          const idx = dateToIndex.get(dateLocal);
          if (idx === undefined) continue;

          const key = `${it.id}::${rid}`;
          const override = overrideByKey.get(key);
          const title = override?.title_override ?? it.title;
          const done = isOccurrenceDone(override);
          const timeLocal = rid.slice(11, 16);
          nextBuckets[idx].rows.push({
            key,
            itemId: it.id,
            title,
            recurrenceIdLocal: rid,
            dateLocal,
            timeLocal,
            done,
            overrideId: override?.id ?? null,
          });
        }
      }

      for (const b of nextBuckets) {
        b.rows.sort((a, c) => {
          const t = a.recurrenceIdLocal.localeCompare(c.recurrenceIdLocal);
          if (t !== 0) return t;
          return a.title.localeCompare(c.title);
        });
      }

      setBuckets(nextBuckets);
    } catch (err: unknown) {
      setError(normalizeErr(err));
    } finally {
      setLoading(false);
    }
  }, [range.days, range.from, range.to]);

  useEffect(() => {
    void load();
  }, [load]);

  const onToggle = useCallback(
    async (row: OccurrenceRow) => {
      if (busyByKey[row.key]) return;
      setError(null);

      setBusyByKey((prev) => ({ ...prev, [row.key]: true }));
      try {
        if (!row.done) {
          const nowUtcMs = Date.now();
          const nowLocal = formatUtcMsToShanghaiLocal(nowUtcMs);
          const resp = await upsertTodoOccurrence({
            item_id: row.itemId,
            recurrence_id_local: row.recurrenceIdLocal,
            status_override: "done",
            completed_at_local: nowLocal,
            client_updated_at_ms: nowUtcMs,
          });
          setBuckets((prev) => updateRowInBuckets(prev, row.key, { done: true, overrideId: resp.data.id }));
        } else {
          if (!row.overrideId) return;
          await deleteTodoOccurrence(row.overrideId, Date.now());
          setBuckets((prev) => updateRowInBuckets(prev, row.key, { done: false, overrideId: null }));
        }
      } catch (err: unknown) {
        setError(normalizeErr(err));
      } finally {
        setBusyByKey((prev) => {
          const next = { ...prev };
          delete next[row.key];
          return next;
        });
      }
    },
    [busyByKey]
  );

  return (
    <Page titleKey="page.calendar.title">
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div style={{ fontSize: 13, opacity: 0.8 }}>
            Range (Asia/Shanghai): <code>{range.from}</code> to <code>{range.to}</code>
          </div>
          <button
            type="button"
            onClick={() => {
              void load();
            }}
            disabled={loading}
            style={{
              padding: "8px 10px",
              borderRadius: 10,
              border: "1px solid var(--border-color, rgba(120,120,120,0.25))",
              background: "var(--card-bg, transparent)",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {error ? (
          <div
            role="alert"
            style={{
              padding: 10,
              borderRadius: 10,
              border: "1px solid rgba(220, 40, 40, 0.35)",
              background: "rgba(220, 40, 40, 0.06)",
              color: "rgba(220, 40, 40, 0.95)",
              fontSize: 13,
            }}
          >
            {error}
          </div>
        ) : null}

        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          }}
        >
          {buckets.map((b) => (
            <section
              key={b.dateLocal}
              style={{
                borderRadius: 12,
                border: "1px solid var(--border-color, rgba(120,120,120,0.25))",
                padding: 10,
                minHeight: 120,
                overflow: "hidden",
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, opacity: 0.9, marginBottom: 8 }}>{b.label}</div>
              {b.rows.length === 0 ? (
                <div style={{ fontSize: 12, opacity: 0.55 }}>No occurrences</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {b.rows.map((row) => {
                    const busy = Boolean(busyByKey[row.key]);
                    return (
                      <div
                        key={row.key}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          gap: 10,
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "baseline", gap: 8, minWidth: 0 }}>
                          <div style={{ fontSize: 12, opacity: 0.7, flex: "0 0 auto" }}>{row.timeLocal}</div>
                          <div
                            title={row.title}
                            style={{
                              fontSize: 13,
                              textDecoration: row.done ? "line-through" : "none",
                              opacity: row.done ? 0.6 : 1,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {row.title}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            void onToggle(row);
                          }}
                          disabled={busy}
                          style={{
                            padding: "6px 10px",
                            borderRadius: 999,
                            border: "1px solid var(--border-color, rgba(120,120,120,0.25))",
                            background: row.done ? "rgba(60, 180, 80, 0.12)" : "transparent",
                            color: row.done ? "rgba(60, 180, 80, 0.95)" : "inherit",
                            cursor: busy ? "not-allowed" : "pointer",
                            fontSize: 12,
                            flex: "0 0 auto",
                          }}
                          title={row.done ? "Mark occurrence undone" : "Mark occurrence done"}
                        >
                          {busy ? "..." : row.done ? "Done" : "Mark"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>
          ))}
        </div>

        <div style={{ fontSize: 12, opacity: 0.6 }}>
          Showing recurring todo occurrences only. Override deletion only applies when an override exists.
        </div>
      </div>
    </Page>
  );
}

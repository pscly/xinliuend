"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getTodoItems, getTodoLists, upsertTodoItem, upsertTodoList } from "@/features/todo/todoApi";
import type { LocalDateTimeString, TodoItem, TodoList } from "@/features/todo/types";
import { Page } from "@/features/ui/Page";
import { useI18n } from "@/lib/i18n/useI18n";

const TZID = "Asia/Shanghai" as const;

type DateTimePart = "year" | "month" | "day" | "hour" | "minute" | "second";

function formatLocalDateTimeString19(date: Date): LocalDateTimeString {
  // Backend expects local datetime without offset: YYYY-MM-DDTHH:mm:ss (length=19).
  // We use Intl formatting (no Date.toISOString()) and explicitly pick Asia/Shanghai.
  const dtf = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZID,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const parts = dtf.formatToParts(date);
  const map: Partial<Record<DateTimePart, string>> = {};
  for (const p of parts) {
    if (
      p.type === "year" ||
      p.type === "month" ||
      p.type === "day" ||
      p.type === "hour" ||
      p.type === "minute" ||
      p.type === "second"
    ) {
      map[p.type] = p.value;
    }
  }

  const year = map.year ?? String(date.getFullYear());
  const month = map.month ?? String(date.getMonth() + 1).padStart(2, "0");
  const day = map.day ?? String(date.getDate()).padStart(2, "0");
  const hour = map.hour ?? String(date.getHours()).padStart(2, "0");
  const minute = map.minute ?? String(date.getMinutes()).padStart(2, "0");
  const second = map.second ?? String(date.getSeconds()).padStart(2, "0");

  const s = `${year}-${month}-${day}T${hour}:${minute}:${second}`;
  // Ensure the contract length=19; fallback is still safe.
  return (s.length === 19 ? s : s.slice(0, 19)) as LocalDateTimeString;
}

function toHumanLocalDateTime(dt: LocalDateTimeString | null | undefined): string {
  return dt ?? "-";
}

function clampInt(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, Math.trunc(value)));
}

function normalizeErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  return "未知错误";
}

export default function TodosPage() {
  const { locale, t } = useI18n();
  const [lists, setLists] = useState<TodoList[]>([]);
  const [selectedListId, setSelectedListId] = useState<string>("");
  const [items, setItems] = useState<TodoItem[]>([]);

  const [listsLoading, setListsLoading] = useState(false);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [listsError, setListsError] = useState<string | null>(null);
  const [itemsError, setItemsError] = useState<string | null>(null);

  const [newListName, setNewListName] = useState("");
  const [creatingList, setCreatingList] = useState(false);

  const [newItemTitle, setNewItemTitle] = useState("");
  const [creatingItem, setCreatingItem] = useState(false);
  const [recurringDaily, setRecurringDaily] = useState(false);
  const [recurringDays, setRecurringDays] = useState<number>(7);

  const selectedList = useMemo(() => lists.find((l) => l.id === selectedListId) ?? null, [lists, selectedListId]);

  const refreshLists = useCallback(
    async (preferListId?: string) => {
      setListsLoading(true);
      setListsError(null);
      try {
        const res = await getTodoLists();
        const next = res.items;
        setLists(next);

        const desired = preferListId ?? selectedListId;
        const hasDesired = desired ? next.some((l) => l.id === desired) : false;
        if (hasDesired) {
          setSelectedListId(desired);
        } else {
          setSelectedListId(next[0]?.id ?? "");
        }
      } catch (err: unknown) {
        setListsError(normalizeErrorMessage(err));
      } finally {
        setListsLoading(false);
      }
    },
    [selectedListId]
  );

  const refreshItems = useCallback(async (listId: string) => {
    setItemsLoading(true);
    setItemsError(null);
    try {
      const res = await getTodoItems({ list_id: listId, include_deleted: false, limit: 200 });
      setItems(res.items);
    } catch (err: unknown) {
      setItemsError(normalizeErrorMessage(err));
    } finally {
      setItemsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshLists();
  }, [refreshLists]);

  useEffect(() => {
    if (!selectedListId) {
      setItems([]);
      return;
    }
    void refreshItems(selectedListId);
  }, [refreshItems, selectedListId]);

  const canCreateItem = Boolean(selectedListId) && newItemTitle.trim().length > 0 && !creatingItem;
  const canCreateList = newListName.trim().length > 0 && !creatingList;

  return (
    <Page titleKey="page.todos.title">
      <div
        style={{
          display: "grid",
          gap: 12,
          padding: "0 16px 16px",
        }}
      >
        <section
          style={{
            border: "1px solid var(--border, rgba(0,0,0,0.12))",
            borderRadius: 14,
            background: "var(--surface-1, rgba(0,0,0,0.02))",
            padding: 12,
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label style={{ display: "grid", gap: 6, minWidth: 220, flex: "1 1 260px" }}>
              <span style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>{t("todos.list.label")}</span>
              <select
                data-testid="todo-list-select"
                value={selectedListId}
                onChange={(e) => setSelectedListId(e.target.value)}
                disabled={listsLoading || lists.length === 0}
                style={{
                  height: 36,
                  borderRadius: 10,
                  border: "1px solid var(--border, rgba(0,0,0,0.18))",
                  background: "var(--surface-0, transparent)",
                  color: "var(--text-1, inherit)",
                  padding: "0 10px",
                }}
              >
                {lists.length === 0 ? <option value="">{t("todos.list.none")}</option> : null}
                {lists.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              onClick={() => void refreshLists()}
              disabled={listsLoading}
              style={{
                height: 36,
                padding: "0 12px",
                borderRadius: 10,
                border: "1px solid var(--border, rgba(0,0,0,0.18))",
                background: "var(--surface-0, transparent)",
                color: "var(--text-1, inherit)",
                cursor: listsLoading ? "not-allowed" : "pointer",
              }}
            >
              {listsLoading ? t("common.loading") : t("common.reload")}
            </button>
          </div>

          {listsError ? (
            <div style={{ color: "var(--danger, #b42318)", fontSize: 12 }}>
              {t("todos.lists.loadFailedPrefix")}
              {listsError}
            </div>
          ) : null}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canCreateList) return;
              const name = newListName.trim();
              void (async () => {
                setCreatingList(true);
                setListsError(null);
                try {
                  const res = await upsertTodoList({ name, client_updated_at_ms: Date.now() });
                  setNewListName("");
                  await refreshLists(res.id);
                } catch (err: unknown) {
                  setListsError(normalizeErrorMessage(err));
                } finally {
                  setCreatingList(false);
                }
              })();
            }}
            style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}
          >
            <label style={{ display: "grid", gap: 6, minWidth: 220, flex: "1 1 260px" }}>
              <span style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>{t("todos.list.new.label")}</span>
              <input
                data-testid="todo-new-list-name"
                value={newListName}
                onChange={(e) => setNewListName(e.target.value)}
                placeholder={t("todos.list.new.placeholder")}
                style={{
                  height: 36,
                  borderRadius: 10,
                  border: "1px solid var(--border, rgba(0,0,0,0.18))",
                  background: "var(--surface-0, transparent)",
                  color: "var(--text-1, inherit)",
                  padding: "0 10px",
                }}
              />
            </label>
            <button
              data-testid="todo-create-list"
              type="submit"
              disabled={!canCreateList}
              style={{
                height: 36,
                padding: "0 14px",
                borderRadius: 10,
                border: "1px solid var(--border, rgba(0,0,0,0.18))",
                background: "var(--accent, #111)",
                color: "var(--accent-contrast, #fff)",
                cursor: canCreateList ? "pointer" : "not-allowed",
              }}
            >
              {creatingList ? t("common.creating") : t("todos.list.new.create")}
            </button>
          </form>
        </section>

        <section
          style={{
            border: "1px solid var(--border, rgba(0,0,0,0.12))",
            borderRadius: 14,
            background: "var(--surface-1, rgba(0,0,0,0.02))",
            padding: 12,
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
            <div style={{ display: "grid", gap: 2 }}>
              <div style={{ fontWeight: 650, letterSpacing: "-0.01em" }}>{selectedList ? selectedList.name : t("todos.items.titleFallback")}</div>
              <div style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>
                {itemsLoading
                  ? t("todos.items.loading")
                  : locale === "zh-CN"
                    ? `${items.length}${t("todos.items.countUnit")}`
                    : `${items.length} ${t("todos.items.countUnit")}`}
              </div>
            </div>
            <button
              type="button"
              onClick={() => (selectedListId ? void refreshItems(selectedListId) : undefined)}
              disabled={!selectedListId || itemsLoading}
              style={{
                height: 32,
                padding: "0 12px",
                borderRadius: 10,
                border: "1px solid var(--border, rgba(0,0,0,0.18))",
                background: "var(--surface-0, transparent)",
                color: "var(--text-1, inherit)",
                cursor: !selectedListId || itemsLoading ? "not-allowed" : "pointer",
              }}
            >
              {t("common.refresh")}
            </button>
          </div>

          {itemsError ? (
            <div style={{ color: "var(--danger, #b42318)", fontSize: 12 }}>
              {t("todos.items.loadFailedPrefix")}
              {itemsError}
            </div>
          ) : null}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!canCreateItem) return;
              const title = newItemTitle.trim();
              const days = clampInt(recurringDays, 1, 365);
              void (async () => {
                setCreatingItem(true);
                setItemsError(null);
                try {
                  const base = {
                    list_id: selectedListId,
                    title,
                    client_updated_at_ms: Date.now(),
                  };

                  if (recurringDaily) {
                    const dtstart = formatLocalDateTimeString19(new Date());
                    await upsertTodoItem({
                      ...base,
                      is_recurring: true,
                      rrule: `FREQ=DAILY;COUNT=${days}`,
                      dtstart_local: dtstart,
                      tzid: TZID,
                    });
                  } else {
                    await upsertTodoItem(base);
                  }

                  setNewItemTitle("");
                  await refreshItems(selectedListId);
                } catch (err: unknown) {
                  setItemsError(normalizeErrorMessage(err));
                } finally {
                  setCreatingItem(false);
                }
              })();
            }}
            style={{ display: "grid", gap: 10 }}
          >
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "end" }}>
              <label style={{ display: "grid", gap: 6, minWidth: 220, flex: "1 1 360px" }}>
                <span style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>{t("todos.item.new.label")}</span>
                <input
                  data-testid="todo-new-item-title"
                  value={newItemTitle}
                  onChange={(e) => setNewItemTitle(e.target.value)}
                  placeholder={selectedListId ? t("todos.item.new.placeholder") : t("todos.item.new.placeholderNoList")}
                  disabled={!selectedListId}
                  style={{
                    height: 36,
                    borderRadius: 10,
                    border: "1px solid var(--border, rgba(0,0,0,0.18))",
                    background: "var(--surface-0, transparent)",
                    color: "var(--text-1, inherit)",
                    padding: "0 10px",
                  }}
                />
              </label>
              <button
                data-testid="todo-add-item"
                type="submit"
                disabled={!canCreateItem}
                style={{
                  height: 36,
                  padding: "0 14px",
                  borderRadius: 10,
                  border: "1px solid var(--border, rgba(0,0,0,0.18))",
                  background: "var(--accent, #111)",
                  color: "var(--accent-contrast, #fff)",
                  cursor: canCreateItem ? "pointer" : "not-allowed",
                }}
              >
                {creatingItem ? t("todos.item.new.adding") : t("todos.item.new.add")}
              </button>
            </div>

            <div
              style={{
                display: "flex",
                gap: 10,
                flexWrap: "wrap",
                alignItems: "center",
                borderTop: "1px dashed var(--border, rgba(0,0,0,0.18))",
                paddingTop: 10,
              }}
            >
              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                <input
                  data-testid="todo-recurring-daily"
                  type="checkbox"
                  checked={recurringDaily}
                  onChange={(e) => setRecurringDaily(e.target.checked)}
                />
                {t("todos.item.recurring.daily")}
              </label>

              <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
                <span style={{ color: "var(--muted, rgba(0,0,0,0.6))" }}>{t("todos.item.recurring.days")}</span>
                <input
                  data-testid="todo-recurring-days"
                  type="number"
                  min={1}
                  max={365}
                  value={recurringDays}
                  onChange={(e) => setRecurringDays(clampInt(Number(e.target.value), 1, 365))}
                  disabled={!recurringDaily}
                  style={{
                    width: 84,
                    height: 32,
                    borderRadius: 10,
                    border: "1px solid var(--border, rgba(0,0,0,0.18))",
                    background: "var(--surface-0, transparent)",
                    color: "var(--text-1, inherit)",
                    padding: "0 10px",
                  }}
                />
              </label>

              <div style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>
                RRULE: <code style={{ fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)" }}>{`FREQ=DAILY;COUNT=${clampInt(recurringDays, 1, 365)}`}</code>
                <span style={{ marginLeft: 10 }}>
                  dtstart_local: <code style={{ fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)" }}>{formatLocalDateTimeString19(new Date())}</code>
                </span>
                <span style={{ marginLeft: 10 }}>
                  tzid: <code style={{ fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)" }}>{TZID}</code>
                </span>
              </div>
            </div>
          </form>

          <div
            style={{
              border: "1px solid var(--border, rgba(0,0,0,0.12))",
              borderRadius: 12,
              overflow: "hidden",
              background: "var(--surface-0, transparent)",
            }}
          >
            {items.length === 0 ? (
              <div style={{ padding: 12, fontSize: 13, color: "var(--muted, rgba(0,0,0,0.6))" }}>{t("todos.items.empty")}</div>
            ) : (
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {items.map((it) => (
                  <li
                    key={it.id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr auto",
                      gap: 10,
                      padding: "10px 12px",
                      borderTop: "1px solid var(--border, rgba(0,0,0,0.10))",
                      alignItems: "start",
                    }}
                  >
                    <div style={{ display: "grid", gap: 2 }}>
                      <div style={{ fontSize: 14, lineHeight: 1.35 }}>{it.title}</div>
                      <div style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))" }}>
                        {it.is_recurring ? (
                          <span>
                            {t("todos.item.recurring")} ·{" "}
                            <code style={{ fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)" }}>{it.rrule ?? "-"}</code> ·
                            <span style={{ marginLeft: 6 }}>
                              dtstart_local <code style={{ fontFamily: "var(--mono, ui-monospace, SFMono-Regular, Menlo, monospace)" }}>{toHumanLocalDateTime(it.dtstart_local)}</code>
                            </span>
                          </span>
                        ) : (
                          <span>{t("todos.item.oneOff")}</span>
                        )}
                      </div>
                    </div>

                    <div style={{ fontSize: 12, color: "var(--muted, rgba(0,0,0,0.6))", textAlign: "right" }}>
                      {it.status}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </Page>
  );
}

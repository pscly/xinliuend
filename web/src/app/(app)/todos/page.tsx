"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { getTodoItems, getTodoLists, upsertTodoItem, upsertTodoList } from "@/features/todo/todoApi";
import type { LocalDateTimeString, TodoItem, TodoList } from "@/features/todo/types";
import { Page } from "@/features/ui/Page";
import { InkButton } from "@/features/ui/InkButton";
import { InkSelectField, InkTextField } from "@/features/ui/InkField";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./TodosPage.module.css";

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

function formatTodoStatus(status: string): string {
  const s = (status ?? "").trim().toLowerCase();
  if (!s) return "-";
  if (s === "open") return "未完成";
  if (s === "done") return "已完成";
  if (s === "archived") return "已归档";
  return status;
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
      <div className={styles.content}>
        <section className={styles.panel}>
          <div className={styles.row}>
            <InkSelectField
              className={styles.grow}
              label={t("todos.list.label")}
              data-testid="todo-list-select"
              value={selectedListId}
              onChange={(e) => setSelectedListId(e.target.value)}
              disabled={listsLoading || lists.length === 0}
            >
              {lists.length === 0 ? <option value="">{t("todos.list.none")}</option> : null}
              {lists.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </InkSelectField>

            <InkButton type="button" variant="ghost" onClick={() => void refreshLists()} disabled={listsLoading}>
              {listsLoading ? t("common.loading") : t("common.reload")}
            </InkButton>
          </div>

          {listsError ? (
            <div className={styles.error}>
              {t("todos.lists.loadFailedPrefix")}
              {listsError}
            </div>
          ) : null}

          <form
            className={`${styles.row} ${styles.rowEnd}`}
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
          >
            <InkTextField
              className={styles.grow}
              label={t("todos.list.new.label")}
              data-testid="todo-new-list-name"
              value={newListName}
              onChange={(e) => setNewListName(e.target.value)}
              placeholder={t("todos.list.new.placeholder")}
            />

            <InkButton data-testid="todo-create-list" type="submit" variant="primary" disabled={!canCreateList}>
              {creatingList ? t("common.creating") : t("todos.list.new.create")}
            </InkButton>
          </form>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHeader}>
            <div style={{ display: "grid", gap: 2 }}>
              <div className={styles.panelTitle}>{selectedList ? selectedList.name : t("todos.items.titleFallback")}</div>
              <div className={styles.panelMeta}>
                {itemsLoading
                  ? t("todos.items.loading")
                  : locale === "zh-CN"
                    ? `${items.length}${t("todos.items.countUnit")}`
                    : `${items.length} ${t("todos.items.countUnit")}`}
              </div>
            </div>

            <InkButton
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => (selectedListId ? void refreshItems(selectedListId) : undefined)}
              disabled={!selectedListId || itemsLoading}
            >
              {t("common.refresh")}
            </InkButton>
          </div>

          {itemsError ? (
            <div className={styles.error}>
              {t("todos.items.loadFailedPrefix")}
              {itemsError}
            </div>
          ) : null}

          <form
            className={styles.form}
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
          >
            <div className={`${styles.row} ${styles.rowEnd}`}>
              <InkTextField
                className={styles.grow}
                label={t("todos.item.new.label")}
                data-testid="todo-new-item-title"
                value={newItemTitle}
                onChange={(e) => setNewItemTitle(e.target.value)}
                placeholder={selectedListId ? t("todos.item.new.placeholder") : t("todos.item.new.placeholderNoList")}
                disabled={!selectedListId}
              />

              <InkButton data-testid="todo-add-item" type="submit" variant="primary" disabled={!canCreateItem}>
                {creatingItem ? t("todos.item.new.adding") : t("todos.item.new.add")}
              </InkButton>
            </div>

            <div className={styles.recurringRow}>
              <label className={styles.checkLabel}>
                <input
                  data-testid="todo-recurring-daily"
                  type="checkbox"
                  checked={recurringDaily}
                  onChange={(e) => setRecurringDaily(e.target.checked)}
                />
                {t("todos.item.recurring.daily")}
              </label>

              <label className={styles.checkLabel}>
                <span className={`${styles.muted}`}>{t("todos.item.recurring.days")}</span>
                <input
                  data-testid="todo-recurring-days"
                  type="number"
                  min={1}
                  max={365}
                  value={recurringDays}
                  onChange={(e) => setRecurringDays(clampInt(Number(e.target.value), 1, 365))}
                  disabled={!recurringDaily}
                  className={styles.smallNumber}
                />
              </label>

              <div className={styles.panelMeta}>
                重复规则： <code className={styles.mono}>{`FREQ=DAILY;COUNT=${clampInt(recurringDays, 1, 365)}`}</code>
                <span style={{ marginLeft: 10 }}>
                  起始时间： <code className={styles.mono}>{formatLocalDateTimeString19(new Date())}</code>
                </span>
                <span style={{ marginLeft: 10 }}>
                  时区： <code className={styles.mono}>{TZID}</code>
                </span>
              </div>
            </div>
          </form>

          <div className={styles.itemsBox}>
            {items.length === 0 ? (
              <div className={styles.empty}>{t("todos.items.empty")}</div>
            ) : (
              <ul className={styles.itemsList}>
                {items.map((it) => (
                  <li key={it.id} className={styles.itemRow}>
                    <div className={styles.itemMain}>
                      <div className={styles.itemTitle}>{it.title}</div>
                      <div className={styles.itemSub}>
                        {it.is_recurring ? (
                          <span>
                            {t("todos.item.recurring")} · <code className={styles.mono}>{it.rrule ?? "-"}</code> ·
                            <span style={{ marginLeft: 6 }}>
                              起始时间 <code className={styles.mono}>{toHumanLocalDateTime(it.dtstart_local)}</code>
                            </span>
                          </span>
                        ) : (
                          <span>{t("todos.item.oneOff")}</span>
                        )}
                      </div>
                    </div>

                    <div className={styles.itemStatus}>{formatTodoStatus(it.status)}</div>
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

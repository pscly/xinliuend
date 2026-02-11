"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listNotifications, markNotificationRead } from "@/features/notifications/notificationsApi";
import type { Notification } from "@/features/notifications/types";
import { Page } from "@/features/ui/Page";
import { InkButton, InkLink } from "@/features/ui/InkButton";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./NotificationsPage.module.css";

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function getPayloadString(payload: Record<string, unknown>, key: string): string | null {
  const v = payload[key];
  return typeof v === "string" && v.trim() ? v : null;
}

function formatTimestamp(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

function formatNotificationKind(kind: string): string {
  const k = kind.trim().toLowerCase();
  if (!k) return "-";
  // Keep an English anchor ("mention") for test stability + debugging, but still show Chinese.
  if (k === "mention") return "mention（提及）";
  return kind;
}

export default function NotificationsPage() {
  const { locale, t } = useI18n();
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);

  const [items, setItems] = useState<Notification[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [markingIds, setMarkingIds] = useState<Set<string>>(() => new Set());

  const runIdRef = useRef<number>(0);

  const load = useCallback(async () => {
    const runId = ++runIdRef.current;
    setLoading(true);
    setError(null);

    try {
      const res = await listNotifications({ unread_only: unreadOnly, limit: 100, offset: 0 });
      if (runIdRef.current !== runId) return;
      setItems(res.notifications);
      setTotal(res.total);
    } catch (e) {
      if (runIdRef.current !== runId) return;
      setItems([]);
      setTotal(0);
      setError(e instanceof Error ? e.message : t("notifications.errorLoad"));
    } finally {
      if (runIdRef.current === runId) setLoading(false);
    }
  }, [t, unreadOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  const visibleItems = useMemo(() => items, [items]);

  async function onMarkRead(id: string) {
    if (markingIds.has(id)) return;
    setMarkingIds((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });

    try {
      const updated = await markNotificationRead(id);
      setItems((prev) => {
        const next = prev.map((n) => (n.id === id ? updated : n));
        if (!unreadOnly) return next;
        return next.filter((n) => n.read_at === null);
      });
      window.dispatchEvent(new Event("notifications:changed"));
    } catch (e) {
      setError(e instanceof Error ? e.message : t("notifications.errorMarkRead"));
    } finally {
      setMarkingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  return (
    <Page titleKey="page.notifications.title" subtitleKey="page.notifications.subtitle">
      <div className={styles.content}>
        <section className={styles.toolbar}>
          <label className={styles.toggleLabel}>
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.currentTarget.checked)} />
            <span>{t("notifications.unreadOnly")}</span>
          </label>

          <div className={styles.toolbarRight}>
            <div className={styles.stats}>
              {loading
                ? t("common.loading")
                : (() => {
                    const base = `${visibleItems.length}${total > visibleItems.length ? ` / ${total}` : ""}`;
                    return locale === "zh-CN" ? `${base} 条` : `${base} items`;
                  })()}
            </div>
            <InkButton
              type="button"
              size="sm"
              variant="ghost"
              onClick={() => {
                void load();
              }}
              disabled={loading}
            >
              {t("notifications.refresh")}
            </InkButton>
          </div>
        </section>

        {error ? (
          <div role="alert" className={styles.error}>
            {error}
          </div>
        ) : null}

        {!loading && !error && visibleItems.length === 0 ? <div className={styles.empty}>{t("notifications.empty")}</div> : null}

        <div className={styles.list}>
          {loading ? (
            <>
              <div
                className="skeleton"
                style={{ height: 72, borderRadius: "var(--radius-2)", border: "1px solid var(--color-border)" }}
              />
              <div
                className="skeleton"
                style={{ height: 72, borderRadius: "var(--radius-2)", border: "1px solid var(--color-border)" }}
              />
              <div
                className="skeleton"
                style={{ height: 72, borderRadius: "var(--radius-2)", border: "1px solid var(--color-border)" }}
              />
            </>
          ) : (
            visibleItems.map((n) => {
              const isUnread = n.read_at === null;
              const payload = isRecord(n.payload) ? n.payload : {};
              const shareToken = getPayloadString(payload, "share_token");
              const snippet = getPayloadString(payload, "snippet");
              const openHref = shareToken ? `/share?token=${encodeURIComponent(shareToken)}` : null;

              return (
                <article
                  key={n.id}
                  data-testid="notif-item"
                  className={`${styles.item} ${isUnread ? styles.itemUnread : ""}`}
                >
                  <div className={styles.itemTop}>
                    <div className={styles.itemLeft}>
                      <div className={styles.itemLeftTop}>
                        <div className={styles.kind}>{formatNotificationKind(n.kind)}</div>
                        {isUnread ? <div className={styles.unreadBadge}>{t("notifications.unread")}</div> : null}
                      </div>
                      <div className={styles.date}>{formatTimestamp(n.created_at)}</div>
                    </div>

                    <div className={styles.actions}>
                      {openHref ? (
                        <InkLink href={openHref} variant="surface" size="sm">
                          {t("notifications.openShare")}
                        </InkLink>
                      ) : null}
                      <InkButton
                        type="button"
                        size="sm"
                        variant={isUnread ? "surface" : "ghost"}
                        onClick={() => {
                          void onMarkRead(n.id);
                        }}
                        disabled={!isUnread || markingIds.has(n.id)}
                      >
                        {markingIds.has(n.id) ? t("notifications.marking") : isUnread ? t("notifications.markRead") : t("notifications.read")}
                      </InkButton>
                    </div>
                  </div>

                  {n.kind === "mention" && snippet ? (
                    <div className={styles.payload}>
                      <pre className={styles.payloadPre}>{snippet}</pre>
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
        </div>
      </div>
    </Page>
  );
}

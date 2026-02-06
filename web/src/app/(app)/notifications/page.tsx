"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { listNotifications, markNotificationRead } from "@/features/notifications/notificationsApi";
import type { Notification } from "@/features/notifications/types";
import { Page } from "@/features/ui/Page";
import { useI18n } from "@/lib/i18n/useI18n";

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
      <div style={{ padding: "16px 16px 20px", display: "grid", gap: 14 }}>
        <section
          style={{
            border: "1px solid var(--color-border)",
            borderRadius: 14,
            background: "var(--color-surface)",
            padding: 14,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
            flexWrap: "wrap",
          }}
        >
          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer", userSelect: "none" }}>
            <input type="checkbox" checked={unreadOnly} onChange={(e) => setUnreadOnly(e.currentTarget.checked)} />
            <span style={{ fontSize: 13, color: "var(--color-text)" }}>{t("notifications.unreadOnly")}</span>
          </label>

          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              {loading
                ? t("common.loading")
                : (() => {
                    const base = `${visibleItems.length}${total > visibleItems.length ? ` / ${total}` : ""}`;
                    return locale === "zh-CN" ? `${base} 条` : `${base} items`;
                  })()}
            </div>
            <button
              type="button"
              onClick={() => {
                void load();
              }}
              disabled={loading}
              style={{
                padding: "8px 10px",
                borderRadius: 12,
                border: "1px solid var(--color-border)",
                background: "transparent",
                color: "var(--color-text)",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {t("notifications.refresh")}
            </button>
          </div>
        </section>

        {error ? (
          <div role="alert" style={{ fontSize: 13, color: "var(--color-text-muted)" }}>
            {error}
          </div>
        ) : null}

        {!loading && !error && visibleItems.length === 0 ? (
          <div style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("notifications.empty")}</div>
        ) : null}

        <div style={{ display: "grid", gap: 10 }}>
          {loading ? (
            <>
              <div className="skeleton" style={{ height: 72, borderRadius: 14, border: "1px solid var(--color-border)" }} />
              <div className="skeleton" style={{ height: 72, borderRadius: 14, border: "1px solid var(--color-border)" }} />
              <div className="skeleton" style={{ height: 72, borderRadius: 14, border: "1px solid var(--color-border)" }} />
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
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: 14,
                    background: isUnread
                      ? "color-mix(in srgb, var(--color-accent) 10%, var(--color-surface))"
                      : "color-mix(in srgb, var(--color-surface-2) 52%, transparent)",
                    padding: 14,
                    display: "grid",
                    gap: 10,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ display: "grid", gap: 4, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <div style={{ fontSize: 12, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
                          {n.kind}
                        </div>
                        {isUnread ? (
                          <div
                            style={{
                              padding: "6px 10px",
                              borderRadius: 999,
                              border: "1px solid color-mix(in srgb, var(--color-accent-gold) 45%, var(--color-border))",
                              background: "color-mix(in srgb, var(--color-accent-gold) 14%, transparent)",
                              color: "var(--color-text)",
                              fontSize: 12,
                              fontWeight: 750,
                              lineHeight: 1,
                            }}
                          >
                            {t("notifications.unread")}
                          </div>
                        ) : null}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{formatTimestamp(n.created_at)}</div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
                      {openHref ? (
                        <Link
                          href={openHref}
                          style={{
                            border: "1px solid var(--color-border)",
                            borderRadius: "var(--radius-1)",
                            background: "var(--color-surface)",
                            color: "var(--color-text)",
                            padding: "8px 10px",
                            fontFamily: "var(--font-body)",
                            textDecoration: "none",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          {t("notifications.openShare")}
                        </Link>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => {
                          void onMarkRead(n.id);
                        }}
                        disabled={!isUnread || markingIds.has(n.id)}
                        style={{
                          border: "1px solid var(--color-border)",
                          borderRadius: "var(--radius-1)",
                          background: isUnread ? "var(--color-surface)" : "transparent",
                          color: isUnread ? "var(--color-text)" : "var(--color-text-muted)",
                          padding: "8px 10px",
                          fontFamily: "var(--font-body)",
                          cursor: !isUnread || markingIds.has(n.id) ? "not-allowed" : "pointer",
                        }}
                      >
                        {markingIds.has(n.id)
                          ? t("notifications.marking")
                          : isUnread
                            ? t("notifications.markRead")
                            : t("notifications.read")}
                      </button>
                    </div>
                  </div>

                  {n.kind === "mention" && snippet ? (
                    <div
                      style={{
                        border: "1px solid var(--color-border)",
                        borderRadius: 12,
                        background: "color-mix(in srgb, var(--color-surface) 86%, transparent)",
                        padding: 12,
                        fontFamily:
                          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                        fontSize: 12,
                        lineHeight: 1.6,
                        color: "var(--color-text)",
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                      }}
                    >
                      {snippet}
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

"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { MemosMigrationResponse, MemosMigrationSummary } from "@/features/memos/memosMigrationApi";
import { applyMemosMigration, previewMemosMigration } from "@/features/memos/memosMigrationApi";
import { Page } from "@/features/ui/Page";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";
import { useOfflineEnabled } from "@/lib/offline/useOfflineEnabled";
import type { SyncStatus } from "@/lib/offline/syncEngine";
import { getSyncStatus, subscribeSyncStatus, syncNow } from "@/lib/offline/syncEngine";
import { resetOfflineDb } from "@/lib/offline/db";

export default function SettingsPage() {
  const { user } = useAuth();
  const { t } = useI18n();
  const { offlineEnabled, updateOfflineEnabled } = useOfflineEnabled();

  const [preview, setPreview] = useState<MemosMigrationResponse | null>(null);
  const [applied, setApplied] = useState<MemosMigrationResponse | null>(null);
  const [busy, setBusy] = useState<"preview" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus>(() => getSyncStatus());
  const [clearingOffline, setClearingOffline] = useState(false);
  const [manualSyncing, setManualSyncing] = useState(false);

  useEffect(() => {
    return subscribeSyncStatus((next) => {
      setSyncStatus(next);
    });
  }, []);

  const lastSyncText = useMemo(() => {
    if (!syncStatus.last_sync_at_ms) return t("settings.offline.status.never");
    try {
      return new Date(syncStatus.last_sync_at_ms).toLocaleString();
    } catch {
      return String(syncStatus.last_sync_at_ms);
    }
  }, [syncStatus.last_sync_at_ms, t]);

  function formatSummaryLines(summary: MemosMigrationSummary) {
    return [
      { label: t("settings.memosMigration.summary.remoteTotal"), value: summary.remote_total },
      { label: t("settings.memosMigration.summary.create"), value: summary.created_local },
      { label: t("settings.memosMigration.summary.update"), value: summary.updated_local_from_remote },
      { label: t("settings.memosMigration.summary.delete"), value: summary.deleted_local_from_remote },
      { label: t("settings.memosMigration.summary.conflicts"), value: summary.conflicts },
    ];
  }

  return (
    <Page titleKey="page.settings.title">
      <div style={{ padding: "16px 16px 20px", display: "grid", gap: 14 }}>
        <section
          style={{
            borderTop: "1px solid var(--color-border)",
            paddingTop: 14,
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ fontSize: 13, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
            {t("settings.account.title")}
          </div>
          <div
            style={{
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              padding: 14,
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ fontSize: 13, color: "var(--color-text)", display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span style={{ color: "var(--color-text-muted)" }}>{t("settings.account.signedInAs")}</span>
              <span style={{ fontWeight: 750 }}>{user?.username ?? "-"}</span>
            </div>
            <div style={{ fontSize: 13, color: "var(--color-text)", display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span style={{ color: "var(--color-text-muted)" }}>{t("settings.account.role")}</span>
              <span style={{ fontWeight: 750 }}>
                {user?.isAdmin ? t("settings.account.role.admin") : t("settings.account.role.user")}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
              <Link
                href="/settings/password"
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-1)",
                  background: "var(--color-surface)",
                  color: "var(--color-text)",
                  padding: "8px 10px",
                  fontFamily: "var(--font-body)",
                  textDecoration: "none",
                }}
              >
                {t("settings.account.changePassword")}
              </Link>
            </div>
          </div>
        </section>

        <section
          style={{
            borderTop: "1px solid var(--color-border)",
            paddingTop: 14,
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ fontSize: 13, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
            {t("settings.memosMigration.title")}
          </div>

          <div
            style={{
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              padding: 14,
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: "var(--color-text)" }}>{t("settings.memosMigration.cardTitle")}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 4 }}>{t("settings.memosMigration.subtitle")}</div>
              </div>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  data-testid="settings-memos-preview"
                  disabled={busy !== null}
                  onClick={async () => {
                    setError(null);
                    setApplied(null);
                    setBusy("preview");
                    try {
                      const res = await previewMemosMigration();
                      setPreview(res);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : t("settings.memosMigration.errorGeneric"));
                    } finally {
                      setBusy(null);
                    }
                  }}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "transparent",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: busy !== null ? "not-allowed" : "pointer",
                    opacity: busy !== null ? 0.7 : 1,
                  }}
                >
                  {busy === "preview" ? t("settings.memosMigration.previewing") : t("settings.memosMigration.preview")}
                </button>

                <button
                  type="button"
                  data-testid="settings-memos-apply"
                  disabled={busy !== null || !preview}
                  onClick={async () => {
                    if (!preview) return;
                    if (!window.confirm(t("settings.memosMigration.confirmApply"))) return;
                    setError(null);
                    setBusy("apply");
                    try {
                      const res = await applyMemosMigration();
                      setApplied(res);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : t("settings.memosMigration.errorGeneric"));
                    } finally {
                      setBusy(null);
                    }
                  }}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: preview ? "var(--color-surface)" : "transparent",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: busy !== null || !preview ? "not-allowed" : "pointer",
                    opacity: busy !== null || !preview ? 0.6 : 1,
                  }}
                >
                  {busy === "apply" ? t("settings.memosMigration.applying") : t("settings.memosMigration.apply")}
                </button>
              </div>
            </div>

            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{t("settings.memosMigration.hint")}</div>

            {error ? (
              <div style={{ fontSize: 12, color: "var(--color-danger)" }}>
                {t("settings.memosMigration.errorPrefix")}
                {error}
              </div>
            ) : null}

            {preview ? (
              <div
                data-testid="settings-memos-summary"
                style={{
                  borderTop: "1px solid var(--color-border)",
                  paddingTop: 10,
                  display: "grid",
                  gap: 8,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 800, color: "var(--color-text)" }}>{t("settings.memosMigration.previewResult")}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                  {formatSummaryLines(preview.summary).map((row) => (
                    <div key={row.label} style={{ border: "1px solid var(--color-border)", borderRadius: 12, padding: 10 }}>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{row.label}</div>
                      <div style={{ fontSize: 16, fontWeight: 850, color: "var(--color-text)", marginTop: 4 }}>{row.value}</div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  {t("settings.memosMigration.memosBaseUrlPrefix")}
                  {preview.memos_base_url}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  {t("settings.memosMigration.warningsTitle")}：{" "}
                  {preview.warnings?.length ? preview.warnings.join("；") : t("settings.memosMigration.warningsEmpty")}
                </div>
              </div>
            ) : null}

            {applied ? (
              <div
                style={{
                  borderTop: "1px solid var(--color-border)",
                  paddingTop: 10,
                  display: "grid",
                  gap: 8,
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 800, color: "var(--color-text)" }}>{t("settings.memosMigration.applyResult")}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
                  {formatSummaryLines(applied.summary).map((row) => (
                    <div key={row.label} style={{ border: "1px solid var(--color-border)", borderRadius: 12, padding: 10 }}>
                      <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>{row.label}</div>
                      <div style={{ fontSize: 16, fontWeight: 850, color: "var(--color-text)", marginTop: 4 }}>{row.value}</div>
                    </div>
                  ))}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  {t("settings.memosMigration.memosBaseUrlPrefix")}
                  {applied.memos_base_url}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
                  {t("settings.memosMigration.warningsTitle")}：{" "}
                  {applied.warnings?.length ? applied.warnings.join("；") : t("settings.memosMigration.warningsEmpty")}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <section
          style={{
            borderTop: "1px solid var(--color-border)",
            paddingTop: 14,
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ fontSize: 13, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
            {t("settings.offline.title")}
          </div>

          <div
            style={{
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              padding: 14,
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: "var(--color-text)" }}>{t("settings.offline.cardTitle")}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 4 }}>{t("settings.offline.subtitle")}</div>
              </div>

              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 10,
                  border: "1px solid var(--color-border)",
                  borderRadius: 999,
                  padding: "8px 10px",
                  background: "transparent",
                  userSelect: "none",
                  cursor: "pointer",
                }}
              >
                <input
                  data-testid="settings-offline-enabled"
                  type="checkbox"
                  checked={offlineEnabled}
                  onChange={(e) => {
                    updateOfflineEnabled(e.currentTarget.checked);
                  }}
                />
                <span style={{ fontSize: 13, color: "var(--color-text)" }}>{t("settings.offline.toggleLabel")}</span>
              </label>
            </div>

            <div style={{ fontSize: 12, color: "var(--color-text-muted)" }}>
              {t("settings.offline.status.title")}：
              {offlineEnabled ? (
                <>
                  {syncStatus.syncing ? ` ${t("settings.offline.status.syncing")}` : syncStatus.online ? ` ${t("settings.offline.status.online")}` : ` ${t("settings.offline.status.offline")}`}
                  {syncStatus.pending > 0 ? ` · ${t("settings.offline.status.pending")} ${syncStatus.pending}` : ""}
                  {` · ${t("settings.offline.status.lastSync")} ${lastSyncText}`}
                </>
              ) : (
                " 已关闭"
              )}
            </div>

            {offlineEnabled ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
                <button
                  type="button"
                  disabled={manualSyncing}
                  onClick={async () => {
                    setManualSyncing(true);
                    try {
                      await syncNow();
                    } finally {
                      setManualSyncing(false);
                    }
                  }}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "var(--color-surface)",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: manualSyncing ? "not-allowed" : "pointer",
                    opacity: manualSyncing ? 0.7 : 1,
                  }}
                >
                  {manualSyncing ? t("settings.offline.status.syncing") : t("settings.offline.actions.syncNow")}
                </button>

                <button
                  type="button"
                  disabled={clearingOffline}
                  onClick={async () => {
                    if (!window.confirm(t("settings.offline.confirmClearCache"))) return;
                    setClearingOffline(true);
                    try {
                      await resetOfflineDb();
                      await syncNow();
                    } finally {
                      setClearingOffline(false);
                    }
                  }}
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "transparent",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    cursor: clearingOffline ? "not-allowed" : "pointer",
                    opacity: clearingOffline ? 0.7 : 1,
                  }}
                >
                  {clearingOffline ? t("common.loadingDots") : t("settings.offline.actions.clearCache")}
                </button>
              </div>
            ) : null}

            {offlineEnabled && syncStatus.last_error ? (
              <div style={{ fontSize: 12, color: "var(--color-danger)" }}>
                {t("common.error")}：{syncStatus.last_error}
              </div>
            ) : null}
          </div>
        </section>

        {user?.isAdmin ? (
          <section
            style={{
              borderTop: "1px solid var(--color-border)",
              paddingTop: 14,
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ fontSize: 13, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-text-muted)" }}>
              {t("settings.admin.title")}
            </div>

            <div
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
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: "var(--color-text)" }}>{t("settings.admin.title")}</div>
                <div style={{ fontSize: 12, color: "var(--color-text-muted)", marginTop: 4 }}>{t("settings.admin.subtitle")}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
                <Link
                  href="/settings/admin"
                  data-testid="settings-admin-link"
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "var(--color-surface)",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    textDecoration: "none",
                  }}
                >
                  {t("settings.admin.openAppAdmin")}
                </Link>
                <a
                  href="/admin"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-1)",
                    background: "transparent",
                    color: "var(--color-text)",
                    padding: "8px 10px",
                    fontFamily: "var(--font-body)",
                    textDecoration: "none",
                  }}
                >
                  {t("settings.admin.openBackendAdmin")}
                </a>
              </div>
            </div>
          </section>
        ) : null}
      </div>
    </Page>
  );
}

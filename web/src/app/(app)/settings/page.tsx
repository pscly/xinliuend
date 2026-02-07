"use client";

import { useEffect, useMemo, useState } from "react";

import type { MemosMigrationResponse, MemosMigrationSummary } from "@/features/memos/memosMigrationApi";
import { applyMemosMigration, previewMemosMigration } from "@/features/memos/memosMigrationApi";
import { InkButton, InkLink } from "@/features/ui/InkButton";
import { InkCard, InkCardBody, InkCardFooter, InkCardHeader } from "@/features/ui/InkCard";
import { useInkDialog } from "@/features/ui/dialogs/useInkDialog";
import { Page } from "@/features/ui/Page";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";
import { resetOfflineDb } from "@/lib/offline/db";
import { useOfflineEnabled } from "@/lib/offline/useOfflineEnabled";
import type { SyncStatus } from "@/lib/offline/syncEngine";
import { getSyncStatus, subscribeSyncStatus, syncNow } from "@/lib/offline/syncEngine";

import styles from "./SettingsPage.module.css";

export default function SettingsPage() {
  const { user } = useAuth();
  const { locale, t } = useI18n();
  const { confirm } = useInkDialog();
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

  const offlineStatusText = useMemo(() => {
    if (!offlineEnabled) return locale === "zh-CN" ? "已关闭" : "Disabled";
    const onlineText = syncStatus.syncing
      ? t("settings.offline.status.syncing")
      : syncStatus.online
        ? t("settings.offline.status.online")
        : t("settings.offline.status.offline");
    const pending = syncStatus.pending > 0 ? ` · ${t("settings.offline.status.pending")} ${syncStatus.pending}` : "";
    return `${onlineText}${pending} · ${t("settings.offline.status.lastSync")} ${lastSyncText}`;
  }, [lastSyncText, locale, offlineEnabled, syncStatus.online, syncStatus.pending, syncStatus.syncing, t]);

  return (
    <Page titleKey="page.settings.title">
      <div className={styles.content}>
        <section className={styles.section}>
          <div className={styles.sectionTitle}>{t("settings.account.title")}</div>

          <InkCard>
            <InkCardBody className={styles.cardBody}>
              <div className={styles.kvRow}>
                <span className={styles.kvLabel}>{t("settings.account.signedInAs")}</span>
                <span className={styles.kvValue}>{user?.username ?? "-"}</span>
              </div>
              <div className={styles.kvRow}>
                <span className={styles.kvLabel}>{t("settings.account.role")}</span>
                <span className={styles.kvValue}>
                  {user?.isAdmin ? t("settings.account.role.admin") : t("settings.account.role.user")}
                </span>
              </div>
            </InkCardBody>

            <InkCardFooter className={styles.cardFooter}>
              <InkLink href="/settings/password" variant="surface" size="sm">
                {t("settings.account.changePassword")}
              </InkLink>
            </InkCardFooter>
          </InkCard>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionTitle}>{t("settings.memosMigration.title")}</div>

          <InkCard>
            <InkCardHeader
              title={t("settings.memosMigration.cardTitle")}
              subtitle={t("settings.memosMigration.subtitle")}
              right={
                <div className={styles.actions}>
                  <InkButton
                    type="button"
                    data-testid="settings-memos-preview"
                    size="sm"
                    variant="ghost"
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
                  >
                    {busy === "preview" ? t("settings.memosMigration.previewing") : t("settings.memosMigration.preview")}
                  </InkButton>

                  <InkButton
                    type="button"
                    data-testid="settings-memos-apply"
                    size="sm"
                    variant={preview ? "primary" : "surface"}
                    disabled={busy !== null || !preview}
                    onClick={async () => {
                      if (!preview) return;
                      const ok = await confirm({
                        title: t("settings.memosMigration.apply"),
                        message: t("settings.memosMigration.confirmApply"),
                        confirmText: t("settings.memosMigration.apply"),
                      });
                      if (!ok) return;
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
                  >
                    {busy === "apply" ? t("settings.memosMigration.applying") : t("settings.memosMigration.apply")}
                  </InkButton>
                </div>
              }
            />

            <InkCardBody className={styles.cardBody}>
              <div className={styles.hint}>{t("settings.memosMigration.hint")}</div>

              {error ? (
                <div className={styles.error}>
                  {t("settings.memosMigration.errorPrefix")}
                  {error}
                </div>
              ) : null}

              {preview ? (
                <div data-testid="settings-memos-summary" className={styles.resultBlock}>
                  <div className={styles.resultTitle}>{t("settings.memosMigration.previewResult")}</div>
                  <div className={styles.summaryGrid}>
                    {formatSummaryLines(preview.summary).map((row) => (
                      <InkCard key={row.label} variant="surface2">
                        <InkCardBody className={styles.summaryCard}>
                          <div className={styles.summaryLabel}>{row.label}</div>
                          <div className={styles.summaryValue}>{row.value}</div>
                        </InkCardBody>
                      </InkCard>
                    ))}
                  </div>
                  <div className={styles.hint}>
                    {t("settings.memosMigration.memosBaseUrlPrefix")}
                    {preview.memos_base_url}
                  </div>
                  <div className={styles.hint}>
                    {t("settings.memosMigration.warningsTitle")}：{" "}
                    {preview.warnings?.length ? preview.warnings.join("；") : t("settings.memosMigration.warningsEmpty")}
                  </div>
                </div>
              ) : null}

              {applied ? (
                <div className={styles.resultBlock}>
                  <div className={styles.resultTitle}>{t("settings.memosMigration.applyResult")}</div>
                  <div className={styles.summaryGrid}>
                    {formatSummaryLines(applied.summary).map((row) => (
                      <InkCard key={row.label} variant="surface2">
                        <InkCardBody className={styles.summaryCard}>
                          <div className={styles.summaryLabel}>{row.label}</div>
                          <div className={styles.summaryValue}>{row.value}</div>
                        </InkCardBody>
                      </InkCard>
                    ))}
                  </div>
                  <div className={styles.hint}>
                    {t("settings.memosMigration.memosBaseUrlPrefix")}
                    {applied.memos_base_url}
                  </div>
                  <div className={styles.hint}>
                    {t("settings.memosMigration.warningsTitle")}：{" "}
                    {applied.warnings?.length ? applied.warnings.join("；") : t("settings.memosMigration.warningsEmpty")}
                  </div>
                </div>
              ) : null}
            </InkCardBody>
          </InkCard>
        </section>

        <section className={styles.section}>
          <div className={styles.sectionTitle}>{t("settings.offline.title")}</div>

          <InkCard>
            <InkCardHeader
              title={t("settings.offline.cardTitle")}
              subtitle={t("settings.offline.subtitle")}
              right={
                <label className={styles.toggle}>
                  <input
                    data-testid="settings-offline-enabled"
                    type="checkbox"
                    checked={offlineEnabled}
                    onChange={(e) => updateOfflineEnabled(e.currentTarget.checked)}
                  />
                  <span>{t("settings.offline.toggleLabel")}</span>
                </label>
              }
            />

            <InkCardBody className={styles.cardBody}>
              <div className={styles.hint}>
                {t("settings.offline.status.title")}：{offlineStatusText}
              </div>

              {offlineEnabled && syncStatus.last_error ? (
                <div className={styles.error}>
                  {t("common.error")}：{syncStatus.last_error}
                </div>
              ) : null}
            </InkCardBody>

            {offlineEnabled ? (
              <InkCardFooter className={styles.cardFooter}>
                <div className={styles.actions}>
                  <InkButton
                    type="button"
                    size="sm"
                    variant="primary"
                    disabled={manualSyncing}
                    onClick={async () => {
                      setManualSyncing(true);
                      try {
                        await syncNow();
                      } finally {
                        setManualSyncing(false);
                      }
                    }}
                  >
                    {manualSyncing ? t("settings.offline.status.syncing") : t("settings.offline.actions.syncNow")}
                  </InkButton>

                  <InkButton
                    type="button"
                    size="sm"
                    variant="surface"
                    disabled={clearingOffline}
                    onClick={async () => {
                      const ok = await confirm({
                        title: t("settings.offline.actions.clearCache"),
                        message: t("settings.offline.confirmClearCache"),
                        confirmText: t("settings.offline.actions.clearCache"),
                      });
                      if (!ok) return;
                      setClearingOffline(true);
                      try {
                        await resetOfflineDb();
                        await syncNow();
                      } finally {
                        setClearingOffline(false);
                      }
                    }}
                  >
                    {clearingOffline ? t("common.loadingDots") : t("settings.offline.actions.clearCache")}
                  </InkButton>
                </div>
              </InkCardFooter>
            ) : null}
          </InkCard>
        </section>

        {user?.isAdmin ? (
          <section className={styles.section}>
            <div className={styles.sectionTitle}>{t("settings.admin.title")}</div>

            <InkCard>
              <InkCardHeader
                title={t("settings.admin.title")}
                subtitle={t("settings.admin.subtitle")}
                right={
                  <div className={styles.actions}>
                    <InkLink href="/settings/admin" data-testid="settings-admin-link" variant="surface" size="sm">
                      {t("settings.admin.openAppAdmin")}
                    </InkLink>
                    <a href="/admin" target="_blank" rel="noopener noreferrer" className={styles.plainLink}>
                      {t("settings.admin.openBackendAdmin")}
                    </a>
                  </div>
                }
              />
              <InkCardBody className={styles.cardBody}>
                <div className={styles.hint}>{t("page.settings.admin.subtitle")}</div>
              </InkCardBody>
            </InkCard>
          </section>
        ) : null}
      </div>
    </Page>
  );
}

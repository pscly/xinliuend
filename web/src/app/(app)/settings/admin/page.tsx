"use client";

import { InkLink } from "@/features/ui/InkButton";
import { InkCard, InkCardBody, InkCardFooter, InkCardHeader } from "@/features/ui/InkCard";
import { Page } from "@/features/ui/Page";
import { RequireAdmin } from "@/lib/auth/guards";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./SettingsAdminPage.module.css";

export default function SettingsAdminPage() {
  const { t } = useI18n();

  return (
    <RequireAdmin>
      <Page titleKey="page.settings.admin.title" subtitleKey="page.settings.admin.subtitle">
        <div data-testid="settings-admin-page" className={styles.content}>
          <section className={styles.section}>
            <div className={styles.sectionTitle}>{t("settings.admin.title")}</div>

            <InkCard>
              <InkCardHeader title={t("settings.admin.title")} subtitle={t("settings.admin.subtitle")} />
              <InkCardBody className={styles.cardBody}>
                <div className={styles.hint}>{t("settings.admin.page.description")}</div>
              </InkCardBody>
              <InkCardFooter className={styles.cardFooter}>
                <a href="/admin" target="_blank" rel="noopener noreferrer" className={styles.plainLink}>
                  {t("settings.admin.openBackendAdmin")}
                </a>
                <InkLink href="/settings" variant="ghost" size="sm">
                  {t("settings.admin.page.backToSettings")}
                </InkLink>
              </InkCardFooter>
            </InkCard>
          </section>
        </div>
      </Page>
    </RequireAdmin>
  );
}


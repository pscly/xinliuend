"use client";

import Link from "next/link";

import { Page } from "@/features/ui/Page";
import { RequireAdmin } from "@/lib/auth/guards";
import { useI18n } from "@/lib/i18n/useI18n";

export default function SettingsAdminPage() {
  const { t } = useI18n();

  return (
    <RequireAdmin>
      <Page titleKey="page.settings.admin.title" subtitleKey="page.settings.admin.subtitle">
        <div data-testid="settings-admin-page" style={{ padding: "16px 16px 20px", display: "grid", gap: 14 }}>
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
                display: "grid",
                gap: 10,
              }}
            >
              <div style={{ fontSize: 13, color: "var(--color-text-muted)", lineHeight: 1.5 }}>{t("settings.admin.page.description")}</div>

              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <a
                  href="/admin"
                  target="_blank"
                  rel="noopener noreferrer"
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
                  {t("settings.admin.openBackendAdmin")}
                </a>
                <Link
                  href="/settings"
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
                  {t("settings.admin.page.backToSettings")}
                </Link>
              </div>
            </div>
          </section>
        </div>
      </Page>
    </RequireAdmin>
  );
}

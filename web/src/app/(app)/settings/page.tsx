"use client";

import Link from "next/link";

import { Page } from "@/features/ui/Page";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";

export default function SettingsPage() {
  const { user } = useAuth();
  const { t } = useI18n();

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

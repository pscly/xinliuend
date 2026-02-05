"use client";

import Link from "next/link";
import { useCallback, useMemo, useState } from "react";

import { Page } from "@/features/ui/Page";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";

type ChangePasswordResponse = { ok: boolean; csrf_token?: string };

export default function SettingsPasswordPage() {
  const { t } = useI18n();
  const { refreshMe } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPassword2, setNewPassword2] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (currentPassword.length < 1) return false;
    if (newPassword.length < 6) return false;
    if (newPassword2.length < 6) return false;
    if (newPassword !== newPassword2) return false;
    return true;
  }, [currentPassword.length, newPassword, newPassword2, submitting]);

  const submit = useCallback(async () => {
    setError(null);
    setSuccess(null);

    if (newPassword !== newPassword2) {
      setError(t("settings.password.errorMismatch"));
      return;
    }

    setSubmitting(true);
    try {
      const res = await apiFetch("/api/v1/me/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
          new_password2: newPassword2,
        }),
      });

      const json = (await res.json().catch(() => null)) as unknown;

      if (!res.ok) {
        const message =
          typeof (json as any)?.message === "string"
            ? ((json as any).message as string)
            : typeof (json as any)?.detail === "string"
              ? ((json as any).detail as string)
              : null;

        if (res.status === 401) {
          setError(t("settings.password.errorInvalidCurrent"));
          return;
        }

        if (res.status === 400 && message === "password mismatch") {
          setError(t("settings.password.errorMismatch"));
          return;
        }

        if (message) {
          setError(message);
          return;
        }

        setError(`HTTP ${res.status}`);
        return;
      }

      const parsed = json as ChangePasswordResponse;
      if (!parsed || parsed.ok !== true) {
        setError(t("settings.password.errorGeneric"));
        return;
      }

      setCurrentPassword("");
      setNewPassword("");
      setNewPassword2("");
      setSuccess(t("settings.password.success"));

      await refreshMe().catch(() => undefined);
    } catch {
      setError(t("settings.password.errorNetwork"));
    } finally {
      setSubmitting(false);
    }
  }, [currentPassword, newPassword, newPassword2, refreshMe, t]);

  return (
    <Page titleKey="page.settings.password.title" subtitleKey="page.settings.password.subtitle">
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
            {t("settings.password.form.title")}
          </div>

          <div
            style={{
              border: "1px solid var(--color-border)",
              borderRadius: 14,
              background: "var(--color-surface)",
              padding: 14,
              display: "grid",
              gap: 12,
            }}
          >
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("settings.password.current")}</span>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  background: "var(--color-surface)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                }}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("settings.password.new")}</span>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  background: "var(--color-surface)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                }}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 13, color: "var(--color-text-muted)" }}>{t("settings.password.confirm")}</span>
              <input
                type="password"
                value={newPassword2}
                onChange={(e) => setNewPassword2(e.target.value)}
                autoComplete="new-password"
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  background: "var(--color-surface)",
                  color: "var(--color-text)",
                  fontFamily: "var(--font-body)",
                }}
              />
            </label>

            <div style={{ fontSize: 12, color: "var(--color-text-muted)", lineHeight: 1.5 }}>
              {t("settings.password.hint")}
            </div>

            {error ? (
              <div
                style={{
                  border: "1px solid rgba(239, 68, 68, 0.35)",
                  background: "rgba(239, 68, 68, 0.12)",
                  color: "rgba(254, 202, 202, 1)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  fontSize: 13,
                }}
              >
                {error}
              </div>
            ) : null}

            {success ? (
              <div
                style={{
                  border: "1px solid rgba(16, 185, 129, 0.35)",
                  background: "rgba(16, 185, 129, 0.12)",
                  color: "rgba(167, 243, 208, 1)",
                  borderRadius: 12,
                  padding: "10px 12px",
                  fontSize: 13,
                }}
              >
                {success}
              </div>
            ) : null}

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
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
                {t("settings.password.back")}
              </Link>
              <button
                type="button"
                disabled={!canSubmit}
                onClick={submit}
                style={{
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-1)",
                  background: canSubmit ? "var(--color-surface)" : "transparent",
                  color: "var(--color-text)",
                  padding: "8px 10px",
                  fontFamily: "var(--font-body)",
                  opacity: canSubmit ? 1 : 0.6,
                }}
              >
                {submitting ? t("settings.password.submitting") : t("settings.password.submit")}
              </button>
            </div>
          </div>
        </section>
      </div>
    </Page>
  );
}

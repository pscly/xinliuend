"use client";

import { useCallback, useMemo, useState } from "react";

import { InkButton, InkLink } from "@/features/ui/InkButton";
import { InkCard, InkCardBody, InkCardFooter, InkCardHeader } from "@/features/ui/InkCard";
import { InkTextField } from "@/features/ui/InkField";
import { Page } from "@/features/ui/Page";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./SettingsPasswordPage.module.css";

type ChangePasswordResponse = { ok: boolean; csrf_token?: string };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function extractErrorMessage(v: unknown): string | null {
  if (!isRecord(v)) return null;
  const msg = v.message ?? v.detail;
  return typeof msg === "string" && msg.trim() ? msg.trim() : null;
}

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
        const message = extractErrorMessage(json);

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

        setError(`请求失败（HTTP ${res.status}）`);
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
      <div className={styles.content}>
        <section className={styles.section}>
          <div className={styles.sectionTitle}>{t("settings.password.form.title")}</div>

          <InkCard>
            <InkCardHeader title={t("settings.password.form.title")} subtitle={t("settings.password.hint")} />
            <InkCardBody className={styles.cardBody}>
              <InkTextField
                type="password"
                autoComplete="current-password"
                label={t("settings.password.current")}
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
              />

              <InkTextField
                type="password"
                autoComplete="new-password"
                label={t("settings.password.new")}
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />

              <InkTextField
                type="password"
                autoComplete="new-password"
                label={t("settings.password.confirm")}
                value={newPassword2}
                onChange={(e) => setNewPassword2(e.target.value)}
              />

              {error ? <div className={styles.error}>{error}</div> : null}
              {success ? <div className={styles.success}>{success}</div> : null}
            </InkCardBody>

            <InkCardFooter className={styles.cardFooter}>
              <InkLink href="/settings" variant="ghost" size="sm">
                {t("settings.password.back")}
              </InkLink>
              <InkButton type="button" size="sm" variant="primary" disabled={!canSubmit} onClick={submit}>
                {submitting ? t("settings.password.submitting") : t("settings.password.submit")}
              </InkButton>
            </InkCardFooter>
          </InkCard>
        </section>
      </div>
    </Page>
  );
}

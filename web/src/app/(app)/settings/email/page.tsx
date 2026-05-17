"use client";

import { useCallback, useMemo, useState } from "react";

import { InkButton, InkLink } from "@/features/ui/InkButton";
import { InkCard, InkCardBody, InkCardFooter, InkCardHeader } from "@/features/ui/InkCard";
import { InkTextField } from "@/features/ui/InkField";
import { Page } from "@/features/ui/Page";
import { apiFetch } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useI18n } from "@/lib/i18n/useI18n";

import styles from "./SettingsEmailPage.module.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function extractErrorMessage(v: unknown): string | null {
  if (!isRecord(v)) return null;
  const msg = v.message ?? v.detail;
  return typeof msg === "string" && msg.trim() ? msg.trim() : null;
}

export default function SettingsEmailPage() {
  const { t } = useI18n();
  const { user, refreshMe } = useAuth();

  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState<"request" | "confirm" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [codeSent, setCodeSent] = useState(false);
  const [success, setSuccess] = useState(false);

  const canRequest = useMemo(() => {
    return busy !== "request" && EMAIL_RE.test(email.trim());
  }, [busy, email]);

  const canConfirm = useMemo(() => {
    if (busy !== null) return false;
    if (!EMAIL_RE.test(email.trim())) return false;
    return code.trim().length >= 4 && code.trim().length <= 12;
  }, [busy, code, email]);

  const requestCode = useCallback(async () => {
    setError(null);
    setSuccess(false);
    if (!EMAIL_RE.test(email.trim())) {
      setError(t("settings.email.invalidEmail"));
      return;
    }
    setBusy("request");
    try {
      const res = await apiFetch("/api/v1/me/email/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      const json = (await res.json().catch(() => null)) as unknown;
      if (!res.ok) {
        setError(`${t("settings.email.errorPrefix")}${extractErrorMessage(json) ?? `HTTP ${res.status}`}`);
        return;
      }
      setCodeSent(true);
    } catch (e) {
      setError(`${t("settings.email.errorPrefix")}${e instanceof Error ? e.message : ""}`);
    } finally {
      setBusy(null);
    }
  }, [email, t]);

  const confirmCode = useCallback(async () => {
    setError(null);
    setSuccess(false);
    if (!EMAIL_RE.test(email.trim())) {
      setError(t("settings.email.invalidEmail"));
      return;
    }
    setBusy("confirm");
    try {
      const res = await apiFetch("/api/v1/me/email/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim(), code: code.trim() }),
      });
      const json = (await res.json().catch(() => null)) as unknown;
      if (!res.ok) {
        setError(`${t("settings.email.errorPrefix")}${extractErrorMessage(json) ?? `HTTP ${res.status}`}`);
        return;
      }
      setSuccess(true);
      setCode("");
      setCodeSent(false);
      await refreshMe().catch(() => undefined);
    } catch (e) {
      setError(`${t("settings.email.errorPrefix")}${e instanceof Error ? e.message : ""}`);
    } finally {
      setBusy(null);
    }
  }, [code, email, refreshMe, t]);

  const currentEmail = user?.email ?? null;
  const isVerified = Boolean(user?.emailVerified);

  return (
    <Page titleKey="page.settings.email.title" subtitleKey="page.settings.email.subtitle">
      <div className={styles.content}>
        <section className={styles.section}>
          <InkCard>
            <InkCardBody className={styles.cardBody}>
              <div className={styles.kvRow}>
                <span className={styles.kvLabel}>{t("settings.email.currentLabel")}</span>
                {currentEmail ? (
                  <span className={styles.kvValue}>
                    {t("settings.email.boundPrefix")}
                    <code className={styles.codeText}>{currentEmail}</code>
                    {" "}
                    {isVerified ? (
                      <span className={styles.badgeOk}>{t("settings.email.verifiedBadge")}</span>
                    ) : (
                      <span className={styles.badgeWarn}>{t("settings.email.unverifiedBadge")}</span>
                    )}
                  </span>
                ) : (
                  <span className={styles.kvValue}>{t("settings.email.notBound")}</span>
                )}
              </div>
            </InkCardBody>
          </InkCard>
        </section>

        <section className={styles.section}>
          <InkCard>
            <InkCardHeader title={t("settings.email.requestCard.title")} subtitle={t("settings.email.requestCard.subtitle")} />
            <InkCardBody className={styles.cardBody}>
              <InkTextField
                type="email"
                inputMode="email"
                autoComplete="email"
                label={t("settings.email.input.label")}
                placeholder={t("settings.email.input.placeholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              {codeSent ? <div className={styles.success}>{t("settings.email.codeSent")}</div> : null}
            </InkCardBody>
            <InkCardFooter className={styles.cardFooter}>
              <InkButton
                type="button"
                size="sm"
                variant="primary"
                disabled={!canRequest}
                onClick={requestCode}
              >
                {busy === "request" ? t("settings.email.requestSubmitting") : t("settings.email.requestSubmit")}
              </InkButton>
            </InkCardFooter>
          </InkCard>
        </section>

        <section className={styles.section}>
          <InkCard>
            <InkCardHeader title={t("settings.email.confirmCard.title")} subtitle={t("settings.email.confirmCard.subtitle")} />
            <InkCardBody className={styles.cardBody}>
              <InkTextField
                inputMode="numeric"
                autoComplete="one-time-code"
                label={t("settings.email.codeLabel")}
                placeholder={t("settings.email.codePlaceholder")}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
              {error ? <div className={styles.error}>{error}</div> : null}
              {success ? <div className={styles.success}>{t("settings.email.success")}</div> : null}
            </InkCardBody>
            <InkCardFooter className={styles.cardFooter}>
              <InkLink href="/settings" variant="ghost" size="sm">
                {t("settings.email.back")}
              </InkLink>
              <InkButton
                type="button"
                size="sm"
                variant="primary"
                disabled={!canConfirm}
                onClick={confirmCode}
              >
                {busy === "confirm" ? t("settings.email.confirmSubmitting") : t("settings.email.confirmSubmit")}
              </InkButton>
            </InkCardFooter>
          </InkCard>
        </section>
      </div>
    </Page>
  );
}

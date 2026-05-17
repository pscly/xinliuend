"use client";

import type { FormEvent } from "react";
import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

import { useI18n } from "@/lib/i18n/useI18n";
import { RedirectIfAuthenticated } from "@/lib/auth/guards";

import styles from "./ResetPasswordPage.module.css";

type ResetResponseOk = { ok: boolean; memos_sync_warning?: string | null };

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function extractErrorMessage(v: unknown): string | null {
  if (!isRecord(v)) return null;
  const msg = v.message ?? v.detail;
  return typeof msg === "string" && msg.trim() ? msg.trim() : null;
}

export default function ResetPasswordPage() {
  // useSearchParams must live inside a Suspense boundary for static export.
  return (
    <Suspense fallback={null}>
      <ResetPasswordPageInner />
    </Suspense>
  );
}

function ResetPasswordPageInner() {
  const { t } = useI18n();
  const search = useSearchParams();
  // Persist the token on mount so query-param removal mid-flow doesn't break submit.
  const [token, setToken] = useState<string>("");
  useEffect(() => {
    const tk = (search?.get("token") || "").trim();
    setToken(tk);
  }, [search]);

  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    if (submitting) return false;
    if (!token) return false;
    if (password.length < 6 || password2.length < 6) return false;
    return password === password2;
  }, [password, password2, submitting, token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setWarning(null);

    if (password !== password2) {
      setError(t("page.reset.errorMismatch"));
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          new_password: password,
          new_password2: password2,
        }),
        credentials: "include",
      });
      const json = (await res.json().catch(() => null)) as unknown;
      if (!res.ok) {
        if (res.status === 400) {
          const msg = extractErrorMessage(json);
          setError(msg || t("page.reset.errorInvalidLink"));
        } else {
          setError(t("page.reset.errorGeneric"));
        }
        return;
      }
      const data = json as ResetResponseOk;
      if (!data || data.ok !== true) {
        setError(t("page.reset.errorGeneric"));
        return;
      }
      setDone(true);
      if (typeof data.memos_sync_warning === "string" && data.memos_sync_warning) {
        setWarning(data.memos_sync_warning);
      }
    } catch {
      setError(t("page.reset.errorGeneric"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <RedirectIfAuthenticated>
      <div className={styles.wrap}>
        <main className={styles.main}>
          <section className={styles.card}>
            <div className={styles.cardInner}>
              <h1 className={styles.title}>{t("page.reset.title")}</h1>
              <p className={styles.subtitle}>{t("page.reset.subtitle")}</p>
            </div>

            {done ? (
              <div className={styles.body}>
                <div className={styles.success}>{t("page.reset.successHint")}</div>
                {warning ? (
                  <div className={styles.warning}>
                    {t("page.reset.memosSyncWarningPrefix")}
                    {warning}
                  </div>
                ) : null}
                <Link href="/login" className={styles.primaryLink}>
                  {t("page.reset.goLogin")} →
                </Link>
              </div>
            ) : !token ? (
              <div className={styles.body}>
                <div className={styles.error}>{t("page.reset.missingToken")}</div>
                <Link href="/forgot-password" className={styles.primaryLink}>
                  → {t("page.forgot.title")}
                </Link>
              </div>
            ) : (
              <form className={styles.form} onSubmit={onSubmit}>
                <label className={styles.field}>
                  <span className={styles.label}>{t("page.reset.newPasswordLabel")}</span>
                  <input
                    className={styles.input}
                    type="password"
                    autoComplete="new-password"
                    minLength={6}
                    maxLength={72}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </label>

                <label className={styles.field}>
                  <span className={styles.label}>{t("page.reset.confirmPasswordLabel")}</span>
                  <input
                    className={styles.input}
                    type="password"
                    autoComplete="new-password"
                    minLength={6}
                    maxLength={72}
                    value={password2}
                    onChange={(e) => setPassword2(e.target.value)}
                  />
                </label>

                {error ? <div className={styles.error}>{error}</div> : null}

                <button type="submit" className={styles.submit} disabled={!canSubmit}>
                  {submitting ? t("page.reset.submitting") : t("page.reset.submit")}
                </button>

                <div className={styles.helperRow}>
                  <Link href="/login" className={styles.helperLink}>
                    ← {t("page.forgot.backToLogin")}
                  </Link>
                </div>
              </form>
            )}
          </section>
        </main>
      </div>
    </RedirectIfAuthenticated>
  );
}

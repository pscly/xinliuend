"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import Link from "next/link";

import { useI18n } from "@/lib/i18n/useI18n";
import { RedirectIfAuthenticated } from "@/lib/auth/guards";

import styles from "./ForgotPasswordPage.module.css";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ForgotPasswordPage() {
  const { t } = useI18n();

  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    const trimmed = email.trim();
    if (!EMAIL_RE.test(trimmed)) {
      setError(t("page.forgot.invalidEmail"));
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/v1/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmed }),
        credentials: "include",
      });
      // Always treat any non-network response as success — the backend
      // intentionally returns the same body even when the email isn't
      // registered (anti-enumeration). Only fall through to error UI on a
      // hard network failure.
      void res;
      setDone(true);
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
              <h1 className={styles.title}>{t("page.forgot.title")}</h1>
              <p className={styles.subtitle}>{t("page.forgot.subtitle")}</p>
            </div>

            {done ? (
              <div className={styles.body}>
                <div className={styles.success}>{t("page.forgot.successHint")}</div>
                <Link href="/login" className={styles.backLink}>
                  ← {t("page.forgot.backToLogin")}
                </Link>
              </div>
            ) : (
              <form className={styles.form} onSubmit={onSubmit}>
                <label className={styles.field}>
                  <span className={styles.label}>{t("page.forgot.emailLabel")}</span>
                  <input
                    className={styles.input}
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    value={email}
                    placeholder={t("page.forgot.emailPlaceholder")}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>

                {error ? <div className={styles.error}>{error}</div> : null}

                <button
                  type="submit"
                  className={styles.submit}
                  disabled={submitting || email.trim().length === 0}
                >
                  {submitting ? t("page.forgot.submitting") : t("page.forgot.submit")}
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

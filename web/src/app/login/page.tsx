"use client";

import type { FormEvent } from "react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { useI18n } from "@/lib/i18n/useI18n";
import type { MessageKey } from "@/lib/i18n/messages";
import { useTheme } from "@/lib/theme/ThemeProvider";
import { nextThemePalette, nextThemePreference, type ThemePalette } from "@/lib/theme/theme";
import { useAuth } from "@/lib/auth/useAuth";
import { RedirectIfAuthenticated } from "@/lib/auth/guards";

import styles from "./LoginPage.module.css";

const USERNAME_RE = /^[A-Za-z0-9]+$/;

function themeLabelKey(preference: "system" | "light" | "dark") {
  if (preference === "light") return "ui.theme.light";
  if (preference === "dark") return "ui.theme.dark";
  return "ui.theme.system";
}

function paletteLabelKey(palette: ThemePalette) {
  if (palette === "indigo") return "ui.palette.indigo";
  if (palette === "cyber") return "ui.palette.cyber";
  return "ui.palette.paperInk";
}

function validateUsername(username: string): MessageKey | null {
  const v = username.trim();
  if (v.length < 1 || v.length > 64) return "auth.username.error";
  if (!USERNAME_RE.test(v)) return "auth.username.error";
  return null;
}

export default function LoginPage() {
  const router = useRouter();
  const { t } = useI18n();
  const { palette, preference, setPalette, setPreference } = useTheme();
  const { login } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorKey, setErrorKey] = useState<MessageKey | null>(null);

  const usernameErrorKey = useMemo(() => validateUsername(username), [username]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErrorKey(null);

    const validationError = validateUsername(username);
    if (validationError) {
      setErrorKey(validationError);
      return;
    }

    setSubmitting(true);
    try {
      await login(username.trim(), password);
      router.replace("/");
    } catch {
      setErrorKey("auth.login.error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <RedirectIfAuthenticated>
      <div className={styles.wrap}>
        <header className={styles.header}>
          <div className={styles.brand}>
            <img
              className={styles.brandMark}
              src="/icon-192.png"
              alt=""
              aria-hidden="true"
              draggable={false}
              decoding="async"
            />
            <div className={styles.brandName}>{t("app.name")}</div>
          </div>
          <div className={styles.controls}>
            <button
              type="button"
              className={styles.pill}
              onClick={() => setPreference(nextThemePreference(preference))}
              aria-label={`${t("ui.theme")}: ${t(themeLabelKey(preference))}`}
            >
              <span className={styles.pillLabel}>{t("ui.theme")}</span>
              <span className={styles.pillValue}>{t(themeLabelKey(preference))}</span>
            </button>

            <button
              type="button"
              className={styles.pill}
              onClick={() => setPalette(nextThemePalette(palette))}
              aria-label={`${t("ui.palette")}: ${t(paletteLabelKey(palette))}`}
            >
              <span className={styles.pillLabel}>{t("ui.palette")}</span>
              <span className={styles.pillValue}>{t(paletteLabelKey(palette))}</span>
            </button>
          </div>
        </header>

        <main className={styles.main}>
          <section className={styles.card}>
            <div className={styles.cardInner}>
              <h1 className={styles.title}>{t("page.login.title")}</h1>
              <p className={styles.subtitle}>{t("page.login.subtitle")}</p>
            </div>

            <form className={styles.form} onSubmit={onSubmit}>
              <label className={styles.field}>
                <span className={styles.label}>{t("auth.username")}</span>
                <input
                  className={styles.input}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  inputMode="text"
                  autoComplete="username"
                  maxLength={64}
                  aria-invalid={Boolean(usernameErrorKey) || undefined}
                />
                <span className={styles.help}>{t("auth.username.help")}</span>
              </label>

              <label className={styles.field}>
                <span className={styles.label}>{t("auth.password")}</span>
                <input
                  className={styles.input}
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  maxLength={72}
                />
              </label>

              {errorKey ? <div className={styles.error}>{t(errorKey)}</div> : null}

              <button
                type="submit"
                className={styles.submit}
                disabled={submitting || Boolean(usernameErrorKey) || password.length < 1}
              >
                {t("auth.login")}
              </button>
            </form>
          </section>
        </main>
      </div>
    </RedirectIfAuthenticated>
  );
}

"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useEffect, useMemo, useState } from "react";

import type { MessageKey } from "./messages";
import { MESSAGES_BY_LOCALE } from "./messages";
import { LOCALE_STORAGE_KEY, normalizeLocale, type AppLocale } from "./locales";

type I18nContextValue = {
  locale: AppLocale;
  setLocale: (next: AppLocale) => void;
  t: (key: MessageKey) => string;
};

export const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<AppLocale>(() => {
    if (typeof window === "undefined") return "zh-CN";
    const storedRaw = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    // 默认中文：避免浏览器语言为英文时导致整个站点首次打开全是英文。
    return storedRaw ? normalizeLocale(storedRaw) : "zh-CN";
  });

  useEffect(() => {
    document.documentElement.lang = locale;
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  }, [locale]);

  const t = useCallback(
    (key: MessageKey) => {
      const messages = MESSAGES_BY_LOCALE[locale];
      return messages[key] ?? key;
    },
    [locale]
  );

  const setLocale = useCallback((next: AppLocale) => {
    setLocaleState(next);
  }, []);

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

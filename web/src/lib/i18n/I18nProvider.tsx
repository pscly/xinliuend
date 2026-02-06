"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useEffect, useMemo } from "react";

import type { MessageKey } from "./messages";
import { MESSAGES_BY_LOCALE } from "./messages";
import type { AppLocale } from "./locales";

type I18nContextValue = {
  locale: AppLocale;
  setLocale: (next: AppLocale) => void;
  t: (key: MessageKey) => string;
};

export const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  // 语言策略：强制中文（避免出现英文 UI）。
  const locale: AppLocale = "zh-CN";

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: MessageKey) => {
      const messages = MESSAGES_BY_LOCALE[locale];
      return messages[key] ?? key;
    },
    [locale]
  );

  const setLocale = useCallback((next: AppLocale) => {
    // 强制中文：保留 API 以兼容旧组件，但不允许切换。
    void next;
  }, []);

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

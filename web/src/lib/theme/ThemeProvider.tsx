"use client";

import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { PALETTE_STORAGE_KEY, THEME_STORAGE_KEY, type ThemePalette, type ThemePreference } from "./theme";

type ThemeContextValue = {
  preference: ThemePreference;
  setPreference: (next: ThemePreference) => void;
  palette: ThemePalette;
  setPalette: (next: ThemePalette) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

function applyThemePreference(preference: ThemePreference) {
  const root = document.documentElement;
  if (preference === "system") {
    root.removeAttribute("data-theme");
    return;
  }
  root.setAttribute("data-theme", preference);
}

function applyThemePalette(palette: ThemePalette) {
  document.documentElement.setAttribute("data-palette", palette);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => {
    if (typeof window === "undefined") return "system";
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY);
    return raw === "light" || raw === "dark" || raw === "system" ? raw : "system";
  });

  const [palette, setPaletteState] = useState<ThemePalette>(() => {
    if (typeof window === "undefined") return "paper-ink";
    const raw = window.localStorage.getItem(PALETTE_STORAGE_KEY);
    return raw === "paper-ink" || raw === "indigo" || raw === "cyber" ? raw : "paper-ink";
  });

  useEffect(() => {
    applyThemePreference(preference);
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  }, [preference]);

  useEffect(() => {
    applyThemePalette(palette);
    window.localStorage.setItem(PALETTE_STORAGE_KEY, palette);
  }, [palette]);

  const setPreference = useCallback((next: ThemePreference) => {
    setPreferenceState(next);
  }, []);

  const setPalette = useCallback((next: ThemePalette) => {
    setPaletteState(next);
  }, []);

  const value = useMemo(() => ({ preference, setPreference, palette, setPalette }), [palette, preference, setPalette, setPreference]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme 必须在 ThemeProvider 内使用");
  }
  return ctx;
}

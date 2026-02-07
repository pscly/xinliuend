export type ThemePreference = "system" | "light" | "dark";

export const THEME_STORAGE_KEY = "theme-preference";

export const THEME_PREFERENCES: readonly ThemePreference[] = [
  "system",
  "light",
  "dark",
] as const;

export function nextThemePreference(current: ThemePreference): ThemePreference {
  if (current === "system") return "light";
  if (current === "light") return "dark";
  return "system";
}

export type ThemePalette = "paper-ink" | "indigo" | "cyber";

export const PALETTE_STORAGE_KEY = "theme-palette";

export const THEME_PALETTES: readonly ThemePalette[] = [
  "paper-ink",
  "indigo",
  "cyber",
] as const;

export function nextThemePalette(current: ThemePalette): ThemePalette {
  if (current === "paper-ink") return "indigo";
  if (current === "indigo") return "cyber";
  return "paper-ink";
}

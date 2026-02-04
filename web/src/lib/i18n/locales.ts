export type AppLocale = "zh-CN" | "en";

export const SUPPORTED_LOCALES: readonly AppLocale[] = ["zh-CN", "en"] as const;

export const LOCALE_STORAGE_KEY = "locale";

export function normalizeLocale(input: string | null | undefined): AppLocale {
  if (!input) return "zh-CN";
  const lowered = input.toLowerCase();
  if (lowered.startsWith("zh")) return "zh-CN";
  return "en";
}

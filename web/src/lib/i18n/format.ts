import type { AppLocale } from "./locales";

export function createDateTimeFormatter(locale: AppLocale, options?: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat(locale, options);
}

export function createRelativeTimeFormatter(locale: AppLocale, options?: Intl.RelativeTimeFormatOptions) {
  return new Intl.RelativeTimeFormat(locale, options);
}

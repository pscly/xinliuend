// Design tokens backed by CSS variables defined in web/src/app/globals.css.

type CssVarRef = `var(--${string})`;

export const TOKENS = {
  "colors.bg": "var(--color-bg)",
  "colors.surface": "var(--color-surface)",
  "colors.surface2": "var(--color-surface-2)",
  "colors.text": "var(--color-text)",
  "colors.textMuted": "var(--color-text-muted)",
  "colors.border": "var(--color-border)",
  "colors.accent": "var(--color-accent)",
  "colors.accentContrast": "var(--color-accent-contrast)",
  "colors.accent2": "var(--color-accent-2)",
  "colors.accentGold": "var(--color-accent-gold)",
} as const satisfies Record<string, CssVarRef>;

export type TokenKey = keyof typeof TOKENS;
export type TokenValue = (typeof TOKENS)[TokenKey];

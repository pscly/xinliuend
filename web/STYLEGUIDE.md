# Frontend Style Guide (Qinglu)

This project aims for a Guofeng Qinglu (qinglu landscape painting) feel: mineral greens/azurites, warm paper, and a restrained gold accent. The UI should read like ink on paper in day mode, and like moonlit ink washes in night mode.

Keep this practical: use the existing CSS variables and patterns; avoid hardcoded colors.

## Visual Direction

- Day (baseline): warm paper background, soft stone surfaces, ink text, jade as primary accent.
- Night (variant): ink-black base with green/azurite undertones, subtle gold, low-glare surfaces.
- Texture: paper grain + fibers + wash layers are part of the brand. Do not replace with flat backgrounds.

## Design Tokens (CSS Variables)

Source of truth: `web/src/app/globals.css`.

### Typography

- `--font-body`: body text stack (serif-first, CN-friendly).
- `--font-display`: display/brand stack (same stack, used for headings/brand).

### Layout + Shape

- `--page-max`: max content width (currently 1100px).
- `--radius-1`: default radius for controls/pills (currently 12px).
- `--radius-2`: larger radius for cards/panels (currently 14px).
- `--shadow-1`: primary elevation shadow (use sparingly).

### Core Colors (use these in components)

- `--color-bg`: app background.
- `--color-surface`: primary surface (cards, headers, panels).
- `--color-surface-2`: secondary surface (sub-panels, grouped sections).
- `--color-text`: main text.
- `--color-text-muted`: secondary text.
- `--color-border`: hairline borders and dividers.
- `--color-accent`: primary accent (jade in day, moonlit jade in night by default).
- `--color-accent-contrast`: text/icon color when placed on `--color-accent`.

Optional accents (use intentionally, not everywhere):

- `--color-accent-2`: secondary accent (azurite).
- `--color-accent-gold`: gold highlight for selected states and ornaments.

### Background Layers (brand atmosphere)

- `--bg-paper-grain`: subtle grain.
- `--bg-paper-fibers`: repeating fiber pattern.
- `--bg-wash-1`, `--bg-wash-2`, `--bg-wash-3`: qinglu wash glows.

### Loading

- `--skeleton-1`, `--skeleton-2`: used by `.skeleton` shimmer.

## Themes

Themes are defined in `web/src/app/globals.css`:

- System default: `@media (prefers-color-scheme: dark)` overrides tokens.
- Manual override: `html[data-theme="light"]` and `html[data-theme="dark"]`.

Guideline: components should consume tokens only (the `--color-*` and `--bg-*` layer tokens), not the raw palette (`--qinglu-*`) unless you are adjusting the theme system itself.

## Typography Guidance (CN/EN)

- Use `--font-body` for most UI copy.
- Use `--font-display` for brand and key headings.
- Avoid ultra-tight tracking for CN; it harms readability. Keep letter-spacing subtle.

Handling long English strings (route names, IDs, URLs):

- Prefer flexible layouts: ensure flex children can shrink (`min-width: 0`) and allow wrapping where appropriate.
- For labels that must stay one line (nav pills, compact headers): use ellipsis (e.g. `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`).
- For content text that can wrap: allow breaking (e.g. `overflow-wrap: anywhere; word-break: break-word;`).
- If you enable hyphenation, do it only where `lang="en"` is set and test on mobile.

## Spacing, Radius, and Shadow

Spacing (current reality from `web/src/features/shell/AppShell.module.css`):

- Header padding: 16px.
- Common gaps: 10px and 12px.
- Main content padding: 26px 16px 40px.
- Pill heights: 34px (nav links) and 36px (controls).

Conventions:

- Use a 4px grid for spacing decisions (8/12/16/24/32/40 are the common stops).
- Use `--radius-1` for pills/inputs/buttons; use `--radius-2` for cards and panels.
- Use `--shadow-1` only for elevated layers (modal/popup/spotlight card). Prefer borders and subtle gradients for depth.

## Component Usage Notes

### Header

Current shell behavior in `web/src/features/shell/AppShell.module.css`:

- Sticky header (`position: sticky; top: 0`) with blur (`backdrop-filter: blur(10px)`).
- Translucent background using `color-mix(in srgb, var(--color-bg) 72%, transparent)`.
- Bottom border uses `--color-border`.

Guideline:

- Keep the header light and readable; do not introduce heavy shadows.
- Avoid tall header variants; keep vertical rhythm stable across routes.

### Navigation (pills)

- Use pill-shaped links with subtle gradients for hover/active, never solid neon fills.
- Default state: muted text (`--color-text-muted`).
- Hover/active: bring text to `--color-text`, add border tint toward `--color-accent-gold`.
- Motion should match current transitions (160-180ms) and remain low-amplitude.

### Pills (controls)

- Use `--color-surface` mixed with transparency for the fill, `--color-border` for the stroke.
- Keep pill copy short; prefer icons plus short labels.

### Cards

Recommended default card recipe (adapt per route):

- Background: `--color-surface`.
- Border: 1px solid `--color-border`.
- Radius: `--radius-2`.
- Optional decoration: a faint wash using `--color-accent` or `--color-accent-2` at low opacity.
- Shadow: only when the card is in a floating context; otherwise no shadow.

## Accessibility

- Focus: use the global `:focus-visible` ring (2px `--color-accent` with 2px offset). Do not remove it.
- Contrast: ensure `--color-text` on `--color-bg`/`--color-surface` stays readable in both themes. If you introduce new surfaces, test day and night.
- Accent usage: when placing text/icons on `--color-accent`, use `--color-accent-contrast`.
- Hit targets: interactive pills should remain >= 34px tall (already true in the shell).

## Motion Guidelines

Allowed:

- Hover/focus transitions for color/border/background/box-shadow (160-220ms ease).
- Enter transitions for route-level elements: subtle fade + small translate (6-10px) and short duration.
- Loading shimmer: `.skeleton` animation is allowed for placeholders.

Avoid:

- Continuous decorative motion (backgrounds that constantly move) and aggressive springy animations.
- Large parallax, long-running keyframes, or animation that competes with reading.

Respect reduced motion:

- When adding new animations, wrap in `@media (prefers-reduced-motion: reduce)` to disable or simplify.

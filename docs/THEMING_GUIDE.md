# Web-Next Theming Guide

This document describes how global themes work in `web-next`, which themes are currently available, and how to add or modify themes safely.

## 1. Current Themes

Defined in `web-next/lib/theme-registry.ts`:

- `venom-dark` (default)
- `venom-light`

Legacy alias (runtime migration only):
- `venom-light-dev` -> `venom-light`

## 2. Architecture Overview

Core files:

- `web-next/lib/theme-registry.ts`
  - Theme IDs (`ThemeId`)
  - Theme metadata (`THEME_REGISTRY`)
  - Legacy alias map (`LEGACY_THEME_ALIASES`)
  - Fallback (`DEFAULT_THEME`)
- `web-next/lib/theme.tsx`
  - `ThemeProvider`, `useTheme`
  - Source priority:
    - `localStorage["venom-theme"]`
    - backend `UI_THEME_DEFAULT` from `/api/v1/config/runtime`
    - `DEFAULT_THEME`
  - Legacy value normalization:
    - localStorage `venom-light-dev` is rewritten to `venom-light`
    - backend `UI_THEME_DEFAULT=venom-light-dev` is normalized to `venom-light`
  - Best-effort backend sync on change
- `web-next/app/layout.tsx`
  - Bootstraps `html[data-theme]` before hydration (reduces FOUC)
- `web-next/app/globals.css`
  - Base semantic tokens in `:root`
  - Per-theme overrides in `html[data-theme="<id>"]`
  - Legacy utility compatibility layer removed from visual CSS contract
- `web-next/components/layout/theme-switcher.tsx`
  - Global selector UI in TopBar
- `web-next/lib/i18n/locales/{pl,en,de}.ts`
  - Theme label/description keys for UI

## 3. How to Add a New Theme

1. Add the theme ID in `web-next/lib/theme-registry.ts`:
   - add `<id>` to `THEME_REGISTRY`
   - add translation key, e.g. `theme.options.<newTheme>`
2. Add CSS token overrides in `web-next/app/globals.css`:
   - create block: `html[data-theme="<id>"] { ... }`
   - override only semantic tokens (`--text-primary`, `--ui-border`, `--ui-surface`, etc.)
3. Add i18n labels and descriptions in all locales:
   - `web-next/lib/i18n/locales/pl.ts`
   - `web-next/lib/i18n/locales/en.ts`
   - `web-next/lib/i18n/locales/de.ts`
4. Validate tests:
   - `web-next/tests/theme-registry.test.ts`
   - `web-next/tests/theme-i18n-keys.test.ts`
   - `web-next/tests/theme-provider.component.test.tsx`
   - `web-next/tests/theme-switcher.component.test.tsx`
5. Run frontend checks:
   - `cd web-next && npm run lint`
   - `cd web-next && npm run test:unit:components`

## 4. How to Modify Existing Themes

When adjusting an existing theme:

1. Change only token values in `web-next/app/globals.css` unless behavior must change.
2. Avoid hardcoded colors in components. Prefer semantic variables (`var(--...)`).
3. Keep contrast at accessible levels (especially text vs surface and button states).
4. Verify both themes in key views:
   - Cockpit (`/`)
   - Models (`/models`)
   - Academy (`/academy`)
   - Config (`/config`)
5. Re-run unit/component tests after visual token changes.
6. Keep stabilization guards green:
   - no `dark:` usage in `web-next/components` and `web-next/app`,
   - no `venom-light-dev` selector in `web-next/app/globals.css`,
   - no transitional compatibility layer for legacy utility classes.

## 5. Recommended Token Scope

Prefer theme-safe semantic tokens:

- Text: `--text-primary`, `--text-secondary`, `--text-heading`, `--ui-muted`
- Surfaces: `--bg-base`, `--bg-panel`, `--ui-surface`, `--surface-muted`, `--surface-overlay-*`
- Borders: `--ui-border`, `--ui-border-strong`, `--border-glass`
- Actions: `--primary`, `--secondary`, button token set
- Status tones: `--tone-success-*`, `--tone-warning-*`, `--tone-danger-*`, `--tone-info-*`, `--tone-neutral-*`
- Effects: `--shadow-card`, `--app-shell-radial`, `--noise-image`

Avoid introducing component-specific hardcoded palettes when an existing token can be reused.

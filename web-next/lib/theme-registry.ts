export const THEME_STORAGE_KEY = "venom-theme";
export const DEFAULT_THEME = "venom-dark" as const;

export const THEME_REGISTRY = {
  "venom-dark": {
    id: "venom-dark",
    translationKey: "theme.options.venomDark",
  },
  "venom-light": {
    id: "venom-light",
    translationKey: "theme.options.venomLight",
  },
} as const;

export type ThemeId = keyof typeof THEME_REGISTRY;
export const THEME_IDS = Object.keys(THEME_REGISTRY) as ThemeId[];
export const LEGACY_THEME_ALIASES = {
  "venom-light-dev": "venom-light",
} as const;

export function isThemeId(value: string | null | undefined): value is ThemeId {
  if (!value) return false;
  return value in THEME_REGISTRY;
}

export function resolveThemeId(value: string | null | undefined): ThemeId | null {
  if (!value) return null;
  if (isThemeId(value)) return value;
  const alias = LEGACY_THEME_ALIASES[value as keyof typeof LEGACY_THEME_ALIASES];
  return alias ?? null;
}

export function normalizeTheme(value: string | null | undefined): ThemeId {
  const resolved = resolveThemeId(value);
  if (resolved) return resolved;
  return DEFAULT_THEME;
}

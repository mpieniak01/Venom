export const THEME_STORAGE_KEY = "venom-theme";
export const DEFAULT_THEME = "venom-dark" as const;

export const THEME_REGISTRY = {
  "venom-dark": {
    id: "venom-dark",
    translationKey: "theme.options.venomDark",
  },
  "venom-light-dev": {
    id: "venom-light-dev",
    translationKey: "theme.options.venomLightDev",
  },
} as const;

export type ThemeId = keyof typeof THEME_REGISTRY;
export const THEME_IDS = Object.keys(THEME_REGISTRY) as ThemeId[];

export function isThemeId(value: string | null | undefined): value is ThemeId {
  if (!value) return false;
  return value in THEME_REGISTRY;
}

export function normalizeTheme(value: string | null | undefined): ThemeId {
  if (isThemeId(value)) return value;
  return DEFAULT_THEME;
}

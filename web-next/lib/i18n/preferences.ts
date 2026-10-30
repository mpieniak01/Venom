export const LANGUAGE_STORAGE_KEY = "venom-language";
export const LANGUAGE_COOKIE = "venom-language";
export type LanguageCode = "pl" | "en" | "de";
export type LocaleDictionary = Record<string, unknown>;

export function isLanguageCode(value: unknown): value is LanguageCode {
  return value === "pl" || value === "en" || value === "de";
}

export function languageFromCookie(cookie: string): LanguageCode | null {
  const entry = cookie.split(";").map((part) => part.trim()).find((part) =>
    part.startsWith(`${LANGUAGE_COOKIE}=`),
  );
  const value = entry?.slice(LANGUAGE_COOKIE.length + 1);
  return isLanguageCode(value) ? value : null;
}

export function languageFromHeader(header: string | null): LanguageCode {
  for (const entry of (header ?? "").split(",")) {
    const [tag, ...parameters] = entry.trim().split(";");
    if (parameters.some((parameter) => /^q=0(?:\.0*)?$/.test(parameter.trim()))) continue;
    const language = tag.slice(0, 2).toLowerCase();
    if (isLanguageCode(language)) return language;
  }
  return "pl";
}

import type { LanguageCode, LocaleDictionary } from "./preferences";

// Explicit imports let the bundler isolate every dictionary; importing a barrel
// or all locales here would put the original cost back on every route.
export async function loadDateLocale(language: LanguageCode): Promise<void> {
  if (language === "en") await import("dayjs/locale/en");
  else if (language === "de") await import("dayjs/locale/de");
  else await import("dayjs/locale/pl");
}

export async function loadLocale(language: LanguageCode): Promise<LocaleDictionary> {
  await loadDateLocale(language);
  switch (language) {
    case "en":
      return (await import("./locales/en")).en;
    case "de":
      return (await import("./locales/de")).de;
    default:
      return (await import("./locales/pl")).pl;
  }
}

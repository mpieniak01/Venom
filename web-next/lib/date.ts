function resolveLanguageFromStorage(): keyof typeof DATE_LOCALES {
  if (typeof window === "undefined") return "pl";
  const stored = window.localStorage.getItem("venom-language");
  if (stored === "en" || stored === "de" || stored === "pl") {
    return stored;
  }
  return "pl";
}

export function formatRelativeTime(value?: string | null): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;

  const diffMs = Date.now() - target.getTime();
  const absSeconds = Math.max(1, Math.floor(Math.abs(diffMs) / 1000));

  let unit: Intl.RelativeTimeFormatUnit = "second";
  let amount = absSeconds;
  if (absSeconds >= 60) {
    const minutes = Math.floor(absSeconds / 60);
    if (minutes < 60) {
      unit = "minute";
      amount = minutes;
    } else {
      const hours = Math.floor(minutes / 60);
      if (hours < 24) {
        unit = "hour";
        amount = hours;
      } else {
        const days = Math.floor(hours / 24);
        if (days < 30) {
          unit = "day";
          amount = days;
        } else {
          const months = Math.floor(days / 30);
          if (months < 12) {
            unit = "month";
            amount = months;
          } else {
            unit = "year";
            amount = Math.floor(months / 12);
          }
        }
      }
    }
  }

  const language = resolveLanguageFromStorage();
  const locale = DATE_LOCALES[language] ?? DATE_LOCALES.en;
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const signedAmount = diffMs >= 0 ? -amount : amount;
  return rtf.format(signedAmount, unit);
}

export type DateFormatKey = "compact" | "medium" | "news" | "date" | "time";

export const DATE_FORMATS: Record<DateFormatKey, Intl.DateTimeFormatOptions> = {
  compact: {
    year: "numeric",
    month: "short",
    day: "2-digit",
  },
  medium: {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  },
  news: {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  },
  date: {
    year: "numeric",
    month: "long",
    day: "2-digit",
  },
  time: {
    hour: "2-digit",
    minute: "2-digit",
  },
};

export const DATE_LOCALES = {
  pl: "pl-PL",
  en: "en-US",
  de: "de-DE",
};

export function formatDateTime(
  value?: string | null,
  language: keyof typeof DATE_LOCALES = "pl",
  format: DateFormatKey = "medium",
): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;
  const locale = DATE_LOCALES[language] ?? DATE_LOCALES.en;
  const options = DATE_FORMATS[format] ?? DATE_FORMATS.medium;
  return new Intl.DateTimeFormat(locale, options).format(target);
}

function resolveLanguageFromStorage(): keyof typeof DATE_LOCALES {
  if (typeof window === "undefined") return "pl";
  const stored = window.localStorage.getItem("venom-language");
  if (stored === "en" || stored === "de" || stored === "pl") {
    return stored;
  }
  return "pl";
}

const RELATIVE_UNITS = [
  { unit: "year", threshold: 12, step: 12 },
  { unit: "month", threshold: 30, step: 30 },
  { unit: "day", threshold: 24, step: 24 },
  { unit: "hour", threshold: 60, step: 60 },
  { unit: "minute", threshold: 60, step: 60 },
] as const;

function resolveRelativeAmount(absSeconds: number): {
  unit: Intl.RelativeTimeFormatUnit;
  amount: number;
} {
  let unit: Intl.RelativeTimeFormatUnit = "second";
  let amount = absSeconds;

  for (const entry of RELATIVE_UNITS) {
    const nextAmount = Math.floor(amount / entry.step);
    if (nextAmount < 1) break;
    unit = entry.unit;
    amount = nextAmount;
    if (amount < entry.threshold) break;
  }

  return { unit, amount };
}

export function formatRelativeTime(value?: string | null): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;

  const diffMs = Date.now() - target.getTime();
  const absSeconds = Math.max(1, Math.floor(Math.abs(diffMs) / 1000));
  const { unit, amount } = resolveRelativeAmount(absSeconds);

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

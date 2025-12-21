export function formatRelativeTime(value?: string | null): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;
  const diffMs = Date.now() - target.getTime();
  if (diffMs < 0) return "przyszłość";
  const seconds = Math.floor(diffMs / 1000);
  if (seconds < 60) return `${seconds}s temu`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m temu`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h temu`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d temu`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}m-cy temu`;
  const years = Math.floor(months / 12);
  return `${years}y temu`;
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

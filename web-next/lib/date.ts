function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatDateTimePrecise(value?: string | null): string {
  if (!value) return "—";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return value;

  const year = target.getFullYear();
  const month = pad2(target.getMonth() + 1);
  const day = pad2(target.getDate());
  const hour = pad2(target.getHours());
  const minute = pad2(target.getMinutes());
  const second = pad2(target.getSeconds());
  const tenth = Math.floor(target.getMilliseconds() / 100);
  return `${year}-${month}-${day} ${hour}:${minute}:${second}.${tenth}`;
}

export function formatRelativeTime(value?: string | null): string {
  return formatDateTimePrecise(value);
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

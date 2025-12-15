import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";

const locales = {
  pl,
  en,
  de,
};

type Locale = Record<string, unknown>;

function flatten(locale: Locale, prefix = "", result: Set<string> = new Set()): Set<string> {
  Object.entries(locale).forEach(([key, value]) => {
    const nextKey = prefix ? `${prefix}.${key}` : key;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      flatten(value as Locale, nextKey, result);
    } else {
      result.add(nextKey);
    }
  });
  return result;
}

const baseKeys = flatten(locales.pl);
const errors: string[] = [];

Object.entries(locales).forEach(([code, locale]) => {
  const keys = flatten(locale);
  const missing = [...baseKeys].filter((key) => !keys.has(key));
  const extra = [...keys].filter((key) => !baseKeys.has(key));

  if (missing.length > 0) {
    errors.push(`Locale ${code} is missing keys:\n- ${missing.join("\n- ")}`);
  }
  if (extra.length > 0) {
    errors.push(`Locale ${code} has extra keys (not in pl):\n- ${extra.join("\n- ")}`);
  }
});

if (errors.length > 0) {
  console.error("\u274c Locale consistency check failed\n");
  console.error(errors.join("\n\n"));
  process.exit(1);
}

console.log("\u2705 Locale consistency check passed (pl/en/de in sync)");

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";

function resolvePath(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, locale);
}

function collectLeafKeys(value: unknown, prefix = ""): string[] {
  if (!value || typeof value !== "object") {
    return [];
  }

  const keys: string[] = [];
  for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (nested && typeof nested === "object") {
      keys.push(...collectLeafKeys(nested, path));
    } else {
      keys.push(path);
    }
  }
  return keys;
}

const REQUIRED_THEME_KEYS = [
  "common.switchTheme",
  "theme.label",
  "theme.options.venomDark.short",
  "theme.options.venomDark.name",
  "theme.options.venomDark.description",
  "theme.options.venomLight.short",
  "theme.options.venomLight.name",
  "theme.options.venomLight.description",
] as const;

describe("theme i18n keys", () => {
  it("contains required keys in all supported locales", () => {
    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", pl as Record<string, unknown>],
      ["en", en as Record<string, unknown>],
      ["de", de as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of REQUIRED_THEME_KEYS) {
        const value = resolvePath(locale, key);
        assert.equal(typeof value, "string", `Missing key ${key} in locale ${name}`);
      }
    }
  });

  it("keeps theme keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys((pl as Record<string, unknown>).theme));
    const enKeys = new Set(collectLeafKeys((en as Record<string, unknown>).theme));
    const deKeys = new Set(collectLeafKeys((de as Record<string, unknown>).theme));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "theme key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "theme key drift: de vs pl");
  });
});

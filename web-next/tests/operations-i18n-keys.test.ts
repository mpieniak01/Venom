import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";
import { commandPalette as commandPalettePl } from "../lib/i18n/locales/command-palette/pl";
import { commandPalette as commandPaletteEn } from "../lib/i18n/locales/command-palette/en";
import { commandPalette as commandPaletteDe } from "../lib/i18n/locales/command-palette/de";
import { commandCenter as commandCenterPl } from "../lib/i18n/locales/command-center/pl";
import { commandCenter as commandCenterEn } from "../lib/i18n/locales/command-center/en";
import { commandCenter as commandCenterDe } from "../lib/i18n/locales/command-center/de";
import { quickActions as quickActionsPl } from "../lib/i18n/locales/quick-actions/pl";
import { quickActions as quickActionsEn } from "../lib/i18n/locales/quick-actions/en";
import { quickActions as quickActionsDe } from "../lib/i18n/locales/quick-actions/de";

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

const REQUIRED_KEYS = [
  "commandPalette.title",
  "commandCenter.stats.queueLabel",
  "commandCenter.shortcuts.links.strategy.label",
  "quickActions.actions.togglePause",
  "quickActions.actions.emergencyConfirm",
] as const;

describe("operations i18n keys", () => {
  it("contains required keys in all supported locales", () => {
    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", pl as Record<string, unknown>],
      ["en", en as Record<string, unknown>],
      ["de", de as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of REQUIRED_KEYS) {
        const value = resolvePath(locale, key);
        assert.equal(typeof value, "string", `Missing key ${key} in locale ${name}`);
      }
    }
  });

  it("keeps commandPalette keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(commandPalettePl));
    const enKeys = new Set(collectLeafKeys(commandPaletteEn));
    const deKeys = new Set(collectLeafKeys(commandPaletteDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "commandPalette key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "commandPalette key drift: de vs pl");
  });

  it("keeps commandCenter keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(commandCenterPl));
    const enKeys = new Set(collectLeafKeys(commandCenterEn));
    const deKeys = new Set(collectLeafKeys(commandCenterDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "commandCenter key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "commandCenter key drift: de vs pl");
  });

  it("keeps quickActions keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(quickActionsPl));
    const enKeys = new Set(collectLeafKeys(quickActionsEn));
    const deKeys = new Set(collectLeafKeys(quickActionsDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "quickActions key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "quickActions key drift: de vs pl");
  });
});

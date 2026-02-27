import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";
import { academy as academyPl } from "../lib/i18n/locales/academy/pl";
import { academy as academyEn } from "../lib/i18n/locales/academy/en";
import { academy as academyDe } from "../lib/i18n/locales/academy/de";
import { models as modelsPl } from "../lib/i18n/locales/models-locale/pl";
import { models as modelsEn } from "../lib/i18n/locales/models-locale/en";
import { models as modelsDe } from "../lib/i18n/locales/models-locale/de";

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
  "academy.dashboard.title",
  "academy.training.status.running",
  "academy.conversion.useForTraining",
  "models.tabs.remoteModels",
  "models.sections.remote.catalog.title",
  "models.domain.trainability.reasons.cloudOnly",
] as const;

describe("academy/models i18n keys", () => {
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

  it("keeps academy keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(academyPl));
    const enKeys = new Set(collectLeafKeys(academyEn));
    const deKeys = new Set(collectLeafKeys(academyDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "academy key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "academy key drift: de vs pl");
  });

  it("keeps models keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(modelsPl));
    const enKeys = new Set(collectLeafKeys(modelsEn));
    const deKeys = new Set(collectLeafKeys(modelsDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "models key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "models key drift: de vs pl");
  });
});

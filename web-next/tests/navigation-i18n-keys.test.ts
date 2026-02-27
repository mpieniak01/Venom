import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";
import { sidebar as sidebarPl } from "../lib/i18n/locales/sidebar/pl";
import { sidebar as sidebarEn } from "../lib/i18n/locales/sidebar/en";
import { sidebar as sidebarDe } from "../lib/i18n/locales/sidebar/de";
import { moduleHost as moduleHostPl } from "../lib/i18n/locales/module-host/pl";
import { moduleHost as moduleHostEn } from "../lib/i18n/locales/module-host/en";
import { moduleHost as moduleHostDe } from "../lib/i18n/locales/module-host/de";
import { systemStatus as systemStatusPl } from "../lib/i18n/locales/system-status/pl";
import { systemStatus as systemStatusEn } from "../lib/i18n/locales/system-status/en";
import { systemStatus as systemStatusDe } from "../lib/i18n/locales/system-status/de";
import { mobileNav as mobileNavPl } from "../lib/i18n/locales/mobile-nav/pl";
import { mobileNav as mobileNavEn } from "../lib/i18n/locales/mobile-nav/en";
import { mobileNav as mobileNavDe } from "../lib/i18n/locales/mobile-nav/de";

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

const REQUIRED_NAVIGATION_KEYS = [
  "sidebar.modulesTitle",
  "sidebar.nav.workflowControl",
  "sidebar.autonomy.title",
  "moduleHost.moduleId",
  "systemStatus.hints.waiting",
  "mobileNav.telemetry.title",
  "mobileNav.systemStatus.loading",
] as const;

describe("navigation i18n keys", () => {
  it("contains required keys in all supported locales", () => {
    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", pl as Record<string, unknown>],
      ["en", en as Record<string, unknown>],
      ["de", de as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of REQUIRED_NAVIGATION_KEYS) {
        const value = resolvePath(locale, key);
        assert.equal(typeof value, "string", `Missing key ${key} in locale ${name}`);
      }
    }
  });

  it("keeps sidebar leaf keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(sidebarPl));
    const enKeys = new Set(collectLeafKeys(sidebarEn));
    const deKeys = new Set(collectLeafKeys(sidebarDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "sidebar key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "sidebar key drift: de vs pl");
  });

  it("keeps moduleHost leaf keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(moduleHostPl));
    const enKeys = new Set(collectLeafKeys(moduleHostEn));
    const deKeys = new Set(collectLeafKeys(moduleHostDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "moduleHost key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "moduleHost key drift: de vs pl");
  });

  it("keeps systemStatus leaf keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(systemStatusPl));
    const enKeys = new Set(collectLeafKeys(systemStatusEn));
    const deKeys = new Set(collectLeafKeys(systemStatusDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "systemStatus key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "systemStatus key drift: de vs pl");
  });

  it("keeps mobileNav leaf keys synchronized across pl/en/de", () => {
    const plKeys = new Set(collectLeafKeys(mobileNavPl));
    const enKeys = new Set(collectLeafKeys(mobileNavEn));
    const deKeys = new Set(collectLeafKeys(mobileNavDe));

    assert.deepEqual([...enKeys].sort(), [...plKeys].sort(), "mobileNav key drift: en vs pl");
    assert.deepEqual([...deKeys].sort(), [...plKeys].sort(), "mobileNav key drift: de vs pl");
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { topBar as topBarPl } from "../lib/i18n/locales/top-bar/pl";
import { topBar as topBarEn } from "../lib/i18n/locales/top-bar/en";
import { topBar as topBarDe } from "../lib/i18n/locales/top-bar/de";
import { pl } from "../lib/i18n/locales/pl";
import { en } from "../lib/i18n/locales/en";
import { de } from "../lib/i18n/locales/de";

const REQUIRED_TOPBAR_KEYS = [
  "topBar.wsLabel",
  "topBar.connected",
  "topBar.offline",
  "topBar.alertCenter",
  "topBar.notifications",
  "topBar.commandPalette",
  "topBar.quickActions",
  "topBar.services",
  "topBar.commandCenter",
] as const;

function resolvePath(locale: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, locale);
}

describe("topBar i18n keys", () => {
  it("contains required keys in all supported locales", () => {
    const locales: Array<[string, Record<string, unknown>]> = [
      ["pl", pl as Record<string, unknown>],
      ["en", en as Record<string, unknown>],
      ["de", de as Record<string, unknown>],
    ];

    for (const [name, locale] of locales) {
      for (const key of REQUIRED_TOPBAR_KEYS) {
        const value = resolvePath(locale, key);
        assert.equal(typeof value, "string", `Missing key ${key} in locale ${name}`);
      }
    }
  });

  it("keeps topBar leaf keys synchronized across pl/en/de", () => {
    assert.deepEqual(
      Object.keys(topBarEn).sort(),
      Object.keys(topBarPl).sort(),
      "topBar key drift: en vs pl",
    );
    assert.deepEqual(
      Object.keys(topBarDe).sort(),
      Object.keys(topBarPl).sort(),
      "topBar key drift: de vs pl",
    );
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  DEFAULT_THEME,
  THEME_REGISTRY,
  isThemeId,
  normalizeTheme,
  resolveThemeId,
} from "../lib/theme-registry";

describe("theme registry", () => {
  it("contains expected stable ids", () => {
    assert.deepEqual(Object.keys(THEME_REGISTRY).sort(), ["venom-dark", "venom-light"]);
  });

  it("validates theme ids", () => {
    assert.equal(isThemeId("venom-dark"), true);
    assert.equal(isThemeId("venom-light"), true);
    assert.equal(isThemeId("unknown-theme"), false);
    assert.equal(isThemeId(""), false);
    assert.equal(isThemeId(undefined), false);
  });

  it("normalizes invalid values to default", () => {
    assert.equal(normalizeTheme("venom-dark"), "venom-dark");
    assert.equal(normalizeTheme("venom-light"), "venom-light");
    assert.equal(normalizeTheme("venom-light-dev"), "venom-light");
    assert.equal(normalizeTheme("foo"), DEFAULT_THEME);
    assert.equal(normalizeTheme(null), DEFAULT_THEME);
  });

  it("resolves legacy aliases", () => {
    assert.equal(resolveThemeId("venom-light-dev"), "venom-light");
    assert.equal(resolveThemeId("venom-light"), "venom-light");
    assert.equal(resolveThemeId("not-a-theme"), null);
  });
});

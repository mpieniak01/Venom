import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "../lib/theme-ui";

describe("theme ui helpers", () => {
  it("uses semantic token classes for the tab bar", () => {
    assert.match(THEME_TAB_BAR_CLASS, /border-\[color:var\(--ui-border\)\]/);
  });

  it("returns active and inactive tab variants with semantic colors", () => {
    const active = getThemeTabClass(true);
    const inactive = getThemeTabClass(false);

    assert.match(active, /border-b-\[color:var\(--accent\)\]/);
    assert.match(active, /bg-\[color:var\(--primary-dim\)\]/);
    assert.match(inactive, /text-\[color:var\(--ui-muted\)\]/);
    assert.match(inactive, /hover:bg-\[color:var\(--ui-surface-hover\)\]/);
  });
});

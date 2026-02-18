import assert from "node:assert/strict";
import { describe, it } from "node:test";

describe("sidebar optional modules", () => {
  it("does not include module-example when feature flag is disabled", async () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "false";
    const mod = await import("../components/layout/sidebar-helpers");
    const items = mod.getNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), false);
  });

  it("includes module-example when feature flag is enabled", async () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "true";
    const mod = await import("../components/layout/sidebar-helpers");
    const items = mod.getNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), true);
  });
});

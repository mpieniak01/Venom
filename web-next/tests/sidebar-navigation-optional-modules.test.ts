import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

const originalFlag = process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;

afterEach(() => {
  if (originalFlag === undefined) {
    delete process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;
    return;
  }
  process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = originalFlag;
});

async function loadNavigationItems() {
  const mod = await import(`../components/layout/sidebar-helpers.ts?ts=${Date.now()}`);
  return mod.getNavigationItems();
}

describe("sidebar optional modules", () => {
  it("does not include module-example when feature flag is disabled", async () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "false";
    const items = await loadNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), false);
  });

  it("includes module-example when feature flag is enabled", async () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "true";
    const items = await loadNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), true);
  });
});

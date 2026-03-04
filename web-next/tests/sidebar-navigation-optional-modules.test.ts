import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";

const originalFlag = process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;
const originalGoogleHomeFlag = process.env.NEXT_PUBLIC_FEATURE_GOOGLE_HOME_BRIDGE;

afterEach(() => {
  if (originalFlag === undefined) {
    delete process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;
  } else {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = originalFlag;
  }

  if (originalGoogleHomeFlag === undefined) {
    delete process.env.NEXT_PUBLIC_FEATURE_GOOGLE_HOME_BRIDGE;
    return;
  }
  process.env.NEXT_PUBLIC_FEATURE_GOOGLE_HOME_BRIDGE = originalGoogleHomeFlag;
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

  it("includes google-home when feature flag is enabled", async () => {
    process.env.NEXT_PUBLIC_FEATURE_GOOGLE_HOME_BRIDGE = "true";
    const items = await loadNavigationItems();
    assert.equal(items.some((item) => item.href === "/google-home"), true);
  });
});

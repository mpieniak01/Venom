import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { getNavigationItems } from "../components/layout/sidebar-helpers";

const originalFlag = process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;

afterEach(() => {
  if (originalFlag === undefined) {
    delete process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE;
    return;
  }
  process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = originalFlag;
});

describe("sidebar optional modules", () => {
  it("does not include module-example when feature flag is disabled", () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "false";
    const items = getNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), false);
  });

  it("includes module-example when feature flag is enabled", () => {
    process.env.NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE = "true";
    const items = getNavigationItems();
    assert.equal(items.some((item) => item.href === "/module-example"), true);
  });
});

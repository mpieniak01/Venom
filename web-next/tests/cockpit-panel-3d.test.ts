import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { getCockpitPanel3DClass } from "../components/cockpit/cockpit-panel-3d";

describe("getCockpitPanel3DClass", () => {
  it("uses fixed overlay classes in fullscreen mode", () => {
    const className = getCockpitPanel3DClass(true);
    assert.ok(className.includes("fixed"));
    assert.ok(className.includes("inset-4"));
    assert.ok(className.includes("z-[70]"));
    assert.ok(!className.includes("h-[76dvh]"));
  });

  it("uses bounded panel height in normal mode", () => {
    const className = getCockpitPanel3DClass(false);
    assert.ok(className.includes("h-[76dvh]"));
    assert.ok(className.includes("min-h-[620px]"));
    assert.ok(className.includes("max-h-[980px]"));
    assert.ok(!className.includes("fixed"));
  });
});

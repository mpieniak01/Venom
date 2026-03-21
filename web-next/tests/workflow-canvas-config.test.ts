import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  SWIMLANE_ORDER,
  WORKFLOW_NODE_THEME,
  miniMapNodeColor,
} from "../components/workflow-control/canvas/config";

describe("workflow canvas config", () => {
  it("ensures every swimlane type has a matching visual theme token", () => {
    for (const laneType of SWIMLANE_ORDER) {
      assert.ok(
        laneType in WORKFLOW_NODE_THEME,
        `Missing theme token for lane type: ${laneType}`,
      );
    }
  });

  it("defines complete visual theme tokens for every workflow node type", () => {
    for (const type of SWIMLANE_ORDER) {
      const theme = WORKFLOW_NODE_THEME[type];
      assert.equal(typeof theme.glowClass, "string");
      assert.equal(typeof theme.shellClass, "string");
      assert.equal(typeof theme.titleClass, "string");
      assert.equal(typeof theme.handleClass, "string");
      assert.ok(theme.glowClass.length > 0);
      assert.ok(theme.shellClass.length > 0);
      assert.ok(theme.titleClass.length > 0);
      assert.ok(theme.handleClass.length > 0);
    }
  });

  it("maps minimap colors by node type and has a fallback", () => {
    assert.equal(miniMapNodeColor({ type: "decision" } as never), "#3b82f6");
    assert.equal(miniMapNodeColor({ type: "intent" } as never), "#eab308");
    assert.equal(miniMapNodeColor({ type: "kernel" } as never), "#22c55e");
    assert.equal(miniMapNodeColor({ type: "runtime" } as never), "#a855f7");
    assert.equal(miniMapNodeColor({ type: "embedding" } as never), "#ec4899");
    assert.equal(miniMapNodeColor({ type: "provider" } as never), "#f97316");
    assert.equal(miniMapNodeColor({ type: "unknown-type" } as never), "#334155");
  });
});

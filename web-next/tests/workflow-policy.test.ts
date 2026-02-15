import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { NODE_CATEGORIES, getSwimlaneForCategory, validateConnection } from "../lib/workflow-policy";

describe("workflow policy", () => {
  it("allows only configured directional connections", () => {
    const decisionToIntent = validateConnection(
      { id: "decision", type: "decision", data: {}, position: { x: 0, y: 0 } },
      { id: "intent", type: "intent", data: {}, position: { x: 0, y: 0 } },
    );
    assert.equal(decisionToIntent.isValid, true);

    const decisionToProvider = validateConnection(
      { id: "decision", type: "decision", data: {}, position: { x: 0, y: 0 } },
      { id: "provider", type: "provider", data: {}, position: { x: 0, y: 0 } },
    );
    assert.equal(decisionToProvider.isValid, false);
    assert.match(decisionToProvider.reason ?? "", /invalid_connection/);
  });

  it("maps swimlane ordering deterministically", () => {
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.DECISION), 0);
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.INTENT), 1);
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.KERNEL), 2);
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.RUNTIME), 3);
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.EMBEDDING), 4);
    assert.equal(getSwimlaneForCategory(NODE_CATEGORIES.PROVIDER), 5);
  });
});

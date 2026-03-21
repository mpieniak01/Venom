import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  relationTheme,
  workflowCanvasEdgeTypes,
} from "../components/workflow-control/canvas/edge-components";

describe("workflow canvas edge components", () => {
  it("exposes workflow relation edge type", () => {
    assert.equal(typeof workflowCanvasEdgeTypes.workflow_relation, "function");
  });

  it("keeps stable visual contract for domain/runtime/sequence relations", () => {
    const domain = relationTheme("domain");
    const runtime = relationTheme("runtime");
    const sequence = relationTheme("sequence");

    assert.equal(domain.stroke, "#22d3ee");
    assert.equal(runtime.stroke, "#a78bfa");
    assert.equal(sequence.stroke, "#34d399");

    assert.equal(domain.strokeDasharray, "8 5");
    assert.equal(runtime.strokeDasharray, undefined);
    assert.equal(sequence.strokeDasharray, undefined);

    assert.ok(domain.borderRadius > runtime.borderRadius);
    assert.ok(runtime.borderRadius > sequence.borderRadius);

    assert.ok(domain.offset > runtime.offset);
    assert.ok(runtime.offset > sequence.offset);
  });
});

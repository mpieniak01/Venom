import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildCanvasGraph, graphSignature } from "../components/workflow-control/canvas/layout";
import { SWIMLANE_ORDER } from "../components/workflow-control/canvas/config";

describe("workflow canvas layout", () => {
  it("renders swimlanes even when workflow state is unavailable", () => {
    const { initialNodes, initialEdges } = buildCanvasGraph(null, true);

    assert.equal(initialEdges.length, 0);
    assert.equal(initialNodes.length, SWIMLANE_ORDER.length);
    assert.ok(initialNodes.every((node) => node.type === "swimlane"));
  });

  it("toggles node interactivity based on readOnly mode", () => {
    const sampleState = {
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime: { services: ["backend", "ui"] },
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
    };

    const editable = buildCanvasGraph(sampleState, false);
    const readOnly = buildCanvasGraph(sampleState, true);

    const editableDecision = editable.initialNodes.find((node) => node.id === "decision");
    const readOnlyDecision = readOnly.initialNodes.find((node) => node.id === "decision");

    assert.equal(editableDecision?.draggable, true);
    assert.equal(editableDecision?.selectable, true);
    assert.equal(readOnlyDecision?.draggable, false);
    assert.equal(readOnlyDecision?.selectable, false);
  });

  it("includes interactivity flags in graph signature", () => {
    const sampleState = {
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime: { services: ["backend", "ui"] },
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
    };

    const editable = buildCanvasGraph(sampleState, false);
    const readOnly = buildCanvasGraph(sampleState, true);

    assert.notEqual(
      graphSignature(editable.initialNodes, editable.initialEdges),
      graphSignature(readOnly.initialNodes, readOnly.initialEdges),
    );
  });
});

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

  it("keeps node interactivity disabled because helper canvas is read-only", () => {
    const sampleState = {
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
        { id: "ui", name: "ui", kind: "ui", status: "running", dependencies: ["backend"] },
      ],
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
      execution_steps: [
        {
          id: "step-1",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
      ],
    };

    const editable = buildCanvasGraph(sampleState, false);
    const readOnly = buildCanvasGraph(sampleState, true);

    const editableDecision = editable.initialNodes.find((node) => node.id === "control-domain:decision");
    const readOnlyDecision = readOnly.initialNodes.find((node) => node.id === "control-domain:decision");

    assert.equal(editableDecision?.draggable, false);
    assert.equal(editableDecision?.selectable, false);
    assert.equal(readOnlyDecision?.draggable, false);
    assert.equal(readOnlyDecision?.selectable, false);
  });

  it("keeps graph signature stable regardless of readOnly flag", () => {
    const sampleState = {
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
        { id: "ui", name: "ui", kind: "ui", status: "running", dependencies: ["backend"] },
      ],
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
      execution_steps: [
        {
          id: "step-1",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
      ],
    };

    const editable = buildCanvasGraph(sampleState, false);
    const readOnly = buildCanvasGraph(sampleState, true);

    assert.equal(
      graphSignature(editable.initialNodes, editable.initialEdges),
      graphSignature(readOnly.initialNodes, readOnly.initialEdges),
    );
  });
});

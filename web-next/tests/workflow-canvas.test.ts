import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildWorkflowGraph } from "../lib/workflow-canvas-helpers";

describe("workflow canvas graph builder", () => {
  it("returns empty graph for null state", () => {
    const graph = buildWorkflowGraph(null);
    assert.equal(graph.nodes.length, 0);
    assert.equal(graph.edges.length, 0);
  });

  it("builds expected core nodes and edges for valid state", () => {
    const graph = buildWorkflowGraph({
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime: { services: ["backend", "ui"] },
      provider: { active: "ollama" },
      embedding_model: "sentence-transformers",
      workflow_status: "running",
    });

    const nodeIds = graph.nodes.map((n) => n.id).sort();
    assert.deepEqual(
      nodeIds,
      ["decision", "embedding", "kernel", "provider", "runtime"].sort()
    );

    const edgeIds = graph.edges.map((e) => e.id).sort();
    assert.deepEqual(edgeIds, ["e1", "e2", "e3", "e4"]);
  });
});

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
      ["decision", "intent", "embedding", "config", "kernel", "provider", "runtime"].sort()
    );

    const edgeIds = graph.edges.map((e) => e.id).sort();
    assert.deepEqual(edgeIds, ["e1", "e2", "e3", "e4", "e5", "e6"]);

    const providerNode = graph.nodes.find((node) => node.id === "provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "embedding");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (providerNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "local"
    );
    assert.equal(
      ((providerNode?.data as { provider?: { sourceType?: string } } | undefined)?.provider?.sourceType),
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "local"
    );
  });

  it("marks provider/embedding as cloud when cloud provider is active", () => {
    const graph = buildWorkflowGraph({
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
    });

    const providerNode = graph.nodes.find((node) => node.id === "provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "embedding");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "cloud"
    );
    assert.equal(
      (providerNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "cloud"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "cloud"
    );
    assert.equal(
      (embeddingNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "cloud"
    );
  });

  it("respects explicit provider/embedding source when present in state", () => {
    const graph = buildWorkflowGraph({
      provider: { active: "openai", sourceType: "local" },
      provider_source: "local",
      embedding_model: "text-embedding-3-large",
      embedding_source: "local",
    });

    const providerNode = graph.nodes.find((node) => node.id === "provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "embedding");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (providerNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceType?: string } | undefined)?.sourceType,
      "local"
    );
  });

  it("uses backend graph when canonical graph payload is present", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          {
            id: "runtime-service:backend",
            type: "runtime_service",
            data: { name: "backend", status: "running" },
            position: { x: 123, y: 456 },
          },
        ],
        edges: [
          {
            id: "runtime-link:backend",
            source: "runtime",
            target: "runtime-service:backend",
            animated: false,
          },
        ],
      },
    });

    assert.equal(graph.nodes.length, 1);
    assert.equal(graph.nodes[0]?.id, "runtime-service:backend");
    assert.equal(graph.nodes[0]?.position.x, 123);
    assert.equal(graph.edges.length, 1);
    assert.equal(graph.edges[0]?.id, "runtime-link:backend");
  });
});

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { buildWorkflowGraph } from "../lib/workflow-canvas-helpers";

describe("workflow canvas graph builder", () => {
  it("returns empty graph for null state", () => {
    const graph = buildWorkflowGraph(null);
    assert.equal(graph.nodes.length, 0);
    assert.equal(graph.edges.length, 0);
  });

  it("builds control, runtime and execution nodes for fallback graph", () => {
    const graph = buildWorkflowGraph({
      decision_strategy: "advanced",
      intent_mode: "expert",
      kernel: "optimized",
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
        { id: "ui", name: "ui", kind: "ui", status: "running", dependencies: ["backend"] },
      ],
      provider: { active: "ollama" },
      embedding_model: "sentence-transformers",
      workflow_status: "running",
      config_fields: [
        { key: "AI_MODE", value: "advanced", options: ["standard", "advanced"] },
        { key: "INTENT_MODE", value: "expert", options: ["simple", "expert"] },
        { key: "KERNEL", value: "optimized", options: ["standard", "optimized"] },
        { key: "ACTIVE_PROVIDER", value: "ollama", options: ["ollama", "openai"] },
        {
          key: "EMBEDDING_MODEL",
          value: "sentence-transformers",
          options: ["sentence-transformers", "openai-embeddings"],
        },
      ],
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
        {
          id: "step-2",
          component: "response",
          action: "answer",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "step-1",
          related_service_id: "ui",
          related_config_keys: ["ACTIVE_PROVIDER"],
        },
      ],
    });

    const nodeIds = graph.nodes.map((n) => n.id).sort();
    assert.deepEqual(nodeIds, [
      "control-domain:config",
      "control-domain:decision",
      "control-domain:embedding",
      "control-domain:intent",
      "control-domain:kernel",
      "control-domain:provider",
      "execution-step:step-1",
      "execution-step:step-2",
      "runtime-service:backend",
      "runtime-service:ui",
    ]);

    const edgeIds = graph.edges.map((e) => e.id).sort();
    assert.deepEqual(edgeIds, [
      "domain-step:intent->execution-step:step-1:INTENT_MODE",
      "domain-step:provider->execution-step:step-2:ACTIVE_PROVIDER",
      "runtime-step:runtime-service:backend->execution-step:step-1",
      "runtime-step:runtime-service:ui->execution-step:step-2",
      "step-edge:execution-step:step-1->execution-step:step-2",
    ]);
    const domainEdge = graph.edges.find((edge) => edge.id === "domain-step:intent->execution-step:step-1:INTENT_MODE");
    const runtimeEdge = graph.edges.find((edge) => edge.id === "runtime-step:runtime-service:backend->execution-step:step-1");
    const sequenceEdge = graph.edges.find((edge) => edge.id === "step-edge:execution-step:step-1->execution-step:step-2");
    assert.equal(domainEdge?.type, "workflow_relation");
    assert.deepEqual(domainEdge?.data, {
      relationKind: "domain",
      relationLabel: "INTENT_MODE",
    });
    assert.equal(runtimeEdge?.type, "workflow_relation");
    assert.deepEqual(runtimeEdge?.data, {
      relationKind: "runtime",
      relationLabel: "runtime",
    });
    assert.equal(sequenceEdge?.type, "workflow_relation");
    assert.deepEqual(sequenceEdge?.data, {
      relationKind: "sequence",
      relationLabel: "depends",
    });

    const providerNode = graph.nodes.find((node) => node.id === "control-domain:provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "control-domain:embedding");
    const firstStepNode = graph.nodes.find((node) => node.id === "execution-step:step-1");
    const secondStepNode = graph.nodes.find((node) => node.id === "execution-step:step-2");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.deepEqual(
      (firstStepNode?.data as { alternativeVariants?: string[] } | undefined)?.alternativeVariants,
      ["simple"],
    );
    assert.equal(
      (firstStepNode?.data as { alternativeCount?: number } | undefined)?.alternativeCount,
      1,
    );
    assert.deepEqual(
      (secondStepNode?.data as { alternativeVariants?: string[] } | undefined)?.alternativeVariants,
      ["openai"],
    );
  });

  it("marks provider/embedding as cloud when cloud provider is active", () => {
    const graph = buildWorkflowGraph({
      provider: { active: "openai" },
      embedding_model: "text-embedding-3-large",
    });

    const providerNode = graph.nodes.find((node) => node.id === "control-domain:provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "control-domain:embedding");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "cloud"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
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

    const providerNode = graph.nodes.find((node) => node.id === "control-domain:provider");
    const embeddingNode = graph.nodes.find((node) => node.id === "control-domain:embedding");
    assert.equal(
      (providerNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
      "local"
    );
    assert.equal(
      (embeddingNode?.data as { sourceTag?: string } | undefined)?.sourceTag,
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

  it("collapses sibling alternative steps into one visible graph node", () => {
    const graph = buildWorkflowGraph({
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
      ],
      config_fields: [
        { key: "INTENT_MODE", value: "expert", options: ["simple", "expert"] },
      ],
      execution_steps: [
        {
          id: "root-step",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
        {
          id: "branch-a",
          component: "routing",
          action: "route-fast",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
        {
          id: "branch-b",
          component: "routing",
          action: "route-safe",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
      ],
    });

    const executionNodeIds = graph.nodes
      .filter((node) => node.type === "execution_step")
      .map((node) => node.id)
      .sort();
    assert.deepEqual(executionNodeIds, [
      "execution-step:branch-a",
      "execution-step:root-step",
    ]);

    const collapsedNode = graph.nodes.find((node) => node.id === "execution-step:branch-a");
    assert.equal(
      (collapsedNode?.data as { collapsedStepCount?: number } | undefined)?.collapsedStepCount,
      1,
    );
    assert.deepEqual(
      (collapsedNode?.data as { alternativeVariants?: string[] } | undefined)?.alternativeVariants,
      ["route-safe", "simple"],
    );

    const sequenceEdges = graph.edges.filter((edge) => edge.source === "execution-step:root-step");
    assert.equal(sequenceEdges.length, 1);
    assert.equal(sequenceEdges[0]?.target, "execution-step:branch-a");
  });

  it("expands a collapsed branch group on demand", () => {
    const systemState = {
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
      ],
      config_fields: [
        { key: "INTENT_MODE", value: "expert", options: ["simple", "expert"] },
      ],
      execution_steps: [
        {
          id: "root-step",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
        {
          id: "branch-a",
          component: "routing",
          action: "route-fast",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
        {
          id: "branch-b",
          component: "routing",
          action: "route-safe",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["INTENT_MODE"],
        },
      ],
    } as const;

    const collapsed = buildWorkflowGraph(systemState);
    const collapsedNode = collapsed.nodes.find((node) => node.id === "execution-step:branch-a");
    const groupKey = (collapsedNode?.data as { groupKey?: string } | undefined)?.groupKey;

    assert.equal(typeof groupKey, "string");

    const expanded = buildWorkflowGraph(systemState, {
      expandedGroupKeys: new Set([groupKey as string]),
    });

    const executionNodeIds = expanded.nodes
      .filter((node) => node.type === "execution_step")
      .map((node) => node.id)
      .sort();
    assert.deepEqual(executionNodeIds, [
      "execution-step:branch-a",
      "execution-step:branch-b",
      "execution-step:root-step",
    ]);

    const expandedBranchNode = expanded.nodes.find((node) => node.id === "execution-step:branch-b");
    assert.equal(
      (expandedBranchNode?.data as { isExpanded?: boolean } | undefined)?.isExpanded,
      true,
    );
  });
});

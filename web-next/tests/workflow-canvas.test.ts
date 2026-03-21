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

  it("falls back to derived canonical graph when backend payload is legacy-mixed", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          { id: "decision", type: "decision", data: { strategy: "advanced" }, position: { x: 0, y: 0 } },
          {
            id: "step:legacy-step",
            type: "execution_step",
            data: { stepId: "legacy-step", component: "intent", action: "classify" },
            position: { x: 320, y: 300 },
          },
        ],
        edges: [{ id: "legacy-edge", source: "decision", target: "step:legacy-step" }],
      },
      runtime_services: [{ id: "backend", name: "backend", kind: "backend", status: "running" }],
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
    });

    const nodeIds = graph.nodes.map((node) => node.id).sort();
    assert.ok(nodeIds.includes("control-domain:intent"));
    assert.ok(nodeIds.includes("runtime-service:backend"));
    assert.ok(nodeIds.includes("execution-step:step-1"));
    assert.ok(!nodeIds.includes("decision"));
    assert.ok(!nodeIds.includes("step:legacy-step"));
  });

  it("falls back to derived canonical graph when backend payload has unsupported node types", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          {
            id: "runtime-service:backend",
            type: "runtime_service",
            data: { name: "backend", status: "running" },
            position: { x: 120, y: 320 },
          },
          {
            id: "mystery-node:1",
            type: "experimental_widget",
            data: { label: "mystery" },
            position: { x: 420, y: 320 },
          },
          {
            id: "execution-step:step-1",
            type: "execution_step",
            data: { stepId: "step-1", component: "intent", action: "classify" },
            position: { x: 620, y: 620 },
          },
        ],
        edges: [
          {
            id: "runtime-link:runtime-service:backend->execution-step:step-1",
            source: "runtime-service:backend",
            target: "execution-step:step-1",
          },
        ],
      },
      runtime_services: [{ id: "backend", name: "backend", kind: "backend", status: "running" }],
      execution_steps: [
        {
          id: "step-1",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
        },
      ],
    });

    const nodeIds = graph.nodes.map((node) => node.id).sort();
    assert.ok(nodeIds.includes("runtime-service:backend"));
    assert.ok(nodeIds.includes("execution-step:step-1"));
    assert.ok(!nodeIds.includes("mystery-node:1"));
    assert.ok(
      graph.nodes.every((node) =>
        ["control_domain", "runtime_service", "execution_step"].includes(
          String(node.type ?? ""),
        ),
      ),
    );
  });

  it("normalizes backend node aliases to canonical node types", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          {
            id: "runtime-service:backend",
            type: "runtime-service",
            data: { name: "backend", status: "running", dependencies: ["db"] },
            position: { x: 123, y: 456 },
          },
          {
            id: "execution-step:step-1",
            type: "execution-step",
            data: { component: "intent", action: "classify", status: "ok" },
            position: { x: 450, y: 630 },
          },
        ],
        edges: [{ id: "e1", source: "runtime-service:backend", target: "execution-step:step-1" }],
      },
      runtime_services: [{ id: "backend", name: "backend", status: "running" }],
      execution_steps: [{ id: "step-1", component: "intent", action: "classify", status: "ok" }],
    });

    const runtimeNode = graph.nodes.find((node) => node.id === "runtime-service:backend");
    const stepNode = graph.nodes.find((node) => node.id === "execution-step:step-1");

    assert.equal(runtimeNode?.type, "runtime_service");
    assert.equal(stepNode?.type, "execution_step");
    assert.equal((runtimeNode?.data as { serviceId?: string } | undefined)?.serviceId, "backend");
    assert.equal((stepNode?.data as { stepId?: string } | undefined)?.stepId, "step-1");
  });

  it("normalizes backend edges with opaque ids into workflow relation kinds", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          { id: "control-domain:intent", type: "control_domain", data: {}, position: { x: 0, y: 0 } },
          { id: "runtime-service:backend", type: "runtime_service", data: {}, position: { x: 0, y: 0 } },
          { id: "execution-step:a", type: "execution_step", data: {}, position: { x: 0, y: 0 } },
          { id: "execution-step:b", type: "execution_step", data: {}, position: { x: 0, y: 0 } },
        ],
        edges: [
          { id: "e1", source: "control-domain:intent", target: "execution-step:a" },
          { id: "e2", source: "runtime-service:backend", target: "execution-step:a" },
          { id: "e3", source: "execution-step:a", target: "execution-step:b" },
        ],
      },
    });

    const edgeById = new Map(graph.edges.map((edge) => [edge.id, edge]));

    assert.equal(edgeById.get("e1")?.type, "workflow_relation");
    assert.equal((edgeById.get("e1")?.data as { relationKind?: string })?.relationKind, "domain");
    assert.ok(edgeById.get("e1")?.markerEnd);

    assert.equal(edgeById.get("e2")?.type, "workflow_relation");
    assert.equal((edgeById.get("e2")?.data as { relationKind?: string })?.relationKind, "runtime");
    assert.ok(edgeById.get("e2")?.markerEnd);

    assert.equal(edgeById.get("e3")?.type, "workflow_relation");
    assert.equal((edgeById.get("e3")?.data as { relationKind?: string })?.relationKind, "sequence");
    assert.ok(edgeById.get("e3")?.markerEnd);
  });

  it("falls back to derived relations when backend graph has nodes but no edges", () => {
    const graph = buildWorkflowGraph({
      graph: {
        nodes: [
          {
            id: "runtime-service:backend",
            type: "runtime_service",
            data: { name: "backend", status: "running" },
            position: { x: 120, y: 320 },
          },
          {
            id: "execution-step:step-1",
            type: "execution_step",
            data: { stepId: "step-1", action: "classify" },
            position: { x: 520, y: 640 },
          },
        ],
        edges: [],
      },
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
      ],
      execution_steps: [
        {
          id: "step-1",
          component: "intent",
          action: "classify",
          status: "ok",
          stage: "execution",
          related_service_id: "backend",
        },
      ],
    });

    assert.ok(graph.nodes.length >= 2);
    assert.ok(graph.edges.length >= 1);
    assert.ok(
      graph.edges.some(
        (edge) =>
          edge.id === "runtime-step:runtime-service:backend->execution-step:step-1" &&
          edge.type === "workflow_relation",
      ),
    );
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

  it("keeps a stable multibranch graph contract for routing and relation kinds", () => {
    const systemState = {
      runtime_services: [
        { id: "backend", name: "backend", kind: "backend", status: "running" },
        { id: "ui", name: "ui", kind: "ui", status: "running", dependencies: ["backend"] },
      ],
      config_fields: [
        { key: "INTENT_MODE", value: "expert", options: ["simple", "expert"] },
        { key: "ACTIVE_PROVIDER", value: "onnx", options: ["onnx", "openai"] },
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
          component: "router",
          action: "route-fast",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["ACTIVE_PROVIDER"],
        },
        {
          id: "branch-b",
          component: "router",
          action: "route-safe",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "root-step",
          related_service_id: "backend",
          related_config_keys: ["ACTIVE_PROVIDER"],
        },
        {
          id: "final-step",
          component: "response",
          action: "answer",
          status: "ok",
          stage: "execution",
          depends_on_step_id: "branch-a",
          related_service_id: "ui",
        },
      ],
    } as const;

    const collapsed = buildWorkflowGraph(systemState);
    const collapsedBranchNode = collapsed.nodes.find((node) => node.id === "execution-step:branch-a");
    const groupKey = (collapsedBranchNode?.data as { groupKey?: string } | undefined)?.groupKey;
    assert.equal(typeof groupKey, "string");

    const expanded = buildWorkflowGraph(systemState, {
      expandedGroupKeys: new Set([groupKey as string]),
    });

    const contract = {
      executionNodeIds: expanded.nodes
        .filter((node) => node.type === "execution_step")
        .map((node) => node.id)
        .sort(),
      relationKindCounts: expanded.edges.reduce<Record<string, number>>((acc, edge) => {
        const kind = (edge.data as { relationKind?: string } | undefined)?.relationKind ?? "none";
        acc[kind] = (acc[kind] ?? 0) + 1;
        return acc;
      }, {}),
      criticalEdgeIds: expanded.edges
        .map((edge) => edge.id)
        .filter((edgeId) =>
          edgeId.startsWith("domain-step:") ||
          edgeId.startsWith("runtime-step:") ||
          edgeId.startsWith("step-edge:"),
        )
        .sort(),
    };

    assert.deepEqual(contract, {
      executionNodeIds: [
        "execution-step:branch-a",
        "execution-step:branch-b",
        "execution-step:final-step",
        "execution-step:root-step",
      ],
      relationKindCounts: {
        domain: 3,
        runtime: 4,
        sequence: 3,
      },
      criticalEdgeIds: [
        "domain-step:intent->execution-step:root-step:INTENT_MODE",
        "domain-step:provider->execution-step:branch-a:ACTIVE_PROVIDER",
        "domain-step:provider->execution-step:branch-b:ACTIVE_PROVIDER",
        "runtime-step:runtime-service:backend->execution-step:branch-a",
        "runtime-step:runtime-service:backend->execution-step:branch-b",
        "runtime-step:runtime-service:backend->execution-step:root-step",
        "runtime-step:runtime-service:ui->execution-step:final-step",
        "step-edge:execution-step:branch-a->execution-step:final-step",
        "step-edge:execution-step:root-step->execution-step:branch-a",
        "step-edge:execution-step:root-step->execution-step:branch-b",
      ],
    });
  });
});

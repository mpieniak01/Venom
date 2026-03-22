import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildCanvasGraph } from "../components/workflow-control/canvas/layout";
import { buildWorkflowGraph } from "../lib/workflow-canvas-helpers";

const MULTIBRANCH_STATE = {
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

function relationContract(edges: Array<{ source: string; target: string; data?: unknown }>) {
  const relationKindCounts = edges.reduce<Record<string, number>>((acc, edge) => {
    const kind = (edge.data as { relationKind?: string } | undefined)?.relationKind ?? "none";
    acc[kind] = (acc[kind] ?? 0) + 1;
    return acc;
  }, {});
  const routingSignature = edges
    .map((edge) => {
      const kind = (edge.data as { relationKind?: string } | undefined)?.relationKind ?? "none";
      return `${edge.source}->${edge.target}:${kind}`;
    })
    .sort();
  return { relationKindCounts, routingSignature };
}

describe("workflow multibranch graph contract snapshot", () => {
  it("keeps collapsed multibranch topology + layout contract stable", () => {
    const graph = buildWorkflowGraph(MULTIBRANCH_STATE);
    const canvas = buildCanvasGraph(MULTIBRANCH_STATE, true);
    const nodeById = new Map(canvas.initialNodes.map((node) => [node.id, node]));
    const executionNodeIds = graph.nodes
      .filter((node) => node.type === "execution_step")
      .map((node) => node.id)
      .sort();

    const contract = {
      executionNodeIds,
      keyPositions: {
        backend: nodeById.get("runtime-service:backend")?.position,
        ui: nodeById.get("runtime-service:ui")?.position,
        root: nodeById.get("execution-step:root-step")?.position,
        branchA: nodeById.get("execution-step:branch-a")?.position,
        final: nodeById.get("execution-step:final-step")?.position,
      },
      ...relationContract(graph.edges),
    };

    assert.deepEqual(contract, {
      executionNodeIds: [
        "execution-step:branch-a",
        "execution-step:final-step",
        "execution-step:root-step",
      ],
      keyPositions: {
        backend: { x: 400, y: 340 },
        ui: { x: 660, y: 340 },
        root: { x: 660, y: 640 },
        branchA: { x: 920, y: 640 },
        final: { x: 1180, y: 640 },
      },
      relationKindCounts: {
        domain: 2,
        runtime: 3,
        sequence: 2,
      },
      routingSignature: [
        "control-domain:intent->execution-step:root-step:domain",
        "control-domain:provider->execution-step:branch-a:domain",
        "execution-step:branch-a->execution-step:final-step:sequence",
        "execution-step:root-step->execution-step:branch-a:sequence",
        "runtime-service:backend->execution-step:branch-a:runtime",
        "runtime-service:backend->execution-step:root-step:runtime",
        "runtime-service:ui->execution-step:final-step:runtime",
      ],
    });
  });

  it("keeps expanded multibranch topology + routing contract stable", () => {
    const collapsed = buildWorkflowGraph(MULTIBRANCH_STATE);
    const collapsedBranchNode = collapsed.nodes.find(
      (node) => node.id === "execution-step:branch-a",
    );
    const groupKey = (collapsedBranchNode?.data as { groupKey?: string } | undefined)?.groupKey;
    assert.equal(typeof groupKey, "string");

    const expandedOptions = { expandedGroupKeys: new Set([groupKey as string]) };
    const graph = buildWorkflowGraph(MULTIBRANCH_STATE, expandedOptions);
    const canvas = buildCanvasGraph(MULTIBRANCH_STATE, true, expandedOptions);
    const nodeById = new Map(canvas.initialNodes.map((node) => [node.id, node]));
    const executionNodeIds = graph.nodes
      .filter((node) => node.type === "execution_step")
      .map((node) => node.id)
      .sort();

    const contract = {
      executionNodeIds,
      keyPositions: {
        branchA: nodeById.get("execution-step:branch-a")?.position,
        branchB: nodeById.get("execution-step:branch-b")?.position,
      },
      ...relationContract(graph.edges),
    };

    assert.deepEqual(contract, {
      executionNodeIds: [
        "execution-step:branch-a",
        "execution-step:branch-b",
        "execution-step:final-step",
        "execution-step:root-step",
      ],
      keyPositions: {
        branchA: { x: 920, y: 640 },
        branchB: { x: 920, y: 728 },
      },
      relationKindCounts: {
        domain: 3,
        runtime: 4,
        sequence: 3,
      },
      routingSignature: [
        "control-domain:intent->execution-step:root-step:domain",
        "control-domain:provider->execution-step:branch-a:domain",
        "control-domain:provider->execution-step:branch-b:domain",
        "execution-step:branch-a->execution-step:final-step:sequence",
        "execution-step:root-step->execution-step:branch-a:sequence",
        "execution-step:root-step->execution-step:branch-b:sequence",
        "runtime-service:backend->execution-step:branch-a:runtime",
        "runtime-service:backend->execution-step:branch-b:runtime",
        "runtime-service:backend->execution-step:root-step:runtime",
        "runtime-service:ui->execution-step:final-step:runtime",
      ],
    });
  });
});

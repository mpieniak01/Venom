import type { Edge, Node } from "@xyflow/react";
import type { SystemState } from "@/types/workflow-control";

export function buildWorkflowGraph(systemState: SystemState | null): {
  nodes: Node[];
  edges: Edge[];
} {
  if (!systemState) {
    return { nodes: [], edges: [] };
  }

  const nodes: Node[] = [
    {
      id: "decision",
      type: "decision",
      data: {
        strategy: systemState.decision_strategy,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "intent",
      type: "intent",
      data: {
        intentMode: systemState.intent_mode,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "kernel",
      type: "kernel",
      data: {
        kernel: systemState.kernel,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "runtime",
      type: "runtime",
      data: {
        runtime: systemState.runtime,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "provider",
      type: "provider",
      data: {
        provider: systemState.provider,
      },
      position: { x: 0, y: 0 },
    },
    {
      id: "embedding",
      type: "embedding",
      data: {
        model: systemState.embedding_model,
      },
      position: { x: 0, y: 0 },
    },
  ];

  const edges: Edge[] = [
    { id: "e1", source: "decision", target: "intent", animated: true },
    { id: "e2", source: "intent", target: "kernel", animated: true },
    { id: "e3", source: "kernel", target: "runtime", animated: true },
    { id: "e4", source: "runtime", target: "embedding", animated: true },
    { id: "e5", source: "embedding", target: "provider", animated: true },
  ];

  return { nodes, edges };
}

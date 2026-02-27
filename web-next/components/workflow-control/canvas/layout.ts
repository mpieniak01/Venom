import type { Edge, Node } from "@xyflow/react";

import { buildWorkflowGraph } from "@/lib/workflow-canvas-helpers";
import type { SystemState } from "@/types/workflow-control";

import {
  LAYOUT_X_OFFSET,
  LAYOUT_X_START,
  STRICT_LAYOUT,
  SWIMLANE_HEIGHT,
  SWIMLANE_ORDER,
  SWIMLANE_WIDTH,
} from "./config";

export function buildCanvasGraph(
  systemState: SystemState | null,
  readOnly: boolean
): { initialNodes: Node[]; initialEdges: Edge[] } {
  const { nodes, edges } = buildWorkflowGraph(systemState);

  const backgroundSwimlanes: Node[] = SWIMLANE_ORDER.map((category, index) => ({
    id: `swimlane-${category}`,
    type: "swimlane",
    data: { label: category, index },
    position: { x: 0, y: index * SWIMLANE_HEIGHT },
    style: { width: SWIMLANE_WIDTH, height: SWIMLANE_HEIGHT },
    selectable: false,
    draggable: false,
    zIndex: 0,
  }));

  const positionedNodes: Node[] = nodes.map((node) => {
    const position = STRICT_LAYOUT[node.type || ""];
    if (!position) {
      return {
        ...node,
        draggable: !readOnly,
        selectable: !readOnly,
        zIndex: 20,
      };
    }

    return {
      ...node,
      parentId: `swimlane-${node.type}`,
      extent: "parent",
      position: {
        x: LAYOUT_X_START + position.x * LAYOUT_X_OFFSET,
        y: 25,
      },
      draggable: !readOnly,
      selectable: !readOnly,
      zIndex: 20,
    };
  });

  return {
    initialNodes: [...backgroundSwimlanes, ...positionedNodes],
    initialEdges: edges,
  };
}

export function graphSignature(nodes: Node[], edges: Edge[]): string {
  return JSON.stringify({
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data: node.data,
      parentId: node.parentId,
      draggable: node.draggable,
      selectable: node.selectable,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: edge.type,
    })),
  });
}

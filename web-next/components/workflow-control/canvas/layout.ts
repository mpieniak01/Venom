import type { Edge, Node } from "@xyflow/react";

import { buildWorkflowGraph, type BuildWorkflowGraphOptions } from "@/lib/workflow-canvas-helpers";
import type { SystemState } from "@/types/workflow-control";

import {
  LAYOUT_Y_OFFSET,
  LAYOUT_Y_START,
  LAYOUT_X_OFFSET,
  LAYOUT_X_START,
  STRICT_LAYOUT,
  SWIMLANE_HEIGHT,
  SWIMLANE_ORDER,
  SWIMLANE_WIDTH,
} from "./config";

export function buildCanvasGraph(
  systemState: SystemState | null,
  _readOnly: boolean,
  options?: BuildWorkflowGraphOptions,
): { initialNodes: Node[]; initialEdges: Edge[] } {
  void _readOnly;
  const { nodes, edges } = buildWorkflowGraph(systemState, options ?? {});
  const canvasReadOnly = true;

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

  const laneIndexForNode = (node: Node): number => {
    const canvasLane = (node.data as { canvasLane?: string } | undefined)?.canvasLane;
    if (canvasLane) {
      const laneIndex = SWIMLANE_ORDER.indexOf(canvasLane as (typeof SWIMLANE_ORDER)[number]);
      if (laneIndex >= 0) return laneIndex;
    }

    if (node.type === "runtime_service" || node.type === "runtime") return 1;
    if (node.type === "execution_step") return 2;
    return 0;
  };

  const positionedNodes: Node[] = nodes.map((node) => {
    const canvasData = (node.data as {
      canvasColumn?: number;
      canvasRow?: number;
      canvasLane?: string;
    } | undefined) ?? {};
    const strictPosition = STRICT_LAYOUT[node.type || ""];
    const laneIndex = laneIndexForNode(node);
    const column =
      typeof canvasData.canvasColumn === "number"
        ? canvasData.canvasColumn
        : strictPosition?.x ?? 0;
    const row =
      typeof canvasData.canvasRow === "number"
        ? canvasData.canvasRow
        : strictPosition?.row ?? 0;

    return {
      ...node,
      position: {
        x: LAYOUT_X_START + column * LAYOUT_X_OFFSET,
        y: laneIndex * SWIMLANE_HEIGHT + LAYOUT_Y_START + row * LAYOUT_Y_OFFSET,
      },
      draggable: !canvasReadOnly,
      selectable: !canvasReadOnly,
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
      selected: node.selected,
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

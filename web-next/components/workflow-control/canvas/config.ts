import { MarkerType, type DefaultEdgeOptions, type Node } from "@xyflow/react";

export const SWIMLANE_HEIGHT = 130;
export const SWIMLANE_WIDTH = 1400;

export const SWIMLANE_ORDER = [
  "decision",
  "intent",
  "kernel",
  "runtime",
  "embedding",
  "provider",
] as const;

export const STRICT_LAYOUT: Record<string, { x: number; y: number }> = {
  decision: { x: 0, y: 0 },
  intent: { x: 1, y: 1 },
  kernel: { x: 2, y: 2 },
  runtime: { x: 3, y: 3 },
  embedding: { x: 4, y: 4 },
  provider: { x: 5, y: 5 },
};

export const LAYOUT_X_START = 60;
export const LAYOUT_X_OFFSET = 210;

export const DEFAULT_EDGE_OPTIONS: DefaultEdgeOptions = {
  type: "smoothstep",
  markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  animated: true,
  style: { strokeWidth: 3, stroke: "#e2e8f0" },
};

export const FIT_VIEW_OPTIONS = {
  padding: 0.1,
  minZoom: 0.68,
  maxZoom: 1.35,
};

export const SWIMLANE_STYLES: Record<
  string,
  { bg: string; border: string; text: string; bgContent: string }
> = {
  decision: {
    bg: "bg-blue-900/40",
    border: "border-slate-700",
    text: "text-blue-400",
    bgContent: "bg-blue-900/5",
  },
  intent: {
    bg: "bg-yellow-900/40",
    border: "border-slate-700",
    text: "text-yellow-400",
    bgContent: "bg-yellow-900/5",
  },
  kernel: {
    bg: "bg-green-900/40",
    border: "border-slate-700",
    text: "text-green-400",
    bgContent: "bg-green-900/5",
  },
  runtime: {
    bg: "bg-purple-900/40",
    border: "border-slate-700",
    text: "text-purple-400",
    bgContent: "bg-purple-900/5",
  },
  provider: {
    bg: "bg-orange-900/40",
    border: "border-slate-700",
    text: "text-orange-400",
    bgContent: "bg-orange-900/5",
  },
  embedding: {
    bg: "bg-pink-900/40",
    border: "border-slate-700",
    text: "text-pink-400",
    bgContent: "bg-pink-900/5",
  },
};

export function miniMapNodeColor(node: Node): string {
  switch (node.type) {
    case "decision":
      return "#3b82f6";
    case "kernel":
      return "#22c55e";
    case "runtime":
      return "#a855f7";
    case "provider":
      return "#f97316";
    case "intent":
      return "#eab308";
    case "embedding":
      return "#ec4899";
    default:
      return "#334155";
  }
}

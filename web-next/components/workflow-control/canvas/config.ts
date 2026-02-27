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

export type WorkflowCanvasNodeType = (typeof SWIMLANE_ORDER)[number];

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

export const WORKFLOW_NODE_THEME: Record<
  WorkflowCanvasNodeType,
  {
    glowClass: string;
    shellClass: string;
    titleClass: string;
    handleClass: string;
  }
> = {
  decision: {
    glowClass: "border-blue-300/90 shadow-[0_0_24px_rgba(96,165,250,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-blue-500 bg-slate-900 px-8 py-6 text-blue-100 shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(59,130,246,0.5)]",
    titleClass: "text-blue-400",
    handleClass: "!h-3 !w-3 !bg-blue-500",
  },
  intent: {
    glowClass: "border-yellow-300/90 shadow-[0_0_24px_rgba(253,224,71,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-yellow-500 bg-slate-900 px-8 py-6 text-yellow-100 shadow-[0_0_15px_rgba(234,179,8,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(234,179,8,0.5)]",
    titleClass: "text-yellow-400",
    handleClass: "!h-3 !w-3 !bg-yellow-500",
  },
  kernel: {
    glowClass: "border-green-300/90 shadow-[0_0_24px_rgba(74,222,128,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-green-500 bg-slate-900 px-8 py-6 text-green-100 shadow-[0_0_15px_rgba(34,197,94,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(34,197,94,0.5)]",
    titleClass: "text-green-400",
    handleClass: "!h-3 !w-3 !bg-green-500",
  },
  runtime: {
    glowClass: "border-purple-300/90 shadow-[0_0_24px_rgba(196,181,253,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-purple-500 bg-slate-900 px-8 py-6 text-purple-100 shadow-[0_0_15px_rgba(168,85,247,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(168,85,247,0.5)]",
    titleClass: "text-purple-400",
    handleClass: "!h-3 !w-3 !bg-purple-500",
  },
  embedding: {
    glowClass: "border-pink-300/90 shadow-[0_0_24px_rgba(249,168,212,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-pink-500 bg-slate-900 px-8 py-6 text-pink-100 shadow-[0_0_15px_rgba(236,72,153,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(236,72,153,0.5)]",
    titleClass: "text-pink-400",
    handleClass: "!h-3 !w-3 !bg-pink-500",
  },
  provider: {
    glowClass: "border-orange-300/90 shadow-[0_0_24px_rgba(253,186,116,0.45)]",
    shellClass:
      "group relative flex h-[80px] min-w-[210px] flex-col justify-center rounded-xl border-2 border-orange-500 bg-slate-900 px-8 py-6 text-orange-100 shadow-[0_0_15px_rgba(249,115,22,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(249,115,22,0.5)]",
    titleClass: "text-orange-400",
    handleClass: "!h-3 !w-3 !bg-orange-500",
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

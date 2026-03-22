import { MarkerType, type DefaultEdgeOptions, type Node } from "@xyflow/react";

export const SWIMLANE_HEIGHT = 300;
export const SWIMLANE_WIDTH = 1800;

export const SWIMLANE_ORDER = [
  "control_domain",
  "runtime_service",
  "execution_step",
] as const;

export type WorkflowCanvasNodeType =
  | "decision"
  | "intent"
  | "kernel"
  | "runtime"
  | "provider"
  | "embedding"
  | "control_domain"
  | "runtime_service"
  | "execution_step";

export const STRICT_LAYOUT: Record<string, { x: number; lane: (typeof SWIMLANE_ORDER)[number]; row?: number }> = {
  control_domain: { x: 0, lane: "control_domain", row: 0 },
  runtime_service: { x: 1, lane: "runtime_service", row: 0 },
  execution_step: { x: 2, lane: "execution_step", row: 0 },
};

export const LAYOUT_X_START = 140;
export const LAYOUT_X_OFFSET = 260;
export const LAYOUT_Y_START = 40;
export const LAYOUT_Y_OFFSET = 88;

export const DEFAULT_EDGE_OPTIONS: DefaultEdgeOptions = {
  type: "workflow_relation",
  markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
  animated: false,
  style: { strokeWidth: 3.5, stroke: "#e2e8f0" },
};

export const FIT_VIEW_OPTIONS = {
  padding: 0.14,
  minZoom: 0.58,
  maxZoom: 1.35,
};

export const SWIMLANE_STYLES: Record<
  string,
  { bg: string; border: string; text: string; bgContent: string }
> = {
  control_domain: {
    bg: "bg-cyan-900/40",
    border: "border-slate-700",
    text: "text-cyan-400",
    bgContent: "bg-cyan-900/5",
  },
  runtime_service: {
    bg: "bg-violet-900/40",
    border: "border-slate-700",
    text: "text-violet-400",
    bgContent: "bg-violet-900/5",
  },
  execution_step: {
    bg: "bg-emerald-900/40",
    border: "border-slate-700",
    text: "text-emerald-400",
    bgContent: "bg-emerald-900/5",
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
  control_domain: {
    glowClass: "border-cyan-300/90 shadow-[0_0_24px_rgba(34,211,238,0.4)]",
    shellClass:
      "group relative flex min-h-[98px] min-w-[220px] flex-col justify-center rounded-xl border-2 border-cyan-500 bg-slate-900 px-5 py-4 text-cyan-100 shadow-[0_0_15px_rgba(6,182,212,0.28)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(6,182,212,0.4)]",
    titleClass: "text-cyan-300",
    handleClass: "!h-3 !w-3 !bg-cyan-500",
  },
  runtime_service: {
    glowClass: "border-violet-300/90 shadow-[0_0_24px_rgba(196,181,253,0.45)]",
    shellClass:
      "group relative flex min-h-[106px] min-w-[230px] flex-col justify-center rounded-xl border-2 border-violet-500 bg-slate-900 px-5 py-4 text-violet-100 shadow-[0_0_15px_rgba(168,85,247,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(168,85,247,0.45)]",
    titleClass: "text-violet-300",
    handleClass: "!h-3 !w-3 !bg-violet-500",
  },
  execution_step: {
    glowClass: "border-emerald-300/90 shadow-[0_0_24px_rgba(110,231,183,0.45)]",
    shellClass:
      "group relative flex min-h-[118px] min-w-[250px] flex-col justify-center rounded-xl border-2 border-emerald-500 bg-slate-900 px-5 py-4 text-emerald-100 shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-shadow duration-300 hover:shadow-[0_0_25px_rgba(16,185,129,0.45)]",
    titleClass: "text-emerald-300",
    handleClass: "!h-3 !w-3 !bg-emerald-500",
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
    case "control_domain":
      return "#22d3ee";
    case "runtime_service":
      return "#a78bfa";
    case "execution_step":
      return "#34d399";
    default:
      return "#334155";
  }
}

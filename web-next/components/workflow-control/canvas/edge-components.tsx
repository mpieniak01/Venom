import {
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  type EdgeProps,
  type EdgeTypes,
} from "@xyflow/react";

type WorkflowRelationData = {
  relationKind?: "domain" | "runtime" | "sequence";
  relationLabel?: string;
};

export function relationTheme(kind: WorkflowRelationData["relationKind"]): {
  stroke: string;
  glow: string;
  labelClassName: string;
  borderRadius: number;
  offset: number;
  strokeDasharray?: string;
} {
  if (kind === "domain") {
    return {
      stroke: "#22d3ee",
      glow: "drop-shadow-[0_0_8px_rgba(34,211,238,0.45)]",
      labelClassName: "border-cyan-400/25 bg-cyan-500/12 text-cyan-100",
      borderRadius: 22,
      offset: 34,
      strokeDasharray: "8 5",
    };
  }
  if (kind === "runtime") {
    return {
      stroke: "#a78bfa",
      glow: "drop-shadow-[0_0_8px_rgba(167,139,250,0.4)]",
      labelClassName: "border-violet-400/25 bg-violet-500/12 text-violet-100",
      borderRadius: 20,
      offset: 30,
    };
  }
  return {
    stroke: "#34d399",
    glow: "drop-shadow-[0_0_8px_rgba(52,211,153,0.35)]",
    labelClassName: "border-emerald-400/25 bg-emerald-500/12 text-emerald-100",
    borderRadius: 16,
    offset: 24,
  };
}

export function WorkflowRelationEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps) {
  const relation = (data ?? {}) as WorkflowRelationData;
  const theme = relationTheme(relation.relationKind);
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    borderRadius: theme.borderRadius,
    offset: theme.offset,
  });
  return (
    <>
      <BaseEdge
        id={`${id}-glow`}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: theme.stroke,
          strokeWidth: 10,
          opacity: 0.18,
          strokeLinecap: "round",
          strokeLinejoin: "round",
        }}
        className={theme.glow}
      />
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: theme.stroke,
          strokeWidth: 3.5,
          strokeDasharray: theme.strokeDasharray,
          strokeLinecap: "round",
          strokeLinejoin: "round",
        }}
        className={theme.glow}
      />
      {relation.relationLabel ? (
        <EdgeLabelRenderer>
          <div
            className="pointer-events-none absolute -translate-x-1/2 -translate-y-1/2"
            style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          >
            <span
              className={[
                "rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] shadow-lg backdrop-blur-sm",
                theme.labelClassName,
              ].join(" ")}
            >
              {relation.relationLabel}
            </span>
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

export const workflowCanvasEdgeTypes: EdgeTypes = {
  workflow_relation: WorkflowRelationEdge,
};

"use client";

import type {
  AnalysisPhase,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
} from "@/components/inspector/model-introspection-dashboard-types";

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

export function clampPercent(value: number): number {
  if (Number.isFinite(value) && !Number.isNaN(value)) {
    return Math.max(0, Math.min(100, value));
  }
  return 0;
}

export function shortenTraceId(requestId: string | null | undefined): string {
  if (!requestId) {
    return "—";
  }
  if (requestId.length > 8) {
    return `${requestId.slice(0, 8)}…`;
  }
  return requestId;
}

export function timelineBadgeTone(status: string): BadgeTone {
  if (status === "done") {
    return "success";
  }
  if (status === "running") {
    return "warning";
  }
  return "neutral";
}

export function splitAnswerHighlights(answer: string): string[] {
  if (!answer.trim()) {
    return [];
  }
  return answer
    .replace(/\s+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((segment) => segment.trim())
    .filter(Boolean)
    .slice(0, 4);
}

export function getPhaseTone(phase: AnalysisPhase): BadgeTone {
  if (phase === "completed") {
    return "success";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "warning";
  }
  return "neutral";
}

export function getPhaseLabel(phase: AnalysisPhase): string {
  if (phase === "first_chunk") {
    return "first chunk";
  }
  return phase;
}

export function getAnalysisPhase(args: {
  analysisVisible: boolean;
  analysisLoading: boolean;
  analysisStatus: string | undefined;
  timelineHasResponseFinalized: boolean;
  firstChunkMs: number | null;
  chunkCount: number;
}): AnalysisPhase {
  const {
    analysisVisible,
    analysisLoading,
    analysisStatus,
    timelineHasResponseFinalized,
    firstChunkMs,
    chunkCount,
  } = args;
  if (analysisVisible) {
    if (analysisStatus === "completed" || timelineHasResponseFinalized) {
      return "completed";
    }
    if (analysisStatus === "running") {
      if (chunkCount > 0) {
        return "streaming";
      }
      return "requesting";
    }
    if (firstChunkMs != null || chunkCount > 0) {
      return "first_chunk";
    }
    return "idle";
  }
  if (analysisLoading) {
    return "requesting";
  }
  return "idle";
}

export function getAnswerTone(
  answer: string,
  analysisVisible: boolean,
): BadgeTone {
  if (analysisVisible && answer) {
    return /potrzebuj|need more context|more context/i.test(answer)
      ? "warning"
      : "success";
  }
  return "neutral";
}

export function getPackageRingColor(packageCoveragePercent: number): string {
  if (packageCoveragePercent >= 100) {
    return "#047857";
  }
  if (packageCoveragePercent >= 80) {
    return "#059669";
  }
  return "#f59e0b";
}

export function getOrbCoreShadow(phase: AnalysisPhase): string {
  if (phase === "completed") {
    return "0 0 16px rgba(4,120,87,0.26)";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "0 0 18px rgba(6,182,212,0.28)";
  }
  if (phase === "requesting") {
    return "0 0 18px rgba(245,158,11,0.28)";
  }
  return "0 0 14px rgba(113,113,122,0.22)";
}

export function getAnalysisProgressBarColor(phase: AnalysisPhase): string {
  if (phase === "completed") {
    return "#10b981";
  }
  if (phase === "streaming" || phase === "first_chunk") {
    return "#06b6d4";
  }
  if (phase === "requesting") {
    return "#f59e0b";
  }
  return "#71717a";
}

export function getGraphNodeTone(status: string): BadgeTone {
  if (status === "available" || status === "connected" || status === "ready") {
    return "success";
  }
  if (status === "missing" || status === "offline") {
    return "warning";
  }
  return "neutral";
}

export function computeAnalysisProgress(args: {
  analysisVisible: boolean;
  analysisTimelineProgress: number;
  analysisStepCount: number;
  chunkCount: number;
  firstChunkMs: number | null | undefined;
  elapsedMs: number;
  analysisStatus: string | undefined;
}): number {
  const {
    analysisVisible,
    analysisTimelineProgress,
    analysisStepCount,
    chunkCount,
    firstChunkMs,
    elapsedMs,
    analysisStatus,
  } = args;
  if (!analysisVisible) {
    return 0;
  }
  if (analysisTimelineProgress > 0) {
    return clampPercent(analysisTimelineProgress);
  }
  const estimatedProgress = Math.min(
    100,
    analysisStepCount * 18 + (firstChunkMs == null ? 0 : 20),
  );
  const noChunkYet = chunkCount === 0 && firstChunkMs == null;
  if (analysisStatus === "running" && noChunkYet) {
    const waitingProgress = 30 + Math.min(50, elapsedMs / 250);
    return clampPercent(Math.max(estimatedProgress, waitingProgress));
  }
  if (noChunkYet) {
    return clampPercent(Math.min(estimatedProgress, 30));
  }
  return clampPercent(estimatedProgress);
}

export function getOrbSubtitle(args: {
  analysisStatus: string | undefined;
  analysisActive: boolean;
  chunkCount: number;
  analysisStepCount: number;
  idleLabel: string;
}): string {
  const {
    analysisStatus,
    analysisActive,
    chunkCount,
    analysisStepCount,
    idleLabel,
  } = args;
  if (analysisStatus === "completed") {
    return `${chunkCount} chunk(s) · ${analysisStepCount} step(s) · completed`;
  }
  if (analysisActive) {
    return `${chunkCount} chunk(s) · ${analysisStepCount} step(s)`;
  }
  return idleLabel;
}

export function getAnswerStatusLabel(args: {
  response: string;
  analysisRunning: boolean;
}): string {
  if (args.response) {
    return "model answered";
  }
  if (args.analysisRunning) {
    return "streaming answer";
  }
  return "awaiting answer";
}

export function getTypeHintText(kind: string): string {
  if (kind === "package") {
    return "Package drilldown uses the same snapshot as runtime health, so it is safe to inspect without triggering extra probes.";
  }
  if (kind === "reuse") {
    return "Reuse drilldown helps confirm that Brain and diagnostics stay shared rather than duplicated.";
  }
  return "Runtime drilldown summarizes the active runtime, model and analysis attachment points.";
}

function formatElapsedDetails(args: {
  analysisVisible: boolean;
  analysisElapsedMs: number;
}): string {
  const { analysisVisible, analysisElapsedMs } = args;
  if (analysisVisible) {
    return `${analysisElapsedMs.toFixed(1)} ms`;
  }
  return "—";
}

function getRuntimeGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Runtime details",
    lines: [
      `Provider: ${snapshot.runtime.provider}`,
      `Model: ${snapshot.runtime.model}`,
      `Endpoint: ${snapshot.runtime.endpoint ?? "local"}`,
      `Service type: ${snapshot.runtime.service_type}`,
      `Mode: ${snapshot.runtime.mode}`,
    ],
  };
}

function getModelGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Model details",
    lines: [
      `Active model: ${snapshot.summary.active_model}`,
      `Runtime label: ${snapshot.summary.runtime_label}`,
      `Drift issues: ${snapshot.runtime_drift.issues.length}`,
    ],
  };
}

function getAnalysisGraphNodeDetails(args: {
  analysisMechanismEnabled: boolean;
  analysisStatus: string | undefined;
  analysisVisible: boolean;
  analysisChunkCount: number;
  analysisElapsedMs: number;
}): GraphNodeDetails {
  const {
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  } = args;
  return {
    title: "Analysis details",
    lines: [
      `Mechanism: ${analysisMechanismEnabled ? "enabled" : "disabled"}`,
      `Status: ${analysisStatus ?? "idle"}`,
      `Content chunks: ${analysisVisible ? analysisChunkCount : 0}`,
      `Elapsed: ${formatElapsedDetails({ analysisVisible, analysisElapsedMs })}`,
    ],
  };
}

function getManagerGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "ModelManager details",
    lines: [
      `Available: ${snapshot.model_manager.available ? "yes" : "no"}`,
      `Metrics: ${snapshot.model_manager.usage_metrics ? "present" : "absent"}`,
      `Error: ${snapshot.model_manager.error ?? "—"}`,
    ],
  };
}

function getBrainGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Reuse details",
    lines: [
      `Path: ${snapshot.reuse.brain.path}`,
      `Available: ${snapshot.reuse.brain.available ? "yes" : "no"}`,
      `Purpose: ${snapshot.reuse.brain.purpose}`,
    ],
  };
}

function getDiagnosticsGraphNodeDetails(snapshot: IntrospectionSnapshot): GraphNodeDetails {
  return {
    title: "Diagnostics reuse",
    lines: snapshot.reuse.diagnostics.map((entry) => `${entry.id}: ${entry.purpose}`),
  };
}

function getPackageGraphNodeDetails(args: {
  snapshot: IntrospectionSnapshot;
  selectedGraphNode: { id: string; label: string; kind: string; status: string };
}): GraphNodeDetails {
  const { snapshot, selectedGraphNode } = args;
  const packageKey = selectedGraphNode.id.replaceAll("package:", "");
  const packageNode = snapshot.packages[packageKey];
  if (packageNode) {
    return {
      title: "Package details",
      lines: [
        `Package: ${packageNode.package}`,
        `Module: ${packageNode.module}`,
        `Available: ${packageNode.available ? "yes" : "no"}`,
        `Version: ${packageNode.version ?? "n/a"}`,
      ],
    };
  }
  return {
    title: "Package details",
    lines: [`Node: ${selectedGraphNode.label}`, `Status: ${selectedGraphNode.status}`],
  };
}

export function resolveSelectedGraphNodeDetails(args: {
  snapshot: IntrospectionSnapshot;
  selectedGraphNode: { id: string; label: string; kind: string; status: string };
  analysisMechanismEnabled: boolean;
  analysisStatus: string | undefined;
  analysisVisible: boolean;
  analysisChunkCount: number;
  analysisElapsedMs: number;
}): GraphNodeDetails {
  const {
    snapshot,
    selectedGraphNode,
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  } = args;

  const nodeId = selectedGraphNode.id;
  if (nodeId === "runtime") return getRuntimeGraphNodeDetails(snapshot);
  if (nodeId === "model") return getModelGraphNodeDetails(snapshot);
  if (nodeId === "analysis") {
    return getAnalysisGraphNodeDetails({
      analysisMechanismEnabled,
      analysisStatus,
      analysisVisible,
      analysisChunkCount,
      analysisElapsedMs,
    });
  }
  if (nodeId === "manager") return getManagerGraphNodeDetails(snapshot);
  if (nodeId === "brain") return getBrainGraphNodeDetails(snapshot);
  if (nodeId === "diagnostics") return getDiagnosticsGraphNodeDetails(snapshot);
  return getPackageGraphNodeDetails({ snapshot, selectedGraphNode });
}

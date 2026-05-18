"use client";

import { useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { Brain, Radar, RefreshCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { useModelIntrospectionMechanism } from "@/components/inspector/model-introspection-mechanism";
import type {
  AnalysisTimelineEntry,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
  SnapshotComparison,
} from "@/components/inspector/model-introspection-dashboard-types";
import {
  buildAttentionModel,
  buildOperatorConclusion,
  buildOperatorRunbookSteps,
  buildLogitLensModel,
  buildSaliencyModel,
  buildRagFocusModel,
  computeAnalysisProgress,
  formatCount,
  getAnalysisPhase,
  getAnswerStatusLabel,
  getAnswerTone,
  getFallbackSignalTone,
  getOperatorFinalStatusTone,
  getOperatorStreamModeTone,
  getOrbSubtitle,
  getTypeHintText,
  resolveFallbackSignal,
  resolveOperatorFinalStatus,
  resolveOperatorStreamMode,
  resolveSelectedGraphNodeDetails,
  splitAnswerHighlights,
} from "@/components/inspector/model-introspection-dashboard-view-model";
import { useModelIntrospectionSnapshot } from "@/components/inspector/use-model-introspection-snapshot";
import { useModelIntrospectionAnalysisStream } from "@/components/inspector/use-model-introspection-analysis-stream";
import {
  AnalysisInputPanel,
  AnalysisLiveResponsePanel,
  AnalysisOrbPanel,
  AttentionPanel,
  LogitLensPanel,
  SaliencyPanel,
  RagFocusPanel,
  AnalysisResultsPanel,
  GraphPanel,
  SnapshotComparisonPanel,
} from "@/components/inspector/model-introspection-dashboard-sections";

type SummaryCard = {
  label: string;
  value: string;
  hint: string;
  accent: "violet" | "green" | "blue" | "indigo";
};

type RunTrends = {
  runs: number;
  window: number;
  runtimeTraceRate: number;
  probeRuntimeRate: number;
  highCoverageRate: number;
  liveStreamingRate: number;
  avgFirstContentMs: number | null;
  avgNoiseRatio: number | null;
};

type OperatorChecklistItem = {
  id: string;
  label: string;
  status: "ok" | "warn";
  detail: string;
};

type InternalsVerdictValue = "full" | "partial" | "fallback_only";
type ProbeCapability = {
  available?: boolean;
  reason?: string;
};
type InternalsCapabilityRow = {
  label: string;
  available: boolean;
  reason: string;
};

function resolveInternalsVerdictPresentation(
  verdict: string | undefined,
): { label: string; tone: BadgeTone } {
  const normalized: InternalsVerdictValue =
    verdict === "full" || verdict === "partial" || verdict === "fallback_only"
      ? verdict
      : "fallback_only";
  if (normalized === "full") {
    return { label: "internals full", tone: "success" };
  }
  if (normalized === "partial") {
    return { label: "internals partial", tone: "warning" };
  }
  return { label: "internals fallback", tone: "neutral" };
}

function resolveProbeBudgetLabel(internalsProbeElapsedMs: number | null): string {
  if (internalsProbeElapsedMs == null) {
    return "probe budget unknown";
  }
  return `probe budget ~${internalsProbeElapsedMs.toFixed(1)} ms`;
}

function sumProbeElapsedMs(values: Array<number | null | undefined>): number | null {
  const numericValues = values.filter(
    (value): value is number => typeof value === "number",
  );
  if (numericValues.length === 0) {
    return null;
  }
  return numericValues.reduce((sum, value) => sum + value, 0);
}

function buildInternalsCapabilityRow(
  label: string,
  capability: ProbeCapability | undefined,
): InternalsCapabilityRow {
  const available = Boolean(capability?.available);
  const rawReason = String(capability?.reason || "unknown");
  const reasonMap: Record<string, string> = {
    ok: "ok",
    probe_unavailable: "probe unavailable",
    probe_failed: "probe failed",
    attention_unavailable: "attention unavailable",
    saliency_unavailable: "saliency unavailable",
    logit_lens_unavailable: "logit lens unavailable",
    attention_proxy_logits: "recovered via logits proxy",
    saliency_proxy_attention: "recovered via attention proxy",
    saliency_proxy_logits: "recovered via logits proxy",
  };
  const mappedReason = reasonMap[rawReason] ?? rawReason.replaceAll("_", " ");
  return {
    label,
    available,
    reason: available && mappedReason === "ok" ? "ok" : mappedReason,
  };
}

function buildProbeLimitsLabel(limits: {
  timeout_seconds?: number;
  max_attempts?: number;
  max_top_k?: number;
  max_layer_count?: number;
  max_head_count?: number;
  max_prompt_tokens?: number;
} | null | undefined): string {
  if (!limits) {
    return "limits: n/a";
  }
  return `limits: t=${limits.timeout_seconds ?? 0}s · att=${limits.max_attempts ?? 0} · top_k=${limits.max_top_k ?? 0} · layers=${limits.max_layer_count ?? 0} · heads=${limits.max_head_count ?? 0} · prompt=${limits.max_prompt_tokens ?? 0}`;
}

function buildRunTrends(payload: unknown): RunTrends | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const candidate = payload as Record<string, unknown>;
  const runs = typeof candidate.runs === "number" ? candidate.runs : 0;
  if (runs <= 0) {
    return null;
  }
  return {
    runs,
    window: typeof candidate.window === "number" ? candidate.window : runs,
    runtimeTraceRate:
      typeof candidate.runtime_trace_rate === "number"
        ? candidate.runtime_trace_rate
        : 0,
    probeRuntimeRate:
      typeof candidate.probe_runtime_rate === "number"
        ? candidate.probe_runtime_rate
        : 0,
    highCoverageRate:
      typeof candidate.high_coverage_rate === "number"
        ? candidate.high_coverage_rate
        : 0,
    liveStreamingRate:
      typeof candidate.live_streaming_rate === "number"
        ? candidate.live_streaming_rate
        : 0,
    avgFirstContentMs:
      typeof candidate.avg_first_content_ms === "number"
        ? candidate.avg_first_content_ms
        : null,
    avgNoiseRatio:
      typeof candidate.avg_noise_ratio === "number"
        ? candidate.avg_noise_ratio
        : null,
  };
}

function resolveSummaryStats(
  snapshot: IntrospectionSnapshot | null,
  t: (key: string) => string,
): SummaryCard[] {
  if (!snapshot) {
    return [];
  }
  return buildSummaryCards({ snapshot, t });
}

function resolveAnalysisTimeline(
  analysisVisible: boolean,
  timeline: AnalysisTimelineEntry[] | undefined,
): AnalysisTimelineEntry[] {
  if (!analysisVisible) {
    return [];
  }
  return timeline ?? [];
}

function resolveSelectedGraphNodeIdEffective(args: {
  nodes: Array<{ id: string }>;
  selectedGraphNodeId: string | null;
}): string | null {
  const { nodes, selectedGraphNodeId } = args;
  if (nodes.length === 0) {
    return null;
  }
  const selectedExists = Boolean(
    selectedGraphNodeId && nodes.some((node) => node.id === selectedGraphNodeId),
  );
  if (selectedExists) {
    return selectedGraphNodeId;
  }
  return nodes[0]?.id ?? null;
}

function resolveSelectedGraphNode(args: {
  nodes: Array<{ id: string; label: string; kind: string; status: string }>;
  selectedGraphNodeIdEffective: string | null;
}): { id: string; label: string; kind: string; status: string } | null {
  const { nodes, selectedGraphNodeIdEffective } = args;
  if (nodes.length === 0 || !selectedGraphNodeIdEffective) {
    return null;
  }
  return nodes.find((node) => node.id === selectedGraphNodeIdEffective) ?? null;
}

function resolveSelectedGraphTypeHint(
  selectedGraphNode: { kind: string } | null,
): string {
  if (!selectedGraphNode) {
    return "";
  }
  return getTypeHintText(selectedGraphNode.kind);
}

function buildOperatorChecklist(args: {
  ragSource: string;
  probeSource: string;
  coveragePercent: number | null;
  streamQuality: string | undefined;
  partial: boolean | undefined;
  t: (key: string, replacements?: Record<string, string | number>) => string;
}): OperatorChecklistItem[] {
  const { ragSource, probeSource, coveragePercent, streamQuality, partial, t } = args;
  const streamQualityLabel =
    streamQuality &&
    [
      "pending",
      "live_streaming",
      "single_chunk",
      "single_chunk_delayed",
      "buffered_delivery",
      "no_content",
    ].includes(streamQuality)
      ? t(`inspector.modelIntrospection.dashboard.analysis.streamMode.${streamQuality}`)
      : streamQuality ?? t("inspector.modelIntrospection.dashboard.results.telemetry.unknown");
  return [
    {
      id: "trace",
      label: t("inspector.modelIntrospection.dashboard.results.checklist.traceLabel"),
      status: ragSource === "runtime_trace" ? "ok" : "warn",
      detail:
        ragSource === "runtime_trace"
          ? t("inspector.modelIntrospection.dashboard.results.checklist.traceOk")
          : t("inspector.modelIntrospection.dashboard.results.checklist.traceWarn"),
    },
    {
      id: "probe",
      label: t("inspector.modelIntrospection.dashboard.results.checklist.probeLabel"),
      status: probeSource === "probe_runtime" ? "ok" : "warn",
      detail:
        probeSource === "probe_runtime"
          ? t("inspector.modelIntrospection.dashboard.results.checklist.probeOk")
          : t("inspector.modelIntrospection.dashboard.results.checklist.probeWarn"),
    },
    {
      id: "coverage",
      label: t("inspector.modelIntrospection.dashboard.results.checklist.coverageLabel"),
      status: (coveragePercent ?? 0) >= 60 ? "ok" : "warn",
      detail: t(
        "inspector.modelIntrospection.dashboard.results.checklist.coverageDetail",
        { value: (coveragePercent ?? 0).toFixed(1) },
      ),
    },
    {
      id: "stream",
      label: t("inspector.modelIntrospection.dashboard.results.checklist.streamLabel"),
      status:
        streamQuality === "live_streaming" || streamQuality === "single_chunk"
          ? "ok"
          : "warn",
      detail: t(
        "inspector.modelIntrospection.dashboard.results.checklist.streamDetail",
        { value: streamQualityLabel },
      ),
    },
    {
      id: "partial",
      label: t("inspector.modelIntrospection.dashboard.results.checklist.partialLabel"),
      status: partial ? "warn" : "ok",
      detail: partial
        ? t("inspector.modelIntrospection.dashboard.results.checklist.partialWarn")
        : t("inspector.modelIntrospection.dashboard.results.checklist.partialOk"),
    },
  ];
}

function buildSummaryCards(args: {
  snapshot: IntrospectionSnapshot;
  t: (key: string) => string;
}): SummaryCard[] {
  const { snapshot, t } = args;
  const packages = snapshot.packages;
  const availableCount = snapshot.available_packages.length;
  const missingCount = snapshot.missing_packages.length;
  const driftCount = snapshot.runtime_drift.issues.length;
  const probeStatus = snapshot.probe?.status ?? "n/a";
  const probeProfile = snapshot.probe?.profile ?? "n/a";
  return [
    {
      label: t("inspector.modelIntrospection.summary.runtime"),
      value: snapshot.summary.runtime_label,
      hint: snapshot.summary.provider,
      accent: "violet",
    },
    {
      label: t("inspector.modelIntrospection.summary.packages"),
      value: formatCount(availableCount),
      hint: `${formatCount(Object.keys(packages).length)} total`,
      accent: "green",
    },
    {
      label: t("inspector.modelIntrospection.summary.missing"),
      value: formatCount(missingCount),
      hint: snapshot.runtime_drift.drift_detected
        ? `${driftCount} drift issue(s)`
        : t("inspector.modelIntrospection.dashboard.runtimeContext.clean"),
      accent: "blue",
    },
    {
      label: t("inspector.modelIntrospection.dashboard.runtimeContext.manager"),
      value: snapshot.model_manager.available
        ? t("inspector.modelIntrospection.dashboard.runtimeContext.connected")
        : t("inspector.modelIntrospection.dashboard.runtimeContext.offline"),
      hint:
        snapshot.model_manager.error ??
        t("inspector.modelIntrospection.dashboard.runtimeContext.readOnly"),
      accent: "indigo",
    },
    {
      label: t("inspector.modelIntrospection.dashboard.runtimeContext.probe"),
      value: probeStatus,
      hint: `profile:${probeProfile}`,
      accent: "blue",
    },
  ];
}

function buildSnapshotComparison(args: {
  snapshot: IntrospectionSnapshot | null;
  analysisCompleted: boolean;
  snapshotAfter: IntrospectionSnapshot | undefined;
}): SnapshotComparison | null {
  const { snapshot, analysisCompleted, snapshotAfter } = args;
  if (!snapshot || !analysisCompleted) {
    return null;
  }
  const before = snapshot;
  const after = snapshotAfter ?? snapshot;
  return {
    before: {
      label: before.summary.runtime_label,
      drift: before.runtime_drift.drift_detected,
      available_packages: before.available_packages.length,
      missing_packages: before.missing_packages.length,
      issues: before.runtime_drift.issues.length,
    },
    after: {
      label: after.summary.runtime_label,
      drift: after.runtime_drift.drift_detected,
      available_packages: after.available_packages.length,
      missing_packages: after.missing_packages.length,
      issues: after.runtime_drift.issues.length,
    },
    delta: {
      available_packages:
        after.available_packages.length - before.available_packages.length,
      missing_packages:
        after.missing_packages.length - before.missing_packages.length,
      issues: after.runtime_drift.issues.length - before.runtime_drift.issues.length,
    },
  };
}

function resolveGraphDetails(args: {
  snapshot: IntrospectionSnapshot | null;
  selectedGraphNode:
    | { id: string; label: string; kind: string; status: string }
    | null;
  analysisMechanismEnabled: boolean;
  analysisStatus: string | undefined;
  analysisVisible: boolean;
  analysisChunkCount: number;
  analysisElapsedMs: number;
}): GraphNodeDetails | null {
  const {
    snapshot,
    selectedGraphNode,
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  } = args;
  if (!snapshot || !selectedGraphNode) {
    return null;
  }
  return resolveSelectedGraphNodeDetails({
    snapshot,
    selectedGraphNode,
    analysisMechanismEnabled,
    analysisStatus,
    analysisVisible,
    analysisChunkCount,
    analysisElapsedMs,
  });
}

function useDashboardDerivedState(args: {
  snapshot: IntrospectionSnapshot | null;
  t: (key: string, replacements?: Record<string, string | number>) => string;
  analysisResult: ReturnType<typeof useModelIntrospectionAnalysisStream>["analysisResult"];
  analysisLoading: boolean;
  analysisPrompt: string;
  analysisMechanismEnabled: boolean;
  selectedGraphNodeId: string | null;
}) {
  const {
    snapshot,
    t,
    analysisResult,
    analysisLoading,
    analysisPrompt,
    analysisMechanismEnabled,
    selectedGraphNodeId,
  } = args;
  const stats = useMemo(() => resolveSummaryStats(snapshot, t), [snapshot, t]);
  const analysisVisible = Boolean(analysisResult?.analysis);
  const analysisRunning = analysisResult?.status === "running";
  const analysisActive = analysisResult?.status === "running";
  const analysisCompleted = analysisResult?.status === "completed" && analysisVisible;
  const analysisComparison = useMemo(() => {
    return buildSnapshotComparison({
      snapshot,
      analysisCompleted,
      snapshotAfter: analysisResult?.snapshot_after,
    });
  }, [analysisCompleted, analysisResult?.snapshot_after, snapshot]);
  const analysisResponse = analysisResult?.analysis?.response ?? "";
  const analysisSourceResponse = analysisVisible ? analysisResponse : "";
  const analysisHighlights = useMemo(
    () => splitAnswerHighlights(analysisSourceResponse),
    [analysisSourceResponse],
  );
  const analysisTimeline = useMemo(
    () => resolveAnalysisTimeline(analysisVisible, analysisResult?.analysis?.timeline),
    [analysisVisible, analysisResult?.analysis?.timeline],
  );
  const analysisProcess = analysisResult?.analysis?.process ?? null;
  const analysisTimelineStepCount =
    analysisResult?.analysis?.timeline_step_count ?? analysisTimeline.length;
  const analysisTraceStepCount =
    analysisProcess?.trace_step_count ?? analysisProcess?.step_count ?? 0;
  const analysisTimelineFirstChunk =
    analysisTimeline.find((entry) => entry.id === "first_chunk") ?? null;
  const analysisTimelineResponseFinalized =
    analysisTimeline.find((entry) => entry.id === "response_finalized") ?? null;
  const analysisTimelineProgress = analysisTimeline.reduce((current, entry) => {
    return typeof entry.progress === "number" ? entry.progress : current;
  }, 0);
  const analysisFirstChunkMs =
    analysisProcess?.first_chunk_ms ??
    analysisTimelineFirstChunk?.at_ms ??
    analysisResult?.analysis?.response_received_ms ??
    null;
  const analysisStepCount = analysisTimelineStepCount;
  const analysisTraceId = analysisProcess?.request_id ?? null;
  const analysisStreaming = analysisRunning && analysisVisible;
  const analysisPhase = getAnalysisPhase({
    analysisVisible,
    analysisLoading,
    analysisStatus: analysisResult?.status,
    timelineHasResponseFinalized: analysisTimelineResponseFinalized != null,
    firstChunkMs: analysisFirstChunkMs,
    chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
  });
  const analysisAnswerTone = getAnswerTone(analysisResponse, analysisVisible);
  const answerStatusLabel = getAnswerStatusLabel({
    response: analysisResponse,
    analysisRunning,
    answeredLabel: t("inspector.modelIntrospection.dashboard.results.answerStatus.answered"),
    streamingLabel: t("inspector.modelIntrospection.dashboard.results.answerStatus.streaming"),
    awaitingLabel: t("inspector.modelIntrospection.dashboard.results.answerStatus.awaiting"),
  });
  const operatorFinalStatus = resolveOperatorFinalStatus({
    analysisStatus: analysisResult?.status,
    analysisVisible,
  });
  const operatorFinalStatusTone = getOperatorFinalStatusTone(operatorFinalStatus);
  const operatorStreamMode = resolveOperatorStreamMode({
    analysisVisible,
    chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
    firstChunkMs: analysisFirstChunkMs,
  });
  const operatorStreamModeTone = getOperatorStreamModeTone(operatorStreamMode);
  const fallbackSignal = resolveFallbackSignal({
    adapterApplied: analysisProcess?.adapter_applied,
    adapterId: analysisProcess?.adapter_id,
  });
  const fallbackSignalTone = getFallbackSignalTone(fallbackSignal);
  const ragFocus = buildRagFocusModel({
    analysisPrompt: analysisResult?.analysis?.prompt ?? analysisPrompt,
    analysisStatus: analysisResult?.status,
    chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
    analysisTimeline,
    analysisProcess,
    snapshot,
    ragFocusPayload: analysisResult?.analysis?.rag_focus ?? null,
  });
  const logitLens = buildLogitLensModel(analysisResult?.analysis?.logit_lens ?? null);
  const attention = buildAttentionModel(analysisResult?.analysis?.attention ?? null);
  const saliency = buildSaliencyModel(analysisResult?.analysis?.saliency ?? null);
  const analysisCapabilities = analysisResult?.analysis?.analysis_capabilities ?? null;
  const internalsProbeElapsedMs = useMemo(
    () =>
      sumProbeElapsedMs([
        logitLens?.diagnostics?.elapsed_ms as number | null | undefined,
        attention?.diagnostics?.elapsed_ms as number | null | undefined,
        saliency?.diagnostics?.elapsed_ms as number | null | undefined,
      ]),
    [
      attention?.diagnostics?.elapsed_ms,
      logitLens?.diagnostics?.elapsed_ms,
      saliency?.diagnostics?.elapsed_ms,
    ],
  );
  const internalsCapabilityRows = useMemo(() => {
    const payload = analysisCapabilities;
    return [
      buildInternalsCapabilityRow("attention", payload?.attention),
      buildInternalsCapabilityRow("saliency", payload?.saliency),
      buildInternalsCapabilityRow("logit lens", payload?.logit_lens),
    ];
  }, [analysisCapabilities]);
  const internalsVerdictPresentation = resolveInternalsVerdictPresentation(
    analysisCapabilities?.internals_verdict,
  );
  const internalsVerdictLabel = internalsVerdictPresentation.label;
  const internalsVerdictTone = internalsVerdictPresentation.tone;
  const probeLimitsLabel = useMemo(
    () => buildProbeLimitsLabel(analysisCapabilities?.limits),
    [analysisCapabilities?.limits],
  );
  const internalsVerdict = useMemo(() => {
    if (!analysisCapabilities) {
      return null;
    }
    const availableCount = Number(analysisCapabilities.available_count ?? 0);
    const totalCount = Number(analysisCapabilities.total_count ?? 3);
    return {
      verdict: internalsVerdictLabel,
      tone: internalsVerdictTone,
      availableCount,
      totalCount,
      details: internalsCapabilityRows.map((row) => `${row.label}:${row.reason}`),
    };
  }, [analysisCapabilities, internalsCapabilityRows, internalsVerdictLabel, internalsVerdictTone]);
  const operatorConclusion = buildOperatorConclusion({
    analysisVisible,
    analysisStatus: analysisResult?.status,
    skippedReason: analysisResult?.skipped_reason ?? null,
    analysisErrorCode: analysisResult?.analysis?.error_code ?? analysisResult?.analysis?.error ?? null,
    analysisTimeline,
    ragFocus,
    logitLens,
    operatorConclusionPayload: analysisResult?.analysis?.operator_conclusion ?? null,
  });
  const streamProfile = analysisResult?.analysis?.stream_profile ?? null;
  const evidenceCoverage = analysisResult?.analysis?.evidence_coverage ?? null;
  const inputProfile = analysisResult?.analysis?.input_profile ?? null;
  const generationProfile = analysisResult?.analysis?.generation_profile ?? null;
  const runTrends = useMemo<RunTrends | null>(
    () => buildRunTrends(analysisResult?.analysis?.run_trends),
    [analysisResult?.analysis?.run_trends],
  );
  const operatorChecklist = buildOperatorChecklist({
    ragSource: String(analysisResult?.analysis?.rag_focus?.source || "graph_fallback"),
    probeSource: String(analysisResult?.analysis?.logit_lens?.source || "probe_unavailable"),
    coveragePercent:
      typeof evidenceCoverage?.coverage_percent === "number"
        ? evidenceCoverage.coverage_percent
        : null,
    streamQuality: streamProfile?.stream_quality,
    partial: operatorConclusion?.partial,
    t,
  });
  const operatorRunbookSteps = buildOperatorRunbookSteps(
    operatorConclusion?.reasonCodes ?? null,
  );
  const availablePackages = snapshot?.available_packages.length ?? 0;
  const missingPackages = snapshot?.missing_packages.length ?? 0;
  const totalPackages = availablePackages + missingPackages;
  const packageCoverage = totalPackages > 0 ? (availablePackages / totalPackages) * 100 : 0;
  const analysisProgress = computeAnalysisProgress({
    analysisVisible,
    analysisTimelineProgress,
    analysisStepCount,
    chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
    firstChunkMs: analysisFirstChunkMs,
    elapsedMs: analysisResult?.analysis?.elapsed_ms ?? 0,
    analysisStatus: analysisResult?.status,
  });
  const visualMetrics = { packageCoverage, analysisProgress };
  const selectedGraphNodeIdEffective = useMemo(
    () =>
      resolveSelectedGraphNodeIdEffective({
        nodes: snapshot?.graph?.nodes ?? [],
        selectedGraphNodeId,
      }),
    [selectedGraphNodeId, snapshot?.graph?.nodes],
  );
  const selectedGraphNode = useMemo(
    () =>
      resolveSelectedGraphNode({
        nodes: snapshot?.graph?.nodes ?? [],
        selectedGraphNodeIdEffective,
      }),
    [selectedGraphNodeIdEffective, snapshot?.graph?.nodes],
  );
  const selectedGraphNodeDetails = useMemo(
    () =>
      resolveGraphDetails({
        snapshot,
        selectedGraphNode,
        analysisMechanismEnabled,
        analysisStatus: analysisResult?.status,
        analysisVisible,
        analysisChunkCount: analysisResult?.analysis?.chunk_count ?? 0,
        analysisElapsedMs: analysisResult?.analysis?.elapsed_ms ?? 0,
      }),
    [
      analysisMechanismEnabled,
      analysisResult?.analysis?.chunk_count,
      analysisResult?.analysis?.elapsed_ms,
      analysisResult?.status,
      analysisVisible,
      selectedGraphNode,
      snapshot,
    ],
  );
  const selectedGraphTypeHint = useMemo(
    () => resolveSelectedGraphTypeHint(selectedGraphNode),
    [selectedGraphNode],
  );
  return {
    stats,
    analysisVisible,
    analysisActive,
    analysisComparison,
    analysisResponse,
    analysisHighlights,
    analysisTimeline,
    analysisProcess,
    analysisTraceStepCount,
    analysisFirstChunkMs,
    analysisStepCount,
    analysisTraceId,
    analysisStreaming,
    analysisPhase,
    analysisAnswerTone,
    answerStatusLabel,
    operatorFinalStatus,
    operatorFinalStatusTone,
    operatorStreamMode,
    operatorStreamModeTone,
    fallbackSignal,
    fallbackSignalTone,
    ragFocus,
    logitLens,
    attention,
    saliency,
    analysisCapabilities,
    internalsProbeElapsedMs,
    internalsCapabilityRows,
    internalsVerdictLabel,
    internalsVerdictTone,
    probeLimitsLabel,
    internalsVerdict,
    operatorConclusion,
    evidenceCoverage,
    inputProfile,
    generationProfile,
    runTrends,
    operatorChecklist,
    operatorRunbookSteps,
    visualMetrics,
    selectedGraphNodeIdEffective,
    selectedGraphNode,
    selectedGraphNodeDetails,
    selectedGraphTypeHint,
  };
}

export function ModelIntrospectionDashboard() {
  const t = useTranslation();
  const { enabled: analysisMechanismEnabled } = useModelIntrospectionMechanism();
  const { snapshot, loading, error, loadSnapshot } = useModelIntrospectionSnapshot();
  const [analysisPrompt, setAnalysisPrompt] = useState(
    t("inspector.modelIntrospection.dashboard.analysis.promptPlaceholder"),
  );
  const {
    analysisLoading,
    analysisError,
    analysisResult,
    runAnalysis,
  } = useModelIntrospectionAnalysisStream({
    analysisMechanismEnabled,
    analysisPrompt,
  });
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [graphLayerOpen, setGraphLayerOpen] = useState(false);
  const [graphDrilldownOpen, setGraphDrilldownOpen] = useState(true);
  const [advancedInternalsOpen, setAdvancedInternalsOpen] = useState(false);

  const {
    stats,
    analysisVisible,
    analysisActive,
    analysisComparison,
    analysisResponse,
    analysisHighlights,
    analysisTimeline,
    analysisProcess,
    analysisTraceStepCount,
    analysisFirstChunkMs,
    analysisStepCount,
    analysisTraceId,
    analysisStreaming,
    analysisPhase,
    analysisAnswerTone,
    answerStatusLabel,
    operatorFinalStatus,
    operatorFinalStatusTone,
    operatorStreamMode,
    operatorStreamModeTone,
    fallbackSignal,
    fallbackSignalTone,
    ragFocus,
    logitLens,
    attention,
    saliency,
    analysisCapabilities,
    internalsProbeElapsedMs,
    internalsCapabilityRows,
    internalsVerdictLabel,
    internalsVerdictTone,
    probeLimitsLabel,
    internalsVerdict,
    operatorConclusion,
    evidenceCoverage,
    inputProfile,
    generationProfile,
    runTrends,
    operatorChecklist,
    operatorRunbookSteps,
    visualMetrics,
    selectedGraphNodeIdEffective,
    selectedGraphNode,
    selectedGraphNodeDetails,
    selectedGraphTypeHint,
  } = useDashboardDerivedState({
    snapshot,
    t,
    analysisResult,
    analysisLoading,
    analysisPrompt,
    analysisMechanismEnabled,
    selectedGraphNodeId,
  });

  const handleRefreshSnapshot = useCallback(() => {
    loadSnapshot().catch(() => undefined);
  }, [loadSnapshot]);

  const handleRunAnalysis = useCallback(() => {
    setAdvancedInternalsOpen(true);
    runAnalysis().catch(() => undefined);
  }, [runAnalysis]);

  const handleResetPrompt = useCallback(() => {
    setAnalysisPrompt(
      t("inspector.modelIntrospection.dashboard.analysis.promptPlaceholder"),
    );
  }, [t]);

  const attentionAvailable = Boolean(
    attention && attention.status === "ok" && attention.layers.length > 0,
  );
  const saliencyAvailable = Boolean(
    saliency && saliency.status === "ok" && saliency.token_weights.length > 0,
  );
  const logitLensAvailable = Boolean(
    logitLens && logitLens.status === "ok" && logitLens.checkpoints.length > 0,
  );
  const allInternalsUnavailable =
    !attentionAvailable && !saliencyAvailable && !logitLensAvailable;
  const anyInternalsAvailable =
    attentionAvailable || saliencyAvailable || logitLensAvailable;
  const unavailableInternalsRows = internalsCapabilityRows.filter((row) => !row.available);
  const proxyInternalsRows = internalsCapabilityRows.filter(
    (row) => row.available && row.reason !== "ok",
  );
  const availableInternalsCount = internalsCapabilityRows.length - unavailableInternalsRows.length;

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow={t("inspector.modelIntrospection.page.eyebrow")}
        title={t("inspector.modelIntrospection.page.title")}
        description={t("inspector.modelIntrospection.page.description")}
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={handleRefreshSnapshot} disabled={loading}>
              <RefreshCcw className="h-4 w-4" />
              {loading ? t("common.loading") : t("inspector.modelIntrospection.actions.refresh")}
            </Button>
            <Button asChild variant="ghost">
              <Link href="/inspector">
                <Radar className="h-4 w-4" />
                {t("inspector.modelIntrospection.actions.openInspector")}
              </Link>
            </Button>
            <Button asChild variant="ghost">
              <Link href="/brain">
                <Brain className="h-4 w-4" />
                {t("inspector.modelIntrospection.actions.openBrain")}
              </Link>
            </Button>
          </div>
        }
      />

      {!snapshot && loading && (
        <Panel
          eyebrow="// loading"
          title={t("inspector.modelIntrospection.dashboard.loading.title")}
          description={t("inspector.modelIntrospection.dashboard.loading.description")}
        >
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">read-only</Badge>
            <Badge tone="neutral">brain reuse</Badge>
            <Badge tone="neutral">diagnostics reuse</Badge>
            <Badge tone="neutral">packages probe</Badge>
          </div>
        </Panel>
      )}

      {error && (
        <Panel
          eyebrow="// error"
          title={t("inspector.modelIntrospection.dashboard.error.title")}
          description={error}
          className="border border-amber-400/30"
        >
          <p className="text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.error.note")}
          </p>
        </Panel>
      )}

      {snapshot && (
        <Panel
          eyebrow="// analysis"
          title={t("inspector.modelIntrospection.dashboard.analysis.title")}
          description={t("inspector.modelIntrospection.dashboard.analysis.description")}
        >
          <div className="grid gap-4 lg:grid-cols-2">
            <AnalysisInputPanel
              prompt={analysisPrompt}
              onPromptChange={setAnalysisPrompt}
              onRunAnalysis={handleRunAnalysis}
              onResetPrompt={handleResetPrompt}
              analysisLoading={analysisLoading}
              analysisMechanismEnabled={analysisMechanismEnabled}
              snapshotReady={Boolean(snapshot)}
              analysisError={analysisError}
              skipped={analysisResult?.status === "skipped"}
              promptLabel={t("inspector.modelIntrospection.dashboard.analysis.promptLabel")}
              promptPlaceholder={t("inspector.modelIntrospection.dashboard.analysis.promptPlaceholder")}
              runLabel={t("inspector.modelIntrospection.dashboard.analysis.run")}
              runningLabel={t("inspector.modelIntrospection.dashboard.analysis.running")}
              resetLabel={t("inspector.modelIntrospection.dashboard.analysis.reset")}
              disabledLabel={t("inspector.modelIntrospection.dashboard.analysis.disabled")}
              skippedLabel={t("inspector.modelIntrospection.dashboard.analysis.skipped")}
            />
            <div className="space-y-4">
              <AnalysisOrbPanel
                active={analysisActive}
                phase={analysisPhase}
                packageCoverage={visualMetrics.packageCoverage}
                chunks={analysisVisible ? analysisResult?.analysis?.chunk_count ?? 0 : 0}
                elapsedMs={analysisVisible ? analysisResult?.analysis?.elapsed_ms ?? 0 : 0}
                firstChunkMs={analysisFirstChunkMs}
                traceId={analysisTraceId}
                stepCount={analysisStepCount}
                charsPerSecond={analysisProcess?.chars_per_second ?? null}
                progress={visualMetrics.analysisProgress}
                subtitle={getOrbSubtitle({
                  analysisStatus: analysisResult?.status,
                  analysisActive,
                  chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
                  analysisStepCount,
                  idleLabel: t("inspector.modelIntrospection.dashboard.analysis.orbIdle"),
                  chunksLabel: t("inspector.modelIntrospection.dashboard.analysis.chunksLabel"),
                  stepsLabel: t("inspector.modelIntrospection.dashboard.analysis.stepsLabel"),
                  completedLabel: t("inspector.modelIntrospection.dashboard.analysis.completedLabel"),
                })}
              />
              <AnalysisLiveResponsePanel
                analysisStreaming={analysisStreaming}
                analysisResponse={analysisResponse}
                answerStatusLabel={answerStatusLabel}
                waitingTokenLabel={t("inspector.modelIntrospection.dashboard.results.waitingToken")}
                streamingLabel={t("inspector.modelIntrospection.dashboard.results.streaming")}
                statusBadgeLabel={t(
                  `inspector.modelIntrospection.dashboard.analysis.status.${operatorFinalStatus}`,
                )}
                statusBadgeTone={operatorFinalStatusTone}
                streamModeLabel={t(
                  `inspector.modelIntrospection.dashboard.analysis.streamMode.${operatorStreamMode}`,
                )}
                streamModeTone={operatorStreamModeTone}
                fallbackLabel={t(
                  `inspector.modelIntrospection.dashboard.analysis.fallback.${fallbackSignal}`,
                )}
                fallbackTone={fallbackSignalTone}
              />
            </div>
          </div>
        </Panel>
      )}

      {analysisVisible && analysisResult?.analysis && snapshot && (
        <Panel
          eyebrow="// results"
          title={t("inspector.modelIntrospection.dashboard.results.title")}
          description={t("inspector.modelIntrospection.dashboard.results.description")}
        >
          <div className="mb-4">
            <RagFocusPanel
              ragFocus={ragFocus}
              title={t("inspector.modelIntrospection.dashboard.results.ragFocus.title")}
              queryLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.query")}
              entitiesLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.entities")}
              evidenceLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.evidence")}
              groundingLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.grounding")}
              activeLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.active")}
              emptyLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.empty")}
              stepLabelPrefix={t("inspector.modelIntrospection.dashboard.results.ragFocus.step")}
              groundingStrongLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.groundingStrong",
              )}
              groundingMediumLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.groundingMedium",
              )}
              groundingWeakLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.groundingWeak",
              )}
              groundingUnknownLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.groundingUnknown",
              )}
              sourceLabel={t("inspector.modelIntrospection.dashboard.results.ragFocus.source")}
              sourceRuntimeTraceLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.sourceRuntimeTrace",
              )}
              sourceFallbackLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.sourceFallback",
              )}
              answerLinksLabel={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.answerLinks",
              )}
              answerLinksEmpty={t(
                "inspector.modelIntrospection.dashboard.results.ragFocus.answerLinksEmpty",
              )}
            />
          </div>
          <div className="mb-4">
            <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-amber-100">Advanced internals</p>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={internalsVerdictTone}>{internalsVerdictLabel}</Badge>
                  <Badge tone="warning">{resolveProbeBudgetLabel(internalsProbeElapsedMs)}</Badge>
                </div>
              </div>
              <p className="mt-2 text-sm text-amber-50/90">
                Attention i Saliency to kosztowna analiza opt-in. Może wydłużać odpowiedź i podlega limitom runtime/probe.
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Badge tone="neutral">
                  profile: {analysisCapabilities?.probe_profile ?? "unknown"}
                </Badge>
                <Badge tone={analysisCapabilities?.probe_healthy ? "success" : "warning"}>
                  runtime: {analysisCapabilities?.runtime_supported ? "supported" : "unsupported"}
                </Badge>
                <Badge tone={analysisCapabilities?.endpoint_configured ? "success" : "warning"}>
                  endpoint: {analysisCapabilities?.endpoint_configured ? "configured" : "missing"}
                </Badge>
                <Badge tone={analysisCapabilities?.model_whitelisted ? "success" : "warning"}>
                  model: {analysisCapabilities?.model_whitelisted ? "whitelisted" : "blocked"}
                </Badge>
                <Badge tone={analysisCapabilities?.probe_enabled ? "success" : "warning"}>
                  probe: {analysisCapabilities?.probe_enabled ? "enabled" : "disabled"}
                </Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Badge tone={availableInternalsCount === internalsCapabilityRows.length ? "success" : "warning"}>
                  coverage {availableInternalsCount}/{internalsCapabilityRows.length}
                </Badge>
                <Badge tone="neutral">{probeLimitsLabel}</Badge>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {unavailableInternalsRows.map((row) => (
                  <Badge key={row.label} tone="warning">
                    {row.label}: {row.reason}
                  </Badge>
                ))}
                {proxyInternalsRows.map((row) => (
                  <Badge key={`proxy-${row.label}`} tone="neutral">
                    {row.label}: {row.reason}
                  </Badge>
                ))}
              </div>
              <div className="mt-3">
                <Button
                  variant="outline"
                  onClick={() => setAdvancedInternalsOpen((current) => !current)}
                >
                  {advancedInternalsOpen ? "Ukryj advanced internals" : "Pokaż advanced internals"}
                </Button>
              </div>
            </div>
          </div>
          <div className="mb-4">
            <LogitLensPanel
              logitLens={logitLens}
              title={t("inspector.modelIntrospection.dashboard.results.logitLens.title")}
              emptyLabel={t("inspector.modelIntrospection.dashboard.results.logitLens.empty")}
              unavailableLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.unavailable",
              )}
              signalsLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.confidence",
              )}
              tokensLabel={t("inspector.modelIntrospection.dashboard.results.logitLens.tokens")}
              checkpointsLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.checkpoints",
              )}
              signalEarlyUnstableLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.signalEarlyUnstable",
              )}
              signalLateStabilizedLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.signalLateStabilized",
              )}
              signalLowConfidenceLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.signalLowConfidence",
              )}
              signalStableLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.signalStable",
              )}
              changedLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.changed",
              )}
              stableLabel={t("inspector.modelIntrospection.dashboard.results.logitLens.stable")}
              sourceLabel={t("inspector.modelIntrospection.dashboard.results.logitLens.source")}
              sourceRuntimeLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.sourceRuntime",
              )}
              sourceUnavailableLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.sourceUnavailable",
              )}
              sourceFallbackWarning={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.sourceFallbackWarning",
              )}
            />
          </div>
          {advancedInternalsOpen && (
            <>
              {proxyInternalsRows.length > 0 && (
                <div className="mb-4 rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs uppercase tracking-wide text-zinc-500">
                      Probe internals recovered
                    </p>
                    <Badge tone="neutral">proxy path active</Badge>
                  </div>
                  <p className="mt-2 text-sm text-zinc-300">
                    Część sygnałów internals została odzyskana ścieżką proxy zamiast natywnego
                    payloadu probe.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {proxyInternalsRows.map((row) => (
                      <Badge key={`proxy-open-${row.label}`} tone="neutral">
                        {row.label}: {row.reason}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
              {anyInternalsAvailable && unavailableInternalsRows.length > 0 && (
                <div className="mb-4 rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs uppercase tracking-wide text-zinc-500">
                      Probe internals partial
                    </p>
                    <Badge tone={internalsVerdictTone}>{internalsVerdictLabel}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-zinc-300">
                    Część internals jest dostępna. Niedostępne mechanizmy pozostają w fallbacku
                    dla tego runu i nie blokują widoku pozostałych danych.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {unavailableInternalsRows.map((row) => (
                      <Badge key={row.label} tone="warning">
                        {row.label}: {row.reason}
                      </Badge>
                    ))}
                    <Badge tone="neutral">{probeLimitsLabel}</Badge>
                  </div>
                </div>
              )}
              {allInternalsUnavailable && (
                <div className="mb-4 rounded-2xl border border-white/10 bg-black/20 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs uppercase tracking-wide text-zinc-500">
                      Probe internals unavailable
                    </p>
                    <Badge tone={internalsVerdictTone}>{internalsVerdictLabel}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-zinc-300">
                    Dla tego runu probe nie zwrocil attention, saliency ani logit lens. Glowny
                    sygnal prowadzi teraz RAG, evidence i verdict odpowiedzi.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {unavailableInternalsRows.map((row) => (
                      <Badge key={row.label} tone="warning">
                        {row.label}: {row.reason}
                      </Badge>
                    ))}
                    <Badge tone="neutral">{probeLimitsLabel}</Badge>
                  </div>
                </div>
              )}
              <div className="mb-4">
                <AttentionPanel
                  attention={attention}
                  title="Attention Head View"
                  emptyLabel="Brak danych attention dla bieżącej analizy."
                  unavailableLabel="Attention probe niedostępny dla bieżącego runu."
                />
              </div>
              <div className="mb-4">
                <SaliencyPanel
                  saliency={saliency}
                  title="Saliency / Attribution"
                  emptyLabel="Brak danych saliency dla bieżącej analizy."
                  unavailableLabel="Saliency probe niedostępny dla bieżącego runu."
                />
              </div>
            </>
          )}
          <AnalysisResultsPanel
            analysisResponse={analysisResponse}
            analysisHighlights={analysisHighlights}
            answerStatusLabel={answerStatusLabel}
            analysisAnswerTone={analysisAnswerTone}
            managerAvailable={snapshot.model_manager.available}
            eventsCount={analysisResult.analysis.events.length}
            analysisTimeline={analysisTimeline}
            analysisProcess={analysisProcess}
            analysisTraceStepCount={analysisTraceStepCount}
            analysisTimelineStepCount={analysisStepCount}
            responseChars={analysisResponse.length}
            chunkCount={analysisResult.analysis.chunk_count}
            resultsHighlightsLabel={t("inspector.modelIntrospection.dashboard.results.highlights")}
            highlightsEmptyLabel={t("inspector.modelIntrospection.dashboard.results.highlightsEmpty")}
            resultsVerdictLabel={t("inspector.modelIntrospection.dashboard.results.verdict")}
            resultsVerdictReady={t("inspector.modelIntrospection.dashboard.results.verdictReady")}
            resultsVerdictPending={t("inspector.modelIntrospection.dashboard.results.verdictPending")}
            advancedShowLabel={t(
              "inspector.modelIntrospection.dashboard.results.advancedShow",
            )}
            advancedHideLabel={t(
              "inspector.modelIntrospection.dashboard.results.advancedHide",
            )}
            advancedTitle={t("inspector.modelIntrospection.dashboard.results.advancedTitle")}
            operatorConclusion={operatorConclusion}
            operatorConclusionLabel={t(
              "inspector.modelIntrospection.dashboard.results.operatorConclusion",
            )}
            operatorConclusionConfidenceLabel={t(
              "inspector.modelIntrospection.dashboard.results.operatorConfidence",
            )}
            operatorConclusionPartialLabel={t(
              "inspector.modelIntrospection.dashboard.results.operatorPartial",
            )}
            streamProfile={analysisResult?.analysis?.stream_profile}
            evidenceCoverage={evidenceCoverage}
            inputProfile={inputProfile}
            generationProfile={generationProfile}
            runTrends={runTrends}
            operatorChecklist={operatorChecklist}
            operatorRunbookSteps={operatorRunbookSteps}
            internalsVerdict={internalsVerdict}
          />
        </Panel>
      )}

      {analysisResult?.snapshot_after && (
        <div className="mt-2">
          <SnapshotComparisonPanel
            comparison={analysisComparison}
            fallbackLabel={t("inspector.modelIntrospection.dashboard.snapshotComparison.fallback")}
            title={t("inspector.modelIntrospection.dashboard.snapshotComparison.title")}
            beforeLabel={t("inspector.modelIntrospection.dashboard.snapshotComparison.before")}
            afterLabel={t("inspector.modelIntrospection.dashboard.snapshotComparison.after")}
            deltaLabel={t("inspector.modelIntrospection.dashboard.snapshotComparison.delta")}
          />
        </div>
      )}

      {stats.length > 0 && (
        <Panel
          eyebrow="// runtime context"
          title={t("inspector.modelIntrospection.dashboard.runtimeContext.title")}
          description={t("inspector.modelIntrospection.dashboard.runtimeContext.description")}
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {stats.map((stat) => (
              <StatCard
                key={stat.label}
                label={stat.label}
                value={stat.value}
                hint={stat.hint}
                accent={stat.accent}
              />
            ))}
          </div>
        </Panel>
      )}

      {snapshot && (
        <Panel
          eyebrow="// technical"
          title={t("inspector.modelIntrospection.dashboard.graph.layerTitle")}
          description={t("inspector.modelIntrospection.dashboard.graph.layerDescription")}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="neutral">
                nodes {formatCount(snapshot.graph?.summary.nodes ?? 0)}
              </Badge>
              <Badge tone="neutral">
                edges {formatCount(snapshot.graph?.summary.edges ?? 0)}
              </Badge>
              <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
                drift {snapshot.runtime_drift.drift_detected ? "present" : "clean"}
              </Badge>
            </div>
            <Button variant="ghost" onClick={() => setGraphLayerOpen((current) => !current)}>
              {graphLayerOpen
                ? t("inspector.modelIntrospection.dashboard.graph.hideLayer")
                : t("inspector.modelIntrospection.dashboard.graph.showLayer")}
            </Button>
          </div>
          {graphLayerOpen && (
            <div className="mt-4">
              <GraphPanel
                snapshot={snapshot}
                analysisActive={analysisActive}
                graphViewOpen={graphDrilldownOpen}
                onToggleGraphView={() => setGraphDrilldownOpen((current) => !current)}
                selectedGraphNodeId={selectedGraphNodeIdEffective}
                onSelectGraphNode={setSelectedGraphNodeId}
                selectedGraphNode={selectedGraphNode}
                selectedGraphNodeDetails={selectedGraphNodeDetails}
                typeHintText={selectedGraphTypeHint}
                title={t("inspector.modelIntrospection.dashboard.graph.title")}
                description={t("inspector.modelIntrospection.dashboard.graph.description")}
                drilldownTitle={t("inspector.modelIntrospection.dashboard.graph.drilldownTitle")}
                hideLabel={t("inspector.modelIntrospection.dashboard.graph.hide")}
                openLabel={t("inspector.modelIntrospection.dashboard.graph.open")}
                stateOpenLabel={t("inspector.modelIntrospection.dashboard.graph.stateOpen")}
                stateCollapsedLabel={t("inspector.modelIntrospection.dashboard.graph.stateCollapsed")}
              />
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

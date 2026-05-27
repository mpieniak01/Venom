"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { Brain, Loader2, Radar, RefreshCcw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { useTranslation } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { useModelIntrospectionMechanism } from "@/components/inspector/model-introspection-mechanism";
import type {
  AnalysisTimelineEntry,
  AnalysisLayerInternalsPayload,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
  ModelArchitectureGraphReadiness,
  SnapshotComparison,
} from "@/components/inspector/model-introspection-dashboard-types";
import {
  buildAttentionModel,
  buildModelArchitectureGraphReadiness,
  buildOperatorConclusion,
  buildLogitLensModel,
  buildSaliencyModel,
  buildRagFocusModel,
  computeAnalysisProgress,
  formatCount,
  getAnalysisPhase,
  getAnswerStatusLabel,
  getAnswerTone,
  getOrbSubtitle,
  getTypeHintText,
  resolveSelectedGraphNodeDetails,
  splitAnswerHighlights,
} from "@/components/inspector/model-introspection-dashboard-view-model";
import { useModelIntrospectionSnapshot } from "@/components/inspector/use-model-introspection-snapshot";
import { useModelIntrospectionAnalysisStream } from "@/components/inspector/use-model-introspection-analysis-stream";
import {
  AnalysisInputPanel,
  AnalysisOrbPanel,
  AttentionPanel,
  LogitLensPanel,
  SaliencyPanel,
  RagFocusPanel,
  AnalysisResultsPanel,
  GraphPanel,
  ArchitectureGraphPanel,
  SnapshotComparisonPanel,
} from "@/components/inspector/model-introspection-dashboard-sections";

type RunTrends = {
  runs: number;
  window: number;
  runtimeTraceRate: number;
  probeRuntimeRate: number;
  highCoverageRate: number;
  liveStreamingRate: number;
  avgFirstContentMs: number | null;
  avgNoiseRatio: number | null;
  avgMlpL2: number | null;
  avgCosineSimilarity: number | null;
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
  availability_class?: string;
};
type InternalsCapabilityRow = {
  label: string;
  available: boolean;
  reason: string;
  availabilityClass: "native_ok" | "proxy_ok" | "unavailable" | "failed";
};
type IntrospectionLevel = "full" | "lite" | "none";
type InternalsNoticeProps = {
  title: string;
  message: string;
  tone: BadgeTone;
  badgeLabel?: string;
  rows: InternalsCapabilityRow[];
  rowsTone: BadgeTone;
  rowKeyPrefix: string;
  extraBadge?: string;
};

type DashboardRuntimeInternalsContext = {
  allInternalsUnavailable: boolean;
  anyInternalsAvailable: boolean;
  isOllamaLiteRuntime: boolean;
  logitLensTitle: string;
  internalsHowToFull: string | null;
  unavailableInternalsRows: InternalsCapabilityRow[];
  proxyInternalsRows: InternalsCapabilityRow[];
  availableInternalsCount: number;
  internalsProcessing: boolean;
  ragStepMarker: ResultStepMarker | null;
  responseStepMarker: ResultStepMarker | null;
  snapshotStepMarker: ResultStepMarker | null;
  logitStepMarker: ResultStepMarker | null;
  attentionStepMarker: ResultStepMarker | null;
  saliencyStepMarker: ResultStepMarker | null;
};

function getArchitectureReadinessTone(
  status: ModelArchitectureGraphReadiness["status"],
): BadgeTone {
  if (status === "available") {
    return "success";
  }
  if (status === "partial") {
    return "warning";
  }
  return "neutral";
}

function deriveDashboardRuntimeInternalsContext(args: {
  analysisResult: ReturnType<typeof useModelIntrospectionAnalysisStream>["analysisResult"];
  snapshot: IntrospectionSnapshot | null;
  introspectionLevel: IntrospectionLevel;
  logitLens: ReturnType<typeof buildLogitLensModel> | null;
  attention: ReturnType<typeof buildAttentionModel> | null;
  saliency: ReturnType<typeof buildSaliencyModel> | null;
  analysisTimeline: AnalysisTimelineEntry[];
  internalsCapabilityRows: InternalsCapabilityRow[];
  analysisLoading: boolean;
  analysisStreaming: boolean;
  t: ReturnType<typeof useTranslation>;
}): DashboardRuntimeInternalsContext {
  const unavailableInternalsRows = args.internalsCapabilityRows.filter(
    (row) => row.availabilityClass === "unavailable" || row.availabilityClass === "failed",
  );
  const availableInternalsCount =
    args.internalsCapabilityRows.length - unavailableInternalsRows.length;
  const allInternalsUnavailable = availableInternalsCount <= 0;
  const anyInternalsAvailable = availableInternalsCount > 0;
  const runtimeProviderNormalized = String(
    args.analysisResult?.analysis?.provider ?? args.snapshot?.runtime?.provider ?? "",
  ).toLowerCase();
  const isOllamaLiteRuntime =
    args.introspectionLevel === "lite" &&
    runtimeProviderNormalized === "ollama" &&
    args.logitLens?.source === "probe_lite";
  const logitLensTitle = isOllamaLiteRuntime
    ? args.t("inspector.modelIntrospection.dashboard.results.logitLens.titleLite")
    : args.t("inspector.modelIntrospection.dashboard.results.logitLens.title");
  const internalsHowToFull = isOllamaLiteRuntime
    ? args.t("inspector.modelIntrospection.dashboard.results.internalsHowToFull")
    : null;
  const proxyInternalsRows = args.internalsCapabilityRows.filter(
    (row) => row.availabilityClass === "proxy_ok",
  );
  const internalsProcessing = args.analysisLoading || args.analysisStreaming;
  return {
    allInternalsUnavailable,
    anyInternalsAvailable,
    isOllamaLiteRuntime,
    logitLensTitle,
    internalsHowToFull,
    unavailableInternalsRows,
    proxyInternalsRows,
    availableInternalsCount,
    internalsProcessing,
    ragStepMarker: resolveResultStepMarker("request_ready", args.analysisTimeline),
    responseStepMarker: resolveResultStepMarker(
      "response_finalized",
      args.analysisTimeline,
    ),
    snapshotStepMarker: resolveResultStepMarker("snapshot_after", args.analysisTimeline),
    logitStepMarker: resolveResultStepMarker("logit_lens_probe", args.analysisTimeline),
    attentionStepMarker: resolveResultStepMarker(
      "attention_probe",
      args.analysisTimeline,
    ),
    saliencyStepMarker: resolveResultStepMarker("saliency_probe", args.analysisTimeline),
  };
}
type ResultStepTone = "success" | "warning" | "neutral" | "danger";
type ResultStepStatus = "done" | "running" | "pending" | "failed";
type ResultStepMarker = {
  number: number;
  key: string;
  labelKey: string;
  status: ResultStepStatus;
  tone: ResultStepTone;
};
type ResultStepDef = {
  number: number;
  key: string;
  labelKey: string;
  timelineIds: readonly string[];
};

type SnapshotLoadingPanelProps = Readonly<{
  snapshot: IntrospectionSnapshot | null;
  loading: boolean;
  t: (key: string) => string;
}>;

type SnapshotErrorPanelProps = Readonly<{
  error: string | null;
  t: (key: string) => string;
}>;

function SnapshotLoadingPanel({
  snapshot,
  loading,
  t,
}: SnapshotLoadingPanelProps) {
  if (snapshot || !loading) {
    return null;
  }
  return (
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
  );
}

function SnapshotErrorPanel({ error, t }: SnapshotErrorPanelProps) {
  if (!error) {
    return null;
  }
  return (
    <Panel
      eyebrow="// error"
      title={t("inspector.modelIntrospection.dashboard.error.title")}
      description={error}
      className="border border-amber-400/30"
    >
      <p className="text-sm text-zinc-300">{t("inspector.modelIntrospection.dashboard.error.note")}</p>
    </Panel>
  );
}

function InternalsNoticeCard({
  title,
  message,
  tone,
  badgeLabel,
  rows,
  rowsTone,
  rowKeyPrefix,
  extraBadge,
}: Readonly<InternalsNoticeProps>) {
  return (
    <div className="mb-4 rounded-2xl border border-white/10 bg-black/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <Badge tone={tone}>{badgeLabel ?? title}</Badge>
      </div>
      <p className="mt-2 text-sm text-zinc-300">{message}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {rows.map((row) => (
          <Badge key={`${rowKeyPrefix}-${row.label}`} tone={rowsTone}>
            {row.label}: {row.reason}
          </Badge>
        ))}
        {extraBadge ? <Badge tone="neutral">{extraBadge}</Badge> : null}
      </div>
    </div>
  );
}

type TechnicalLayerPanelProps = Readonly<{
  snapshot: IntrospectionSnapshot | null;
  graphLayerOpen: boolean;
  analysisActive: boolean;
  architectureGraphReadiness: ModelArchitectureGraphReadiness;
  analysisLayerInternalsPayload: AnalysisLayerInternalsPayload | null;
  selectedGraphNodeIdEffective: string | null;
  selectedGraphNode: { id: string; label: string; kind: string; status: string } | null;
  selectedGraphNodeDetails: GraphNodeDetails | null;
  selectedGraphTypeHint: string;
  onToggleGraphLayer: () => void;
  onSelectGraphNode: (id: string | null) => void;
  t: (key: string) => string;
}>;

function TechnicalLayerPanel({
  snapshot,
  graphLayerOpen,
  analysisActive,
  architectureGraphReadiness,
  analysisLayerInternalsPayload,
  selectedGraphNodeIdEffective,
  selectedGraphNode,
  selectedGraphNodeDetails,
  selectedGraphTypeHint,
  onToggleGraphLayer,
  onSelectGraphNode,
  t,
}: TechnicalLayerPanelProps) {
  if (!snapshot) {
    return null;
  }
  return (
    <Panel
      eyebrow="// technical"
      title={t("inspector.modelIntrospection.dashboard.graph.layerTitle")}
      description={t("inspector.modelIntrospection.dashboard.graph.layerDescription")}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">nodes {formatCount(snapshot.graph?.summary.nodes ?? 0)}</Badge>
          <Badge tone="neutral">edges {formatCount(snapshot.graph?.summary.edges ?? 0)}</Badge>
          <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
            drift {snapshot.runtime_drift.drift_detected ? "present" : "clean"}
          </Badge>
        </div>
        <Button variant="ghost" onClick={onToggleGraphLayer}>
          {graphLayerOpen
            ? t("inspector.modelIntrospection.dashboard.graph.hideLayer")
            : t("inspector.modelIntrospection.dashboard.graph.showLayer")}
        </Button>
      </div>
      <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-500/10 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={getArchitectureReadinessTone(architectureGraphReadiness.status)}>
            model graph {architectureGraphReadiness.status}
          </Badge>
          <Badge tone="neutral">
            payload {architectureGraphReadiness.hasArchitecturePayload ? "present" : "missing"}
          </Badge>
          <Badge tone="neutral">fidelity {architectureGraphReadiness.fidelity}</Badge>
          <Badge tone="neutral">
            source {architectureGraphReadiness.source}
          </Badge>
          <Badge tone="neutral">layers {formatCount(architectureGraphReadiness.layerCount)}</Badge>
          <Badge tone="neutral">blocks {formatCount(architectureGraphReadiness.blockCount)}</Badge>
        </div>
        <p className="mt-2 text-sm text-cyan-50/90">
          {architectureGraphReadiness.recommendedNextStep}
        </p>
        {architectureGraphReadiness.missingSignals.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {architectureGraphReadiness.missingSignals.map((signal) => (
              <Badge key={signal} tone="neutral">
                {signal}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>
      {snapshot.architecture_graph ? (
        <div className="mt-4">
      <ArchitectureGraphPanel
            snapshot={snapshot}
            readiness={architectureGraphReadiness}
            layerInternalsPayload={analysisLayerInternalsPayload}
            title={t("inspector.modelIntrospection.dashboard.graph.architectureTitle")}
            description={t("inspector.modelIntrospection.dashboard.graph.architectureDescription")}
            typeHintText={t("inspector.modelIntrospection.dashboard.graph.architectureTypeHint")}
          />
        </div>
      ) : null}
      {graphLayerOpen ? (
        <div className="mt-4">
          <GraphPanel
            snapshot={snapshot}
            analysisActive={analysisActive}
            selectedGraphNodeId={selectedGraphNodeIdEffective}
            onSelectGraphNode={onSelectGraphNode}
            selectedGraphNode={selectedGraphNode}
            selectedGraphNodeDetails={selectedGraphNodeDetails}
            typeHintText={selectedGraphTypeHint}
            title={t("inspector.modelIntrospection.dashboard.graph.title")}
            description={t("inspector.modelIntrospection.dashboard.graph.description")}
          />
        </div>
      ) : null}
    </Panel>
  );
}

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
    probe_disabled: "probe disabled in runtime config",
    probe_failed: "probe failed",
    runtime_not_supported: "runtime not supported for probe",
    model_not_whitelisted: "model not whitelisted for probe",
    endpoint_missing: "probe endpoint missing",
    live_analysis_disabled: "live analysis disabled",
    attention_unavailable: "attention unavailable",
    saliency_unavailable: "saliency unavailable",
    logit_lens_unavailable: "logit lens unavailable",
    attention_proxy_logits: "recovered via logits proxy",
    saliency_proxy_attention: "recovered via attention proxy",
    saliency_proxy_logits: "recovered via logits proxy",
  };
  const mappedReason = reasonMap[rawReason] ?? rawReason.replaceAll("_", " ");
  const rawClass = String(capability?.availability_class || "").trim();
  let availabilityClass: InternalsCapabilityRow["availabilityClass"];
  if (rawClass === "native_ok" || rawClass === "proxy_ok" || rawClass === "unavailable" || rawClass === "failed") {
    availabilityClass = rawClass;
  } else if (available && mappedReason === "ok") {
    availabilityClass = "native_ok";
  } else if (available) {
    availabilityClass = "proxy_ok";
  } else if (mappedReason === "probe failed") {
    availabilityClass = "failed";
  } else {
    availabilityClass = "unavailable";
  }
  return {
    label,
    available,
    reason: available && mappedReason === "ok" ? "ok" : mappedReason,
    availabilityClass,
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

function resolveIntrospectionLevel(args: {
  analysisLevel: string | null | undefined;
  snapshotLevel: string | null | undefined;
}): IntrospectionLevel {
  const candidate = (args.analysisLevel ?? args.snapshotLevel ?? "none").toLowerCase();
  if (candidate === "full" || candidate === "lite" || candidate === "none") {
    return candidate;
  }
  return "none";
}

const RESULT_STEP_DEFS: readonly ResultStepDef[] = [
  {
    number: 1,
    key: "snapshot_before",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.snapshotBefore",
    timelineIds: ["snapshot_before"],
  },
  {
    number: 2,
    key: "request_ready",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.requestReady",
    timelineIds: ["request_ready"],
  },
  {
    number: 3,
    key: "stream_opened",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.streamOpened",
    timelineIds: ["stream_opened"],
  },
  {
    number: 4,
    key: "first_chunk",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.firstChunk",
    timelineIds: ["first_chunk"],
  },
  {
    number: 5,
    key: "response_finalized",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.responseFinalized",
    timelineIds: ["response_finalized"],
  },
  {
    number: 6,
    key: "snapshot_after",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.snapshotAfter",
    timelineIds: ["snapshot_after"],
  },
  {
    number: 7,
    key: "logit_lens_probe",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.logitLensProbe",
    timelineIds: ["logit_lens_probe", "internals:logit_lens_probe"],
  },
  {
    number: 8,
    key: "attention_probe",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.attentionProbe",
    timelineIds: ["attention_probe", "internals:attention_probe"],
  },
  {
    number: 9,
    key: "saliency_probe",
    labelKey: "inspector.modelIntrospection.dashboard.results.steps.saliencyProbe",
    timelineIds: ["saliency_probe", "internals:saliency_probe"],
  },
];

function getStepTone(status: ResultStepStatus): ResultStepTone {
  if (status === "done") return "success";
  if (status === "running") return "warning";
  if (status === "failed") return "danger";
  return "neutral";
}

function resolveResultStepStatus(args: Readonly<{
  hasFailed: boolean;
  hasRunning: boolean;
  hasDone: boolean;
}>): ResultStepStatus {
  if (args.hasFailed) {
    return "failed";
  }
  if (args.hasRunning) {
    return "running";
  }
  if (args.hasDone) {
    return "done";
  }
  return "pending";
}

function resolveResultStepMarker(
  stepKey: string,
  timeline: AnalysisTimelineEntry[],
): ResultStepMarker | null {
  const def = RESULT_STEP_DEFS.find((item) => item.key === stepKey);
  if (!def) return null;
  const matches = timeline.filter((entry) => def.timelineIds.includes(entry.id));
  const hasFailed = matches.some((entry) => entry.status === "failed");
  const hasRunning = matches.some((entry) => entry.status === "running");
  const hasDone = matches.some((entry) => entry.status === "done");
  const status = resolveResultStepStatus({ hasFailed, hasRunning, hasDone });
  return {
    number: def.number,
    key: def.key,
    labelKey: def.labelKey,
    status,
    tone: getStepTone(status),
  };
}

function formatStepLabel(
  t: (key: string) => string,
  marker: ResultStepMarker | null,
): string | undefined {
  if (!marker) {
    return undefined;
  }
  return `${t("inspector.modelIntrospection.dashboard.results.stepPrefix")} ${marker.number} · ${t(marker.labelKey)}`;
}

function formatStepStatusLabel(
  t: (key: string) => string,
  status: ResultStepStatus,
): string {
  const statusKeyMap: Record<ResultStepStatus, string> = {
    done: "inspector.modelIntrospection.dashboard.results.stepStatus.done",
    running: "inspector.modelIntrospection.dashboard.results.stepStatus.running",
    pending: "inspector.modelIntrospection.dashboard.results.stepStatus.pending",
    failed: "inspector.modelIntrospection.dashboard.results.stepStatus.failed",
  };
  return t(statusKeyMap[status]);
}

function ResultStepHeader({
  marker,
  t,
}: Readonly<{
  marker: ResultStepMarker | null;
  t: (key: string) => string;
}>) {
  if (!marker) return null;
  const materializing = marker.status === "pending" || marker.status === "running";
  return (
    <div className="mb-2 flex items-center gap-2">
      <Badge tone={marker.tone}>{formatStepLabel(t, marker)}</Badge>
      <Badge tone="neutral">{formatStepStatusLabel(t, marker.status)}</Badge>
      {materializing ? (
        <Badge tone="neutral">
          <Loader2 className="h-3 w-3 animate-spin" />
          {t("inspector.modelIntrospection.dashboard.results.stepMaterializing")}
        </Badge>
      ) : null}
    </div>
  );
}

function getStepMaterializationClass(marker: ResultStepMarker | null): string {
  if (!marker) {
    return "transition-all duration-300";
  }
  if (marker.status === "pending" || marker.status === "running") {
    return "transition-all duration-300 opacity-95";
  }
  return "transition-all duration-300";
}

function isStepMaterializing(marker: ResultStepMarker | null): boolean {
  return marker?.status === "pending" || marker?.status === "running";
}

function ResultStepContainer({
  marker,
  className,
  children,
  t,
}: Readonly<{
  marker: ResultStepMarker | null;
  className?: string;
  children: ReactNode;
  t: (key: string) => string;
}>) {
  const materializing = isStepMaterializing(marker);
  return (
    <div
      className={cn("relative", className, getStepMaterializationClass(marker))}
      aria-busy={materializing}
      data-step-materializing={materializing ? "true" : "false"}
    >
      <div className={cn(materializing && "blur-[1.25px] saturate-75")}>{children}</div>
      {materializing ? (
        <div className="pointer-events-none absolute inset-0 rounded-2xl border border-white/10 bg-black/20">
          <div className="absolute right-3 top-3 inline-flex items-center gap-2 rounded-full border border-white/20 bg-black/60 px-2 py-1 text-xs text-zinc-200">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t("inspector.modelIntrospection.dashboard.results.stepMaterializing")}
          </div>
        </div>
      ) : null}
    </div>
  );
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
    avgMlpL2:
      typeof candidate.avg_mlp_l2 === "number"
        ? candidate.avg_mlp_l2
        : null,
    avgCosineSimilarity:
      typeof candidate.avg_cosine_similarity === "number"
        ? candidate.avg_cosine_similarity
        : null,
  };
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
  const analysisVisible = Boolean(analysisResult?.analysis);
  const analysisRunning = analysisResult?.status === "running";
  const analysisActive = analysisResult?.status === "running";
  const analysisCompleted = analysisResult?.status === "completed" && analysisVisible;
  const refreshedSnapshot = analysisResult?.snapshot_after ?? snapshot;
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
  const analysisTimelineFirstChunk =
    analysisTimeline.find((entry) => entry.id === "first_chunk") ?? null;
  const analysisTimelineProgress = analysisTimeline.reduce((current, entry) => {
    if (typeof entry.progress !== "number") {
      return current;
    }
    return Math.max(current, entry.progress);
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
  const analysisLayerInternalsPayload = analysisResult?.analysis?.layer_internals ?? null;
  const architectureGraphReadiness = buildModelArchitectureGraphReadiness(refreshedSnapshot);
  const analysisCapabilities = analysisResult?.analysis?.analysis_capabilities ?? null;
  const introspectionLevel = resolveIntrospectionLevel({
    analysisLevel: analysisResult?.analysis?.introspection_level,
    snapshotLevel: snapshot?.summary?.introspection_level ?? snapshot?.introspection_level,
  });
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
      buildInternalsCapabilityRow("hidden state", payload?.hidden_state),
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
    const totalCount = Number(analysisCapabilities.total_count ?? 4);
    const probeGateDetails = [
      `probe_status:${String(analysisCapabilities.probe_status ?? "unknown")}`,
      `probe_enabled:${analysisCapabilities.probe_enabled ? "yes" : "no"}`,
      `runtime_supported:${analysisCapabilities.runtime_supported ? "yes" : "no"}`,
      `model_whitelisted:${analysisCapabilities.model_whitelisted ? "yes" : "no"}`,
      `endpoint_configured:${analysisCapabilities.endpoint_configured ? "yes" : "no"}`,
    ];
    return {
      verdict: internalsVerdictLabel,
      tone: internalsVerdictTone,
      availableCount,
      totalCount,
      details: [
        ...internalsCapabilityRows.map((row) => `${row.label}:${row.reason}`),
        ...probeGateDetails,
      ],
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
    analysisVisible,
    analysisActive,
    analysisComparison,
    analysisResponse,
    analysisHighlights,
    analysisTimeline,
    analysisProcess,
    analysisFirstChunkMs,
    analysisStepCount,
    analysisTraceId,
    analysisStreaming,
    analysisPhase,
    analysisAnswerTone,
    answerStatusLabel,
    ragFocus,
    logitLens,
    attention,
    saliency,
    analysisLayerInternalsPayload,
    analysisCapabilities,
    introspectionLevel,
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
    visualMetrics,
    architectureGraphReadiness,
    selectedGraphNodeIdEffective,
    selectedGraphNode,
    selectedGraphNodeDetails,
    selectedGraphTypeHint,
  };
}

export function ModelIntrospectionDashboard() {
  const t = useTranslation();
  const { enabled: analysisMechanismEnabled } = useModelIntrospectionMechanism();
  const { snapshot, loading, error, loadSnapshot } = useModelIntrospectionSnapshot({
    autoLoad: false,
  });
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

  const {
    analysisVisible,
    analysisActive,
    analysisComparison,
    analysisResponse,
    analysisHighlights,
    analysisTimeline,
    analysisProcess,
    analysisFirstChunkMs,
    analysisStepCount,
    analysisTraceId,
    analysisStreaming,
    analysisPhase,
    analysisAnswerTone,
    answerStatusLabel,
    ragFocus,
    logitLens,
    attention,
    saliency,
    analysisLayerInternalsPayload,
    analysisCapabilities,
    introspectionLevel,
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
    visualMetrics,
    architectureGraphReadiness,
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

  const handleRunAnalysis = useCallback(async () => {
    let snapshotForAnalysis = snapshot;
    if (!snapshot) {
      snapshotForAnalysis = await loadSnapshot();
    }
    if (!snapshotForAnalysis) {
      return;
    }
    await runAnalysis();
  }, [loadSnapshot, runAnalysis, snapshot]);

  const handleResetPrompt = useCallback(() => {
    setAnalysisPrompt(
      t("inspector.modelIntrospection.dashboard.analysis.promptPlaceholder"),
    );
  }, [t]);

  const {
    allInternalsUnavailable,
    anyInternalsAvailable,
    isOllamaLiteRuntime,
    logitLensTitle,
    internalsHowToFull,
    unavailableInternalsRows,
    proxyInternalsRows,
    availableInternalsCount,
    internalsProcessing,
    ragStepMarker,
    responseStepMarker,
    snapshotStepMarker,
    logitStepMarker,
    attentionStepMarker,
    saliencyStepMarker,
  } = deriveDashboardRuntimeInternalsContext({
    analysisResult,
    snapshot,
    introspectionLevel,
    logitLens,
    attention,
    saliency,
    analysisTimeline,
    internalsCapabilityRows,
    analysisLoading,
    analysisStreaming,
    t,
  });

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

      <SnapshotLoadingPanel snapshot={snapshot} loading={loading} t={t} />
      <SnapshotErrorPanel error={error} t={t} />

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
          </div>
        </div>
      </Panel>

      {snapshot && (
        <Panel
          eyebrow="// results"
          title={t("inspector.modelIntrospection.dashboard.results.title")}
          description={t("inspector.modelIntrospection.dashboard.results.description")}
        >
          <div className="relative transition-all duration-300">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(340px,1fr)]">
          <div className="min-w-0">
          <ResultStepContainer marker={ragStepMarker} className="mb-4" t={t}>
            <ResultStepHeader marker={ragStepMarker} t={t} />
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
          </ResultStepContainer>
          <div className="mb-4">
            <div className="rounded-2xl border border-amber-400/25 bg-amber-500/10 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-amber-100">
                  {t("inspector.modelIntrospection.dashboard.results.internals.title")}
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={internalsVerdictTone}>{internalsVerdictLabel}</Badge>
                  <Badge tone="warning">{resolveProbeBudgetLabel(internalsProbeElapsedMs)}</Badge>
                </div>
              </div>
              <p className="mt-2 text-sm text-amber-50/90">
                {t("inspector.modelIntrospection.dashboard.results.internals.description")}
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
                {internalsProcessing && (
                  <Badge tone="neutral">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    {t("inspector.modelIntrospection.dashboard.results.internals.processing")}
                  </Badge>
                )}
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
            </div>
          </div>
          <ResultStepContainer marker={logitStepMarker} className="mb-4" t={t}>
            <ResultStepHeader marker={logitStepMarker} t={t} />
            <LogitLensPanel
              logitLens={logitLens}
              title={logitLensTitle}
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
              normalizedAriaLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.normalizedAria",
              )}
              rawAriaLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.rawAria",
              )}
              rawTokensUnavailableLabel={t(
                "inspector.modelIntrospection.dashboard.results.logitLens.rawTokensUnavailable",
              )}
            />
          </ResultStepContainer>
          {proxyInternalsRows.length > 0 && (
            <InternalsNoticeCard
              title={t("inspector.modelIntrospection.dashboard.results.internalsRecoveredTitle")}
              badgeLabel={t("inspector.modelIntrospection.dashboard.results.internalsRecoveredBadge")}
              message={t("inspector.modelIntrospection.dashboard.results.internalsRecoveredMessage")}
              tone="neutral"
              rows={proxyInternalsRows}
              rowsTone="neutral"
              rowKeyPrefix="proxy-open"
            />
          )}
          {anyInternalsAvailable && unavailableInternalsRows.length > 0 && (
            <InternalsNoticeCard
              title={t("inspector.modelIntrospection.dashboard.results.internalsPartialTitle")}
              message={t("inspector.modelIntrospection.dashboard.results.internalsPartialMessage")}
              tone={internalsVerdictTone}
              badgeLabel={internalsVerdictLabel}
              rows={unavailableInternalsRows}
              rowsTone="warning"
              rowKeyPrefix="partial"
              extraBadge={probeLimitsLabel}
            />
          )}
          {allInternalsUnavailable && (
            <InternalsNoticeCard
              title={t("inspector.modelIntrospection.dashboard.results.internalsUnavailableTitle")}
              message={t("inspector.modelIntrospection.dashboard.results.internalsUnavailableMessage")}
              tone={internalsVerdictTone}
              badgeLabel={internalsVerdictLabel}
              rows={unavailableInternalsRows}
              rowsTone="warning"
              rowKeyPrefix="unavailable"
              extraBadge={probeLimitsLabel}
            />
          )}
          {internalsHowToFull && (
            <div className="mb-4 rounded-2xl border border-cyan-400/25 bg-cyan-500/10 p-4">
              <p className="text-xs uppercase tracking-wide text-cyan-100">
                {t("inspector.modelIntrospection.dashboard.results.internalsHowToFullTitle")}
              </p>
              <p className="mt-2 text-sm text-cyan-50/90">{internalsHowToFull}</p>
            </div>
          )}
          <ResultStepContainer marker={attentionStepMarker} className="mb-4" t={t}>
            <ResultStepHeader marker={attentionStepMarker} t={t} />
            <AttentionPanel
              attention={attention}
              title={t("inspector.modelIntrospection.dashboard.results.attention.title")}
              emptyLabel={t("inspector.modelIntrospection.dashboard.results.attention.empty")}
              unavailableLabel={
                isOllamaLiteRuntime
                  ? t("inspector.modelIntrospection.dashboard.results.attention.unavailableLite")
                  : t("inspector.modelIntrospection.dashboard.results.attention.unavailable")
              }
            />
          </ResultStepContainer>
          <ResultStepContainer marker={saliencyStepMarker} className="mb-4" t={t}>
            <ResultStepHeader marker={saliencyStepMarker} t={t} />
            <SaliencyPanel
              saliency={saliency}
              title={t("inspector.modelIntrospection.dashboard.results.saliency.title")}
              emptyLabel={t("inspector.modelIntrospection.dashboard.results.saliency.empty")}
              unavailableLabel={
                isOllamaLiteRuntime
                  ? t("inspector.modelIntrospection.dashboard.results.saliency.unavailableLite")
                  : t("inspector.modelIntrospection.dashboard.results.saliency.unavailable")
              }
            />
          </ResultStepContainer>
          </div>
          <div className="min-w-0 xl:sticky xl:top-6 xl:self-start">
            <ResultStepContainer marker={responseStepMarker} className="mb-4" t={t}>
              <AnalysisResultsPanel
                responseStepLabel={formatStepLabel(t, responseStepMarker)}
                responseStepStatus={responseStepMarker?.status}
                snapshotStepLabel={formatStepLabel(t, snapshotStepMarker)}
                snapshotStepStatus={snapshotStepMarker?.status}
                analysisResponse={analysisResponse}
                analysisHighlights={analysisHighlights}
                answerStatusLabel={answerStatusLabel}
                analysisAnswerTone={analysisAnswerTone}
                managerAvailable={snapshot.model_manager.available}
                eventsCount={analysisResult?.analysis?.events.length ?? 0}
                analysisTimeline={analysisTimeline}
                analysisProcess={analysisProcess}
                analysisTraceStepCount={analysisStepCount}
                analysisTimelineStepCount={analysisStepCount}
                responseChars={analysisResponse.length}
                chunkCount={analysisResult?.analysis?.chunk_count ?? 0}
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
                streamProfile={analysisResult?.analysis?.stream_profile ?? null}
                evidenceCoverage={evidenceCoverage}
                inputProfile={inputProfile}
                generationProfile={generationProfile}
                runTrends={runTrends}
                operatorChecklist={operatorChecklist}
                internalsVerdict={internalsVerdict}
              />
            </ResultStepContainer>
          </div>
          </div>
          </div>
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

      <TechnicalLayerPanel
        snapshot={snapshot}
        graphLayerOpen={graphLayerOpen}
        analysisActive={analysisActive}
        architectureGraphReadiness={architectureGraphReadiness}
        analysisLayerInternalsPayload={analysisLayerInternalsPayload}
        selectedGraphNodeIdEffective={selectedGraphNodeIdEffective}
        selectedGraphNode={selectedGraphNode}
        selectedGraphNodeDetails={selectedGraphNodeDetails}
        selectedGraphTypeHint={selectedGraphTypeHint}
        onToggleGraphLayer={() => setGraphLayerOpen((current) => !current)}
        onSelectGraphNode={setSelectedGraphNodeId}
        t={t}
      />
    </div>
  );
}

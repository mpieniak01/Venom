"use client";

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import type cytoscapeType from "cytoscape";
import {
  clampPercent,
  formatCount,
  getAnalysisProgressBarColor,
  getGraphNodeTone,
  getOrbCoreShadow,
  getPackageRingColor,
  getPhaseTone,
  getLogitLensSignalTone,
  getDataSourceTone,
  getRagGroundingTone,
  shortenTraceId,
  timelineBadgeTone,
} from "@/components/inspector/model-introspection-dashboard-view-model";
import type {
  AnalysisPhase,
  AnalysisProcessTrace,
  AnalysisTimelinePath,
  AnalysisTimelineEntry,
  AnalysisLayerInternalsPayload,
  AnalysisMlpActivationPayload,
  AttentionModel,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
  LogitLensModel,
  OperatorConclusionModel,
  ModelArchitectureGraph,
  ModelArchitectureGraphEdge,
  ModelArchitectureGraphNode,
  ModelArchitectureGraphReadiness,
  RagFocusModel,
  SaliencyModel,
  SnapshotComparison,
  AnalysisLayerInternalsBlock,
} from "@/components/inspector/model-introspection-dashboard-types";

type AnalysisOrbProps = Readonly<{
  active: boolean;
  phase: AnalysisPhase;
  packageCoverage: number;
  chunks: number;
  elapsedMs: number;
  subtitle: string;
  traceId: string | null;
  firstChunkMs: number | null;
  stepCount: number;
  charsPerSecond: number | null;
  progress: number;
}>;

type AnalysisInputPanelProps = Readonly<{
  prompt: string;
  onPromptChange: (value: string) => void;
  onRunAnalysis: () => void;
  onResetPrompt: () => void;
  analysisLoading: boolean;
  analysisMechanismEnabled: boolean;
  analysisError: string | null;
  skipped: boolean;
  promptLabel: string;
  promptPlaceholder: string;
  runLabel: string;
  runningLabel: string;
  resetLabel: string;
  disabledLabel: string;
  skippedLabel: string;
}>;

type AnalysisResultsPanelProps = Readonly<{
  responseStepLabel?: string;
  responseStepStatus?: string;
  snapshotStepLabel?: string;
  snapshotStepStatus?: string;
  analysisResponse: string;
  analysisHighlights: string[];
  answerStatusLabel: string;
  analysisAnswerTone: BadgeTone;
  managerAvailable: boolean;
  eventsCount: number;
  analysisTimeline: AnalysisTimelineEntry[];
  analysisProcess: AnalysisProcessTrace | null;
  analysisTraceStepCount: number;
  analysisTimelineStepCount: number;
  responseChars: number;
  chunkCount: number;
  resultsHighlightsLabel: string;
  highlightsEmptyLabel: string;
  resultsVerdictLabel: string;
  resultsVerdictReady: string;
  resultsVerdictPending: string;
  advancedShowLabel: string;
  advancedHideLabel: string;
  advancedTitle: string;
  operatorConclusion: OperatorConclusionModel | null;
  operatorConclusionLabel: string;
  operatorConclusionConfidenceLabel: string;
  operatorConclusionPartialLabel: string;
  streamProfile:
    | {
        stream_quality?: string;
        chunk_intervals_ms?: number[];
        time_to_first_byte_ms?: number | null;
        time_to_first_byte_estimated?: boolean;
        time_to_first_byte_source?: string;
        chunk_interval_p50_ms?: number | null;
        chunk_interval_p95_ms?: number | null;
      }
    | null
    | undefined;
  evidenceCoverage:
    | {
        coverage_percent?: number;
        fragments_total?: number;
        fragments_linked?: number;
      }
    | null
    | undefined;
  inputProfile:
    | {
        prompt_tokens_est?: number;
        context_tokens_est?: number;
        system_tokens_est?: number;
        prompt_trimmed?: boolean;
      }
    | null
    | undefined;
  generationProfile:
    | {
        top_p?: number | null;
        top_p_requested?: number | null;
        top_p_applied?: number | null;
        top_p_source?: string;
        top_p_status?: string;
      }
    | null
    | undefined;
  runTrends:
    | {
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
      }
    | null
    | undefined;
  operatorChecklist:
    | Array<{
        id: string;
        label: string;
        status: "ok" | "warn";
        detail: string;
      }>
    | null
    | undefined;
  internalsVerdict:
    | {
        verdict: string;
        tone: BadgeTone;
        availableCount: number;
        totalCount: number;
        details: string[];
      }
    | null
    | undefined;
}>;

type AnalysisLiveResponsePanelProps = Readonly<{
  analysisStreaming: boolean;
  analysisResponse: string;
  answerStatusLabel: string;
  waitingTokenLabel: string;
  streamingLabel: string;
  statusBadgeLabel: string;
  statusBadgeTone: BadgeTone;
  streamModeLabel: string;
  streamModeTone: BadgeTone;
  fallbackLabel: string;
  fallbackTone: BadgeTone;
}>;

type RagFocusPanelProps = Readonly<{
  ragFocus: RagFocusModel | null;
  title: string;
  queryLabel: string;
  entitiesLabel: string;
  evidenceLabel: string;
  groundingLabel: string;
  activeLabel: string;
  emptyLabel: string;
  stepLabelPrefix: string;
  groundingStrongLabel: string;
  groundingMediumLabel: string;
  groundingWeakLabel: string;
  groundingUnknownLabel: string;
  sourceLabel: string;
  sourceRuntimeTraceLabel: string;
  sourceFallbackLabel: string;
  answerLinksLabel: string;
  answerLinksEmpty: string;
}>;

type LogitLensPanelProps = Readonly<{
  logitLens: LogitLensModel | null;
  title: string;
  emptyLabel: string;
  unavailableLabel: string;
  signalsLabel: string;
  tokensLabel: string;
  checkpointsLabel: string;
  signalEarlyUnstableLabel: string;
  signalLateStabilizedLabel: string;
  signalLowConfidenceLabel: string;
  signalStableLabel: string;
  changedLabel: string;
  stableLabel: string;
  sourceLabel: string;
  sourceRuntimeLabel: string;
  sourceUnavailableLabel: string;
  sourceFallbackWarning: string;
  normalizedAriaLabel: string;
  rawAriaLabel: string;
  rawTokensUnavailableLabel: string;
}>;

type AttentionPanelProps = Readonly<{
  attention: AttentionModel | null;
  title: string;
  emptyLabel: string;
  unavailableLabel: string;
}>;

type SaliencyPanelProps = Readonly<{
  saliency: SaliencyModel | null;
  title: string;
  emptyLabel: string;
  unavailableLabel: string;
}>;

function getGraphNodeClassName(selected: boolean): string {
  if (selected) {
    return "border-violet-400/60 bg-violet-500/10 shadow-[0_0_0_1px_rgba(139,92,246,0.35)]";
  }
  return "border-white/10 bg-black/20 hover:border-white/20 hover:bg-white/10";
}

function getPhaseStyles(phase: AnalysisPhase) {
  const styles: Record<
    AnalysisPhase,
    { ring: string; core: string; text: string }
  > = {
    idle: {
      ring: "border-zinc-600",
      core: "bg-zinc-800",
      text: "text-zinc-300",
    },
    requesting: {
      ring: "border-amber-500",
      core: "bg-amber-500",
      text: "text-amber-100",
    },
    streaming: {
      ring: "border-cyan-400",
      core: "bg-cyan-400",
      text: "text-cyan-100",
    },
    first_chunk: {
      ring: "border-violet-400",
      core: "bg-violet-400",
      text: "text-violet-100",
    },
    completed: {
      ring: "border-emerald-700",
      core: "bg-emerald-700",
      text: "text-emerald-100",
    },
  };
  return styles[phase];
}

function resolveOrbScale(args: {
  active: boolean;
  isAnimating: boolean;
  elapsedFactor: number;
}): string {
  const { active, isAnimating, elapsedFactor } = args;
  if (!active) {
    return "scale(1)";
  }
  if (!isAnimating) {
    return "scale(1)";
  }
  return `scale(${1 + elapsedFactor / 1000})`;
}

export function GraphNodeCard({
  label,
  kind,
  status,
  selected,
  onClick,
}: Readonly<{
  label: string;
  kind: string;
  status: string;
  selected: boolean;
  onClick: () => void;
}>) {
  const tone = getGraphNodeTone(status);
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Select graph node ${label}`}
      className={`rounded-2xl border px-4 py-3 text-left transition ${getGraphNodeClassName(selected)}`}
    >
      <div className="flex items-center justify-between gap-2">
        <Badge tone={tone}>{kind}</Badge>
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">{status}</span>
      </div>
      <p className="mt-3 font-mono text-sm text-white">{label}</p>
    </button>
  );
}

export function AnalysisOrbPanel({
  active,
  phase,
  packageCoverage,
  chunks,
  elapsedMs,
  subtitle,
  traceId,
  firstChunkMs,
  stepCount,
  charsPerSecond,
  progress,
}: AnalysisOrbProps) {
  const t = useTranslation();
  const intensity = clampPercent(chunks * 32);
  const elapsedFactor = clampPercent(elapsedMs / 120);
  const packageCoveragePercent = clampPercent(packageCoverage);
  const progressPercent = clampPercent(progress);
  const [displayProgress, setDisplayProgress] = useState(progressPercent);
  const displayProgressRef = useRef(progressPercent);
  const phaseLabel = t(`inspector.modelIntrospection.dashboard.analysis.phase.${phase}`);
  const phaseTone = getPhaseTone(phase);
  const colors = getPhaseStyles(phase);
  const packageRingColor = getPackageRingColor(packageCoveragePercent);
  const isAnimating = active && phase !== "completed";
  const activityTone: BadgeTone = active ? "success" : "neutral";
  const activityLabel = active
    ? t("inspector.modelIntrospection.dashboard.analysis.orbActivityActive")
    : t("inspector.modelIntrospection.dashboard.analysis.orbActivityIdle");
  const firstChunkAvailable = firstChunkMs != null;
  const firstChunkTone: BadgeTone = firstChunkAvailable ? "success" : "neutral";
  const firstChunkLabel = firstChunkAvailable
    ? `${formatCount(Math.round(firstChunkMs))} ${t("inspector.modelIntrospection.common.ms")}`
    : t("inspector.modelIntrospection.common.na");
  const traceLabel = traceId
    ? shortenTraceId(traceId)
    : t("inspector.modelIntrospection.dashboard.analysis.traceMissing");
  const firstChunkDetailLabel = firstChunkAvailable
    ? `${firstChunkMs.toFixed(1)} ${t("inspector.modelIntrospection.common.ms")}`
    : t("inspector.modelIntrospection.common.na");
  const rateLabel = formatRateLabel(charsPerSecond);
  const orbTransform = resolveOrbScale({ active, isAnimating, elapsedFactor });

  useEffect(() => {
    displayProgressRef.current = displayProgress;
  }, [displayProgress]);

  useEffect(() => {
    const hasRaf =
      typeof globalThis.requestAnimationFrame === "function" &&
      typeof globalThis.cancelAnimationFrame === "function";
    let rafId: number | null = null;
    let timeoutId: ReturnType<typeof globalThis.setTimeout> | null = null;
    const scheduleFrame = (callback: FrameRequestCallback): void => {
      if (hasRaf) {
        rafId = globalThis.requestAnimationFrame(callback);
        return;
      }
      timeoutId = globalThis.setTimeout(() => callback(performance.now()), 16);
    };
    let startAt = 0;
    const startValue = displayProgressRef.current;
    const targetValue = progressPercent;
    const distance = Math.abs(targetValue - startValue);
    const duration =
      distance < 0.25 ? 80 : Math.max(240, Math.min(1200, 160 + distance * 9));

    const animate = (timestamp: number) => {
      if (startAt === 0) {
        startAt = timestamp;
      }
      const elapsed = timestamp - startAt;
      const t = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayProgress(startValue + (targetValue - startValue) * eased);
      if (t < 1) {
        scheduleFrame(animate);
      }
    };

    scheduleFrame(animate);
    return () => {
      if (rafId != null) {
        globalThis.cancelAnimationFrame(rafId);
      }
      if (timeoutId != null) {
        globalThis.clearTimeout(timeoutId);
      }
    };
  }, [progressPercent]);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">
        {t("inspector.modelIntrospection.dashboard.analysis.orbTitle")}
      </p>
      <div className="mt-3 flex items-center gap-4">
        <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full">
          <div className="absolute inset-0 rounded-full border-2 border-zinc-800 bg-black shadow-[0_0_0_1px_rgba(0,0,0,0.9),0_0_18px_rgba(0,0,0,0.45)]" />
          <div className="absolute inset-1.5 rounded-full border border-black bg-black" />
          <div
            className={`absolute inset-2.5 rounded-full border-[3px] bg-black ${colors.ring} ${isAnimating ? "motion-safe:animate-pulse" : ""}`}
            style={{
              borderColor: packageRingColor,
              boxShadow: `0 0 0 1px rgba(0,0,0,0.75), 0 0 12px ${packageRingColor}22`,
            }}
          />
          <div
            className={`absolute inset-6 rounded-full ${colors.core} ${isAnimating ? "motion-safe:animate-pulse" : ""}`}
            style={{
              transform: orbTransform,
              boxShadow: getOrbCoreShadow(phase),
            }}
          />
          <div className="relative h-full w-full rounded-full" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <p className="text-sm text-zinc-200">{subtitle}</p>
          <div className="flex flex-wrap gap-2">
            <Badge tone={activityTone}>{activityLabel}</Badge>
            <Badge tone={phaseTone}>{phaseLabel}</Badge>
            <Badge tone="neutral">{formatCount(Math.round(elapsedMs))} ms</Badge>
            <Badge tone={firstChunkTone}>
              {t("inspector.modelIntrospection.dashboard.analysis.firstChunk")} {firstChunkLabel}
            </Badge>
            <Badge tone={intensity > 0 ? "warning" : "neutral"}>
              {t("inspector.modelIntrospection.dashboard.analysis.intensity")}{" "}
              {formatCount(Math.round(intensity))}%
            </Badge>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
            <div className="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
              <span>{t("inspector.modelIntrospection.dashboard.analysis.coverage")}</span>
              <span>{formatCount(Math.round(packageCoveragePercent))}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${packageCoveragePercent}%`,
                  backgroundColor: packageRingColor,
                }}
              />
            </div>
            <div className="mt-3 flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
              <span>{t("inspector.modelIntrospection.dashboard.analysis.analysis")}</span>
              <span>{formatCount(Math.round(displayProgress))}%</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full transition-all duration-500"
                style={{
                  width: `${displayProgress}%`,
                  backgroundColor: getAnalysisProgressBarColor(phase),
                }}
              />
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.analysis.trace")}
                </p>
                <p className="mt-1 font-mono text-xs text-white">{traceLabel}</p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.analysis.steps")}
                </p>
                <p className="mt-1 font-mono text-xs text-white">{formatCount(stepCount)}</p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.analysis.firstChunk")}
                </p>
                <p className="mt-1 font-mono text-xs text-white">{firstChunkDetailLabel}</p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.analysis.rate")}
                </p>
                <p className="mt-1 font-mono text-xs text-white">{rateLabel}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function AnalysisInputPanel(props: AnalysisInputPanelProps) {
  const {
    prompt,
    onPromptChange,
    onRunAnalysis,
    onResetPrompt,
    analysisLoading,
    analysisMechanismEnabled,
    analysisError,
    skipped,
    promptLabel,
    promptPlaceholder,
    runLabel,
    runningLabel,
    resetLabel,
    disabledLabel,
    skippedLabel,
  } = props;

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-xs uppercase tracking-wide text-zinc-500" htmlFor="model-introspection-prompt">
          {promptLabel}
        </label>
        <textarea
          id="model-introspection-prompt"
          value={prompt}
          onChange={(event) => onPromptChange(event.target.value)}
          className="min-h-28 w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-sm text-white outline-none transition focus:border-violet-400/60"
          placeholder={promptPlaceholder}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button
          onClick={onRunAnalysis}
          disabled={analysisLoading || !analysisMechanismEnabled}
        >
          {analysisLoading ? runningLabel : runLabel}
        </Button>
        <Button variant="ghost" onClick={onResetPrompt} disabled={analysisLoading}>
          {resetLabel}
        </Button>
      </div>
      {!analysisMechanismEnabled && (
        <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-300">
          {disabledLabel}
        </div>
      )}
      {analysisError && (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {analysisError}
        </div>
      )}
      {skipped && (
        <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-300">
          {skippedLabel}
        </div>
      )}
    </div>
  );
}

function renderVerdictCopy(args: {
  hasResponse: boolean;
  verdictReady: string;
  verdictPending: string;
}): string {
  if (args.hasResponse) {
    return args.verdictReady;
  }
  return args.verdictPending;
}

function renderManagerMetricsBadge(
  available: boolean,
  t: (key: string, replacements?: Record<string, string | number>) => string,
): string {
  if (available) {
    return t("inspector.modelIntrospection.dashboard.results.managerMetricsOn");
  }
  return t("inspector.modelIntrospection.dashboard.results.managerMetricsOff");
}

function getRagStepTone(status: "done" | "running" | "pending"): BadgeTone {
  if (status === "done") {
    return "success";
  }
  if (status === "running") {
    return "warning";
  }
  return "neutral";
}

function getTimelinePathTone(path: AnalysisTimelinePath | undefined): BadgeTone {
  if (path === "internals_path") {
    return "warning";
  }
  if (path === "answer_path") {
    return "success";
  }
  return "neutral";
}

function resolveGroundingLabel(args: {
  ragFocus: RagFocusModel;
  groundingStrongLabel: string;
  groundingMediumLabel: string;
  groundingWeakLabel: string;
  groundingUnknownLabel: string;
}): string {
  const {
    ragFocus,
    groundingStrongLabel,
    groundingMediumLabel,
    groundingWeakLabel,
    groundingUnknownLabel,
  } = args;
  if (ragFocus.grounding === "strong") {
    return groundingStrongLabel;
  }
  if (ragFocus.grounding === "medium") {
    return groundingMediumLabel;
  }
  if (ragFocus.grounding === "weak") {
    return groundingWeakLabel;
  }
  return groundingUnknownLabel;
}

export function RagFocusPanel(props: RagFocusPanelProps) {
  const {
    ragFocus,
    title,
    queryLabel,
    entitiesLabel,
    evidenceLabel,
    groundingLabel,
    activeLabel,
    emptyLabel,
    stepLabelPrefix,
    groundingStrongLabel,
    groundingMediumLabel,
    groundingWeakLabel,
    groundingUnknownLabel,
    sourceLabel,
    sourceRuntimeTraceLabel,
    sourceFallbackLabel,
    answerLinksLabel,
    answerLinksEmpty,
  } = props;

  if (!ragFocus) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="mt-3 text-sm text-zinc-400">{emptyLabel}</p>
      </div>
    );
  }

  const groundingResolvedLabel = resolveGroundingLabel({
    ragFocus,
    groundingStrongLabel,
    groundingMediumLabel,
    groundingWeakLabel,
    groundingUnknownLabel,
  });

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">{queryLabel}</p>
      <p className="mt-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-zinc-200">
        {ragFocus.query}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={getDataSourceTone(ragFocus.source)}>
          {sourceLabel}{" "}
          {ragFocus.source === "runtime_trace"
            ? sourceRuntimeTraceLabel
            : sourceFallbackLabel}
        </Badge>
        <Badge tone="neutral">
          {entitiesLabel} {formatCount(ragFocus.entities.length)}
        </Badge>
        <Badge tone="neutral">
          {evidenceLabel} {formatCount(ragFocus.evidenceEdges.length)}
        </Badge>
        <Badge tone={getRagGroundingTone(ragFocus.grounding)}>
          {groundingLabel} {groundingResolvedLabel}
        </Badge>
        <Badge tone="neutral">
          {activeLabel} {formatCount(ragFocus.activeEntityIds.length)}
        </Badge>
      </div>
      <div className="mt-3 grid gap-2 xl:grid-cols-2">
        {ragFocus.entities.map((entity) => (
          <div
            key={entity.id}
            className={`rounded-xl border px-3 py-2 text-xs ${
              entity.active
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-100"
                : "border-white/10 bg-black/20 text-zinc-300"
            }`}
          >
            <p className="font-mono">{entity.label}</p>
            <p className="mt-1 uppercase tracking-wide text-zinc-500">{entity.kind}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-2">
        {ragFocus.evidenceEdges.slice(0, 8).map((edge, index) => (
          <div
            key={`${edge.from}-${edge.to}-${index}`}
            className={`rounded-xl border px-3 py-2 text-xs ${
              edge.active
                ? "border-cyan-400/35 bg-cyan-400/10 text-cyan-100"
                : "border-white/10 bg-black/20 text-zinc-300"
            }`}
          >
            <p className="font-mono">
              {edge.from} → {edge.to}
            </p>
            <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-zinc-500">{edge.id}</p>
            <p className="mt-1 uppercase tracking-wide text-zinc-500">{edge.label}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{answerLinksLabel}</p>
        <div className="mt-2 space-y-2">
          {ragFocus.answerEvidenceLinks.length > 0 ? (
            ragFocus.answerEvidenceLinks.map((link) => (
              <div key={link.id} className="rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-zinc-300">
                <p className="text-zinc-100">{link.fragment}</p>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                  {link.edgeIds.join(" · ")}
                </p>
              </div>
            ))
          ) : (
            <p className="text-xs text-zinc-400">{answerLinksEmpty}</p>
          )}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {ragFocus.steps.map((step) => (
          <Badge key={step.id} tone={getRagStepTone(step.status)}>
            {stepLabelPrefix} {step.id} · {step.status}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function formatCheckpointConfidence(value: number | null): string {
  if (value == null) {
    return "—";
  }
  return `${Math.round(value * 100)}%`;
}

function formatCheckpointScore(value: number): string {
  return value.toFixed(3);
}

function renderSignalLabel(args: {
  active: boolean;
  activeLabel: string;
  stableLabel: string;
}): string {
  if (args.active) {
    return args.activeLabel;
  }
  return args.stableLabel;
}

function resolveNoiseTone(noiseRatio: number): BadgeTone {
  if (noiseRatio >= 0.7) {
    return "warning";
  }
  if (noiseRatio >= 0.35) {
    return "neutral";
  }
  return "success";
}

function resolveNoiseLabel(noiseRatio: number): string {
  if (noiseRatio >= 0.7) {
    return "noise high";
  }
  if (noiseRatio >= 0.35) {
    return "noise medium";
  }
  return "noise low";
}

export function LogitLensPanel(props: LogitLensPanelProps) {
  const {
    logitLens,
    title,
    emptyLabel,
    unavailableLabel,
    signalsLabel,
    tokensLabel,
    checkpointsLabel,
    signalEarlyUnstableLabel,
    signalLateStabilizedLabel,
    signalLowConfidenceLabel,
    signalStableLabel,
    changedLabel,
    stableLabel,
    sourceLabel,
    sourceRuntimeLabel,
    sourceUnavailableLabel,
    sourceFallbackWarning,
    normalizedAriaLabel,
    rawAriaLabel,
    rawTokensUnavailableLabel,
  } = props;
  const [tokenViewMode, setTokenViewMode] = useState<"normalized" | "raw">("normalized");

  if (!logitLens) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="mt-3 text-sm text-zinc-400">{emptyLabel}</p>
      </div>
    );
  }

  const hasCheckpointData = logitLens.checkpoints.length > 0;
  const hasTokenData = logitLens.raw_input_tokens.length > 0 || logitLens.raw_output_tokens.length > 0;
  const available = hasCheckpointData || hasTokenData;
  if (!available) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone="warning">{logitLens.status}</Badge>
          {logitLens.code && <Badge tone="neutral">{logitLens.code}</Badge>}
        </div>
        <p className="mt-3 text-sm text-zinc-400">
          {logitLens.message || unavailableLabel}
        </p>
      </div>
    );
  }

  const signals = logitLens.signals;
  const showRaw = tokenViewMode === "raw";
  const inputPreview = showRaw
    ? logitLens.raw_input_tokens.join(" · ")
    : logitLens.input_tokens.join(" · ");
  const outputPreview = showRaw
    ? logitLens.raw_output_tokens.join(" · ")
    : logitLens.output_tokens.join(" · ");

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={getDataSourceTone(logitLens.source)}>
          {sourceLabel}{" "}
          {logitLens.source === "probe_runtime"
            ? sourceRuntimeLabel
            : sourceUnavailableLabel}
        </Badge>
        <Badge tone={logitLens.interpretability.interpretable ? "success" : "warning"}>
          {logitLens.interpretability.interpretable ? "interpretable" : "not interpretable"}
        </Badge>
        <Badge tone="neutral">
          confidence {logitLens.interpretability.confidence_band}
        </Badge>
        <Badge tone={resolveNoiseTone(logitLens.interpretability.token_noise_ratio)}>
          {resolveNoiseLabel(logitLens.interpretability.token_noise_ratio)}
        </Badge>
        <Badge tone="neutral">
          noise ratio {(logitLens.interpretability.token_noise_ratio * 100).toFixed(0)}%
        </Badge>
        <Badge tone={getLogitLensSignalTone(signals.early_unstable)}>
          {renderSignalLabel({
            active: signals.early_unstable,
            activeLabel: signalEarlyUnstableLabel,
            stableLabel: signalStableLabel,
          })}
        </Badge>
        <Badge tone={getLogitLensSignalTone(signals.late_stabilized)}>
          {renderSignalLabel({
            active: signals.late_stabilized,
            activeLabel: signalLateStabilizedLabel,
            stableLabel: signalStableLabel,
          })}
        </Badge>
        <Badge tone={getLogitLensSignalTone(signals.low_confidence_path)}>
          {renderSignalLabel({
            active: signals.low_confidence_path,
            activeLabel: signalLowConfidenceLabel,
            stableLabel: signalStableLabel,
          })}
        </Badge>
        <Button
          variant={showRaw ? "ghost" : "outline"}
          size="sm"
          onClick={() => setTokenViewMode("normalized")}
          aria-label={normalizedAriaLabel}
        >
          normalized
        </Button>
        <Button
          variant={showRaw ? "outline" : "ghost"}
          size="sm"
          onClick={() => setTokenViewMode("raw")}
          aria-label={rawAriaLabel}
        >
          raw
        </Button>
      </div>
      {logitLens.source !== "probe_runtime" && (
        <p className="mt-2 text-xs text-amber-200/90">{sourceFallbackWarning}</p>
      )}
      <div className="mt-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-300">
        <p className="uppercase tracking-wide text-zinc-500">{tokensLabel}</p>
        <p className="mt-1 break-words">{inputPreview || "—"}</p>
        <p className="mt-1 text-zinc-500">→</p>
        <p className="mt-1 break-words">{outputPreview || "—"}</p>
        {showRaw && logitLens.raw_output_tokens.length === 0 && (
          <p className="mt-2 text-[11px] text-amber-200/90">{rawTokensUnavailableLabel}</p>
        )}
      </div>
      <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">{checkpointsLabel}</p>
      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        {logitLens.checkpoints.map((checkpoint) => {
          const topCandidates = checkpoint.top_k;
          return (
            <div
              key={checkpoint.id}
              className="rounded-xl border border-white/10 bg-black/20 px-3 py-2"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-mono text-xs text-zinc-100">
                  {checkpoint.percent}% · layer {checkpoint.layer}
                </p>
                <Badge tone={checkpoint.changed ? "warning" : "success"}>
                  {checkpoint.changed ? changedLabel : stableLabel}
                </Badge>
              </div>
              <div className="mt-2 space-y-1">
                {topCandidates.map((candidate, index) => (
                  <p key={`${checkpoint.id}-${candidate.token}-${index}`} className="text-xs text-zinc-300">
                    {index + 1}.{" "}
                    {showRaw ? (candidate.raw_token ?? candidate.token) : candidate.token} (
                    {formatCheckpointScore(candidate.score)})
                  </p>
                ))}
              </div>
              <p className="mt-2 text-[11px] uppercase tracking-wide text-zinc-500">
                {signalsLabel} {formatCheckpointConfidence(checkpoint.confidence)}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function AttentionPanel(props: AttentionPanelProps) {
  const { attention, title, emptyLabel, unavailableLabel } = props;

  if (!attention) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="mt-3 text-sm text-zinc-400">{emptyLabel}</p>
      </div>
    );
  }

  const available = attention.status === "ok" && attention.layers.length > 0;
  if (!available) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone="warning">{attention.status}</Badge>
          {attention.code && <Badge tone="neutral">{attention.code}</Badge>}
        </div>
        <p className="mt-3 text-sm text-zinc-400">{attention.message || unavailableLabel}</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={getDataSourceTone(attention.source)}>
          source {attention.source === "probe_runtime" ? "runtime probe" : "fallback"}
        </Badge>
        <Badge tone="neutral">layers {attention.layers.length}</Badge>
      </div>
      <div className="mt-3 space-y-3">
        {attention.layers.slice(0, 3).map((layer) => (
          <div
            key={`layer-${layer.layer}`}
            className="rounded-xl border border-white/10 bg-black/20 px-3 py-2"
          >
            <p className="font-mono text-xs text-zinc-100">layer {layer.layer}</p>
            <div className="mt-2 grid gap-2 lg:grid-cols-2">
              {layer.heads.slice(0, 2).map((head) => (
                <div
                  key={`head-${layer.layer}-${head.head}`}
                  className="rounded-lg border border-white/10 bg-black/30 px-3 py-2"
                >
                  <p className="text-xs uppercase tracking-wide text-zinc-500">head {head.head}</p>
                  <div className="mt-2 space-y-1">
                    {head.top_links.slice(0, 3).map((link, index) => (
                      <p
                        key={`link-${layer.layer}-${head.head}-${index}`}
                        className="text-xs text-zinc-300"
                      >
                        {index + 1}. {link.from_token} → {link.to_token} ({link.weight.toFixed(3)})
                      </p>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function SaliencyPanel(props: SaliencyPanelProps) {
  const { saliency, title, emptyLabel, unavailableLabel } = props;

  if (!saliency) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="mt-3 text-sm text-zinc-400">{emptyLabel}</p>
      </div>
    );
  }

  const available = saliency.status === "ok" && saliency.token_weights.length > 0;
  if (!available) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Badge tone="warning">{saliency.status}</Badge>
          {saliency.code && <Badge tone="neutral">{saliency.code}</Badge>}
        </div>
        <p className="mt-3 text-sm text-zinc-400">{saliency.message || unavailableLabel}</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge tone={getDataSourceTone(saliency.source)}>
          source {saliency.source === "probe_runtime" ? "runtime probe" : "fallback"}
        </Badge>
        <Badge tone="neutral">method {saliency.method ?? "n/a"}</Badge>
        {saliency.target_output_token && (
          <Badge tone="neutral">
            target {saliency.target_output_token}
          </Badge>
        )}
      </div>
      <div className="mt-3 grid gap-2 lg:grid-cols-2">
        {saliency.token_weights.slice(0, 8).map((item, index) => {
          const magnitude = Math.min(100, Math.max(0, Math.abs(item.weight) * 100));
          return (
            <div
              key={`saliency-${item.token_index}-${index}`}
              className="rounded-xl border border-white/10 bg-black/20 px-3 py-2"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="font-mono text-xs text-zinc-100">{item.token}</p>
                <Badge tone={item.weight >= 0 ? "success" : "warning"}>
                  {item.weight.toFixed(3)}
                </Badge>
              </div>
              <div className="mt-2 h-1.5 rounded bg-zinc-800">
                <div
                  className="h-1.5 rounded bg-cyan-400"
                  style={{ width: `${magnitude}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function renderProcessFirstChunkLabel(firstChunkMs: number | null | undefined): string {
  if (firstChunkMs != null) {
    return `${firstChunkMs.toFixed(1)} ms`;
  }
  return "—";
}

function formatRateLabel(charsPerSecond: number | null): string {
  if (charsPerSecond == null) {
    return "—";
  }
  return `${charsPerSecond.toFixed(1)} chars/s`;
}

function renderAnalysisResponseStateLabel(args: {
  analysisResponse: string;
  presentedLabel: string;
  awaitingDataLabel: string;
}): string {
  const { analysisResponse, presentedLabel, awaitingDataLabel } = args;
  if (analysisResponse) {
    return presentedLabel;
  }
  return awaitingDataLabel;
}

function renderManagerBadgeTone(managerAvailable: boolean): BadgeTone {
  if (managerAvailable) {
    return "success";
  }
  return "warning";
}

function renderBooleanTelemetryBadge(args: {
  flag: boolean | null | undefined;
  trueLabel: string;
  falseLabel: string;
}): { tone: BadgeTone; label: string } {
  if (args.flag) {
    return { tone: "warning", label: args.trueLabel };
  }
  return { tone: "success", label: args.falseLabel };
}

function renderTopPStatusBadge(
  topPStatus: string | null | undefined,
): { tone: BadgeTone; key: string } {
  if (topPStatus === "runtime_confirmed") {
    return { tone: "success", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusConfirmed" };
  }
  if (topPStatus === "requested_only") {
    return { tone: "warning", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusRequestedOnly" };
  }
  return { tone: "neutral", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusUnavailable" };
}

function renderStreamOpenSourceBadge(
  firstByteSource: string | null | undefined,
): { tone: BadgeTone; key: string } {
  if (firstByteSource === "runtime_ttfb") {
    return { tone: "success", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusConfirmed" };
  }
  if (firstByteSource === "estimated_stream_open") {
    return { tone: "warning", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusEstimated" };
  }
  return { tone: "neutral", key: "inspector.modelIntrospection.dashboard.results.telemetry.statusUnavailable" };
}

type AnalysisRunTrendsCardProps = Readonly<{
  runTrends:
    | {
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
      }
    | null
    | undefined;
}>;

function formatAvgFirstContentMs(value: number | null, naLabel: string, msLabel: string): string {
  if (value === null) {
    return naLabel;
  }
  return `${value.toFixed(1)} ${msLabel}`;
}

function formatAvgNoiseRatio(value: number | null, naLabel: string): string {
  if (value === null) {
    return naLabel;
  }
  return `${(value * 100).toFixed(0)}%`;
}

function AnalysisRunTrendsCard(props: AnalysisRunTrendsCardProps) {
  const { runTrends } = props;
  const t = useTranslation();
  if (!runTrends) {
    return (
      <p className="mt-3 text-sm text-zinc-400">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.empty")}
      </p>
    );
  }
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.runs")} {runTrends.runs}
      </Badge>
      <Badge tone={runTrends.runtimeTraceRate >= 80 ? "success" : "warning"}>
        {t("inspector.modelIntrospection.dashboard.results.runTrends.runtimeTrace")}{" "}
        {runTrends.runtimeTraceRate.toFixed(0)}%
      </Badge>
      <Badge tone={runTrends.probeRuntimeRate >= 80 ? "success" : "warning"}>
        {t("inspector.modelIntrospection.dashboard.results.runTrends.probeRuntime")}{" "}
        {runTrends.probeRuntimeRate.toFixed(0)}%
      </Badge>
      <Badge tone={runTrends.highCoverageRate >= 80 ? "success" : "warning"}>
        {t("inspector.modelIntrospection.dashboard.results.runTrends.highCoverage")}{" "}
        {runTrends.highCoverageRate.toFixed(0)}%
      </Badge>
      <Badge tone={runTrends.liveStreamingRate >= 50 ? "success" : "warning"}>
        {t("inspector.modelIntrospection.dashboard.results.runTrends.liveStreaming")}{" "}
        {runTrends.liveStreamingRate.toFixed(0)}%
      </Badge>
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.avgFirstChunk")}{" "}
        {formatAvgFirstContentMs(
          runTrends.avgFirstContentMs,
          t("inspector.modelIntrospection.common.na"),
          t("inspector.modelIntrospection.common.ms"),
        )}
      </Badge>
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.avgNoise")}{" "}
        {formatAvgNoiseRatio(
          runTrends.avgNoiseRatio,
          t("inspector.modelIntrospection.common.na"),
        )}
      </Badge>
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.avgMlpL2")}{" "}
        {runTrends.avgMlpL2 !== null
          ? runTrends.avgMlpL2.toFixed(4)
          : t("inspector.modelIntrospection.common.na")}
      </Badge>
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.avgCosineSimilarity")}{" "}
        {runTrends.avgCosineSimilarity !== null
          ? runTrends.avgCosineSimilarity.toFixed(4)
          : t("inspector.modelIntrospection.common.na")}
      </Badge>
      <Badge tone="neutral">
        {t("inspector.modelIntrospection.dashboard.results.runTrends.window")}{" "}
        {runTrends.window}
      </Badge>
    </div>
  );
}

export function AnalysisResultsPanel(props: AnalysisResultsPanelProps) {
  const t = useTranslation();
  const {
    responseStepLabel,
    responseStepStatus,
    snapshotStepLabel,
    snapshotStepStatus,
    analysisResponse,
    analysisHighlights,
    answerStatusLabel,
    analysisAnswerTone,
    managerAvailable,
    eventsCount,
    analysisTimeline,
    analysisProcess,
    analysisTraceStepCount,
    analysisTimelineStepCount,
    responseChars,
    chunkCount,
    resultsHighlightsLabel,
    highlightsEmptyLabel,
    resultsVerdictLabel,
    resultsVerdictReady,
    resultsVerdictPending,
    advancedShowLabel,
    advancedHideLabel,
    advancedTitle,
    operatorConclusion,
    operatorConclusionLabel,
    operatorConclusionConfidenceLabel,
    operatorConclusionPartialLabel,
    streamProfile,
    evidenceCoverage,
    inputProfile,
    generationProfile,
    runTrends,
    operatorChecklist,
    internalsVerdict,
  } = props;
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const managerBadgeText = renderManagerMetricsBadge(managerAvailable, t);
  const managerBadgeTone = renderManagerBadgeTone(managerAvailable);
  const responseStateLabel = renderAnalysisResponseStateLabel({
    analysisResponse,
    presentedLabel: t("inspector.modelIntrospection.dashboard.results.responseStatePresented"),
    awaitingDataLabel: t("inspector.modelIntrospection.dashboard.results.responseStateAwaitingData"),
  });
  const responseShapeBadge = renderBooleanTelemetryBadge({
    flag: analysisProcess?.response_truncated,
    trueLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.responseTruncated"),
    falseLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.responseComplete"),
  });
  const promptShapeBadge = renderBooleanTelemetryBadge({
    flag: analysisProcess?.prompt_trimmed,
    trueLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.promptTrimmed"),
    falseLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.promptIntact"),
  });
  const contextShapeBadge = renderBooleanTelemetryBadge({
    flag: analysisProcess?.context_preview_truncated,
    trueLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.contextTruncated"),
    falseLabel: t("inspector.modelIntrospection.dashboard.results.telemetry.contextIntact"),
  });
  const topPStatusBadge = renderTopPStatusBadge(generationProfile?.top_p_status);
  const streamOpenSourceBadge = renderStreamOpenSourceBadge(
    streamProfile?.time_to_first_byte_source,
  );

  return (
    <div className="space-y-4">
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          {responseStepLabel ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge tone="success">{responseStepLabel}</Badge>
              {responseStepStatus ? <Badge tone="neutral">{responseStepStatus}</Badge> : null}
            </div>
          ) : null}
          <p className="text-xs uppercase tracking-wide text-zinc-500">{resultsHighlightsLabel}</p>
          <div className="mt-3 space-y-2">
            {analysisHighlights.length > 0 ? (
              analysisHighlights.map((highlight, index) => (
                <div
                  key={`${highlight}-${index}`}
                  className="rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm text-zinc-200"
                >
                  {highlight}
                </div>
              ))
            ) : (
              <p className="text-sm text-zinc-400">{highlightsEmptyLabel}</p>
            )}
          </div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">{resultsVerdictLabel}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Badge tone={analysisAnswerTone}>
              {responseStateLabel}
            </Badge>
            <Badge tone={managerBadgeTone}>{managerBadgeText}</Badge>
          </div>
          <p className="mt-3 text-sm text-zinc-300">
            {renderVerdictCopy({
              hasResponse: Boolean(analysisResponse),
              verdictReady: resultsVerdictReady,
              verdictPending: resultsVerdictPending,
            })}
          </p>
          {operatorConclusion && (
            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 px-3 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={operatorConclusion.tone}>
                  {operatorConclusionLabel} {operatorConclusion.verdict}
                </Badge>
                <Badge tone="neutral">
                  {operatorConclusionConfidenceLabel} {operatorConclusion.confidenceTier}
                </Badge>
                {operatorConclusion.partial && (
                  <Badge tone="warning">{operatorConclusionPartialLabel}</Badge>
                )}
              </div>
              <ul className="mt-2 space-y-1 text-xs text-zinc-300">
                {operatorConclusion.reasons.map((reason, index) => (
                  <li key={`${reason}-${index}`}>• {reason}</li>
                ))}
              </ul>
              {operatorConclusion.reasonCodes.length > 0 && (
                <p className="mt-2 font-mono text-[10px] uppercase tracking-wide text-zinc-500">
                  {operatorConclusion.reasonCodes.join(" · ")}
                </p>
              )}
            </div>
          )}
          {internalsVerdict && (
            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 px-3 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={internalsVerdict.tone}>
                  internals verdict {internalsVerdict.verdict}
                </Badge>
                <Badge tone="neutral">
                  coverage {internalsVerdict.availableCount}/{internalsVerdict.totalCount}
                </Badge>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {internalsVerdict.details.map((detail) => (
                  <Badge key={detail} tone="neutral">
                    {detail}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          {snapshotStepLabel ? (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge tone="success">{snapshotStepLabel}</Badge>
              {snapshotStepStatus ? <Badge tone="neutral">{snapshotStepStatus}</Badge> : null}
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={analysisAnswerTone}>{answerStatusLabel}</Badge>
            <Badge tone={managerBadgeTone}>{managerBadgeText}</Badge>
            <Badge tone="neutral">
              {eventsCount} {t("inspector.modelIntrospection.dashboard.results.telemetry.streamEvents")}
            </Badge>
          </div>
          <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.results.analysisProcess")}
          </p>
          <div className="mt-3 space-y-2">
            {analysisTimeline.map((step, index) => (
              <div
                key={`${step.id}:${step.path ?? "none"}:${step.at_ms}:${index}`}
                className="rounded-xl border border-white/10 bg-black/20 px-3 py-3"
              >
                <div className="flex flex-col gap-2">
                  <div className="min-w-0">
                    <p className="text-sm text-white">{step.label}</p>
                    <p className="mt-1 text-xs text-zinc-400 break-words whitespace-pre-wrap [overflow-wrap:anywhere] max-w-full">
                      {step.detail}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {step.path && (
                      <Badge tone={getTimelinePathTone(step.path)}>{step.path}</Badge>
                    )}
                    {typeof step.progress === "number" && (
                      <Badge tone="neutral">{formatCount(Math.round(step.progress))}%</Badge>
                    )}
                    {step.reason_code && step.status !== "done" && (
                      <Badge tone="danger">{step.reason_code}</Badge>
                    )}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={timelineBadgeTone(step.status)}>{step.status}</Badge>
                    <span className="font-mono text-xs text-zinc-400">{step.at_ms.toFixed(1)} ms</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.results.processTelemetry")}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.results.telemetry.trace")}{" "}
              {analysisProcess?.status ?? t("inspector.modelIntrospection.common.na")}
            </Badge>
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.results.telemetry.traceSteps")}{" "}
              {formatCount(analysisTraceStepCount)}
            </Badge>
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.results.telemetry.processSteps")}{" "}
              {formatCount(analysisTimelineStepCount)}
            </Badge>
            <Badge tone={typeof analysisProcess?.first_chunk_ms === "number" ? "success" : "neutral"}>
              {t("inspector.modelIntrospection.dashboard.analysis.firstChunk")}{" "}
              {renderProcessFirstChunkLabel(analysisProcess?.first_chunk_ms)}
            </Badge>
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.results.telemetry.chunks")}{" "}
              {analysisProcess?.response_chunks ?? chunkCount}
            </Badge>
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.results.telemetry.chars")}{" "}
              {analysisProcess?.response_chars ?? responseChars}
            </Badge>
            <Badge tone={responseShapeBadge.tone}>{responseShapeBadge.label}</Badge>
            <Badge tone={promptShapeBadge.tone}>{promptShapeBadge.label}</Badge>
            <Badge tone={contextShapeBadge.tone}>{contextShapeBadge.label}</Badge>
            {typeof evidenceCoverage?.coverage_percent === "number" && (
              <Badge tone={evidenceCoverage.coverage_percent >= 60 ? "success" : "warning"}>
                {t("inspector.modelIntrospection.dashboard.analysis.coverage")}{" "}
                {evidenceCoverage.coverage_percent.toFixed(1)}%
              </Badge>
            )}
            {typeof evidenceCoverage?.fragments_total === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.fragments")}{" "}
                {evidenceCoverage.fragments_linked ?? 0}/{evidenceCoverage.fragments_total}
              </Badge>
            )}
            {streamProfile?.stream_quality && (
              <Badge tone={streamProfile.stream_quality === "live_streaming" ? "success" : "warning"}>
                {t("inspector.modelIntrospection.dashboard.results.telemetry.stream")}{" "}
                {t(`inspector.modelIntrospection.dashboard.analysis.streamMode.${streamProfile.stream_quality}`)}
              </Badge>
            )}
            {Array.isArray(streamProfile?.chunk_intervals_ms) && streamProfile.chunk_intervals_ms.length > 0 && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.intervals")}{" "}
                {streamProfile.chunk_intervals_ms.length}
              </Badge>
            )}
            {typeof inputProfile?.prompt_tokens_est === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.promptTokens")}{" "}
                {inputProfile.prompt_tokens_est}
              </Badge>
            )}
            {typeof inputProfile?.context_tokens_est === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.contextTokens")}{" "}
                {inputProfile.context_tokens_est}
              </Badge>
            )}
            {typeof inputProfile?.system_tokens_est === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.systemTokens")}{" "}
                {inputProfile.system_tokens_est}
              </Badge>
            )}
            {typeof generationProfile?.top_p_requested === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.topPRequested")}{" "}
                {generationProfile.top_p_requested.toFixed(2)}
              </Badge>
            )}
            {typeof generationProfile?.top_p_applied === "number" ? (
              <Badge tone="success">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.topPApplied")}{" "}
                {generationProfile.top_p_applied.toFixed(2)}
              </Badge>
            ) : (
              <Badge tone="warning">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.topPApplied")}{" "}
                {t("inspector.modelIntrospection.common.na")}
              </Badge>
            )}
            <Badge tone={topPStatusBadge.tone}>
              {t("inspector.modelIntrospection.dashboard.results.telemetry.topPStatus")}{" "}
              {t(topPStatusBadge.key)}
            </Badge>
            {inputProfile?.prompt_trimmed === true && (
              <Badge tone="warning">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.promptTrimmed")}
              </Badge>
            )}
            {typeof streamProfile?.time_to_first_byte_ms === "number" && (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.streamOpen")}{" "}
                {streamProfile.time_to_first_byte_ms.toFixed(1)}{" "}
                {t("inspector.modelIntrospection.common.ms")}
              </Badge>
            )}
            <Badge tone={streamOpenSourceBadge.tone}>
              {t("inspector.modelIntrospection.dashboard.results.telemetry.streamOpenSource")}{" "}
              {t(streamOpenSourceBadge.key)}
            </Badge>
            {streamProfile?.time_to_first_byte_estimated === true && (
              <Badge tone="warning">
                {t("inspector.modelIntrospection.dashboard.results.telemetry.streamOpenEstimated")}
              </Badge>
            )}
            {typeof streamProfile?.chunk_interval_p50_ms === "number" && (
              <Badge tone="neutral">
                p50 {streamProfile.chunk_interval_p50_ms.toFixed(1)}{" "}
                {t("inspector.modelIntrospection.common.ms")}
              </Badge>
            )}
            {typeof streamProfile?.chunk_interval_p95_ms === "number" && (
              <Badge tone="neutral">
                p95 {streamProfile.chunk_interval_p95_ms.toFixed(1)}{" "}
                {t("inspector.modelIntrospection.common.ms")}
              </Badge>
            )}
          </div>
          {analysisProcess && (
            <div className="mt-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-xs uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.results.request")}{" "}
                  {shortenTraceId(analysisProcess.request_id)}
                </p>
                {analysisProcess.steps.length > 0 && (
                  <Button
                    variant="ghost"
                    onClick={() => setAdvancedOpen((current) => !current)}
                  >
                    {advancedOpen ? advancedHideLabel : advancedShowLabel}
                  </Button>
                )}
              </div>
              {advancedOpen && analysisProcess.steps.length > 0 && (
                <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                    {advancedTitle}
                  </p>
                  <div className="mt-2 space-y-2">
                    {analysisProcess.steps.slice(0, 4).map((step, index) => (
                      <div
                        key={`${step.action ?? "step"}-${index}`}
                        className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-zinc-300"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-mono text-zinc-100">
                            {step.component ?? t("inspector.modelIntrospection.dashboard.results.stepFallback")}
                            .{step.action ?? t("inspector.modelIntrospection.dashboard.results.unknown")}
                          </span>
                          <span className="uppercase tracking-wide text-zinc-500">
                            {step.status ?? t("inspector.modelIntrospection.dashboard.results.ok")}
                          </span>
                        </div>
                        <p className="mt-1 text-zinc-400">
                          {step.details ?? t("inspector.modelIntrospection.dashboard.results.noDetails")}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.results.checklist.title")}
          </p>
          <div className="mt-3 space-y-2">
            {(operatorChecklist ?? []).map((item) => (
              <div
                key={item.id}
                className="rounded-xl border border-white/10 bg-black/20 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm text-zinc-100">{item.label}</p>
                  <Badge tone={item.status === "ok" ? "success" : "warning"}>
                    {item.status === "ok"
                      ? t("inspector.modelIntrospection.dashboard.results.checklist.ok")
                      : t("inspector.modelIntrospection.dashboard.results.checklist.warn")}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-zinc-400">{item.detail}</p>
              </div>
            ))}
            {(operatorChecklist ?? []).length === 0 && (
              <p className="text-sm text-zinc-400">
                {t("inspector.modelIntrospection.dashboard.results.checklist.unavailable")}
              </p>
            )}
          </div>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.results.runTrends.title")}
          </p>
          <AnalysisRunTrendsCard runTrends={runTrends} />
        </div>
      </div>
    </div>
  );
}

export function AnalysisLiveResponsePanel(props: AnalysisLiveResponsePanelProps) {
  const t = useTranslation();
  const {
    analysisStreaming,
    analysisResponse,
    answerStatusLabel,
    waitingTokenLabel,
    streamingLabel,
    statusBadgeLabel,
    statusBadgeTone,
    streamModeLabel,
    streamModeTone,
    fallbackLabel,
    fallbackTone,
  } = props;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={statusBadgeTone}>{statusBadgeLabel}</Badge>
        <Badge tone={streamModeTone}>{streamModeLabel}</Badge>
        <Badge tone={fallbackTone}>{fallbackLabel}</Badge>
        <Badge tone={analysisStreaming ? "warning" : "neutral"}>
          {analysisStreaming
            ? t("inspector.modelIntrospection.dashboard.results.typing")
            : answerStatusLabel}
        </Badge>
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-200">
        {analysisResponse || waitingTokenLabel}
        {analysisStreaming && (
          <span
            aria-hidden="true"
            className="ml-1 inline-block h-4 w-[2px] translate-y-[2px] animate-pulse bg-cyan-300"
          />
        )}
      </p>
      {analysisStreaming && (
        <p className="mt-2 text-xs uppercase tracking-wide text-cyan-200/80">
          {streamingLabel}
        </p>
      )}
    </div>
  );
}

type SnapshotComparisonPanelProps = Readonly<{
  comparison: SnapshotComparison | null;
  fallbackLabel: string;
  title: string;
  beforeLabel: string;
  afterLabel: string;
  deltaLabel: string;
}>;

function withSign(value: number): string {
  return value >= 0 ? `+${value}` : String(value);
}

export function SnapshotComparisonPanel(props: SnapshotComparisonPanelProps) {
  const { comparison, fallbackLabel, title, beforeLabel, afterLabel, deltaLabel } = props;
  if (!comparison) {
    return <p className="mt-2 text-sm text-zinc-300">{fallbackLabel}</p>;
  }

  return (
    <div className="mt-6 rounded-2xl border border-white/15 bg-black/25 p-4 shadow-[0_14px_32px_rgba(0,0,0,0.18)]">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
      <div className="mt-3 grid gap-4 xl:grid-cols-3 xl:gap-5">
        <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">{beforeLabel}</p>
          <p className="mt-2 font-mono text-sm text-white">{comparison.before.label}</p>
          <p className="mt-2 text-xs text-zinc-400">
            drift: {comparison.before.drift ? "yes" : "no"} · issues: {comparison.before.issues}
          </p>
          <p className="text-xs text-zinc-400">
            available: {formatCount(comparison.before.available_packages)} · missing: {formatCount(comparison.before.missing_packages)}
          </p>
        </div>
        <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">{afterLabel}</p>
          <p className="mt-2 font-mono text-sm text-white">{comparison.after.label}</p>
          <p className="mt-2 text-xs text-zinc-400">
            drift: {comparison.after.drift ? "yes" : "no"} · issues: {comparison.after.issues}
          </p>
          <p className="text-xs text-zinc-400">
            available: {formatCount(comparison.after.available_packages)} · missing: {formatCount(comparison.after.missing_packages)}
          </p>
        </div>
        <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">{deltaLabel}</p>
          <p className="mt-2 font-mono text-sm text-white">
            packages {withSign(comparison.delta.available_packages)}
          </p>
          <p className="text-xs text-zinc-400">
            missing {withSign(comparison.delta.missing_packages)} · issues {withSign(comparison.delta.issues)}
          </p>
        </div>
      </div>
    </div>
  );
}

type GraphPanelProps = Readonly<{
  snapshot: IntrospectionSnapshot;
  analysisActive: boolean;
  selectedGraphNodeId: string | null;
  onSelectGraphNode: (id: string) => void;
  selectedGraphNode: GraphNodeItem | null;
  selectedGraphNodeDetails: GraphNodeDetails | null;
  typeHintText: string;
  title: string;
  description: string;
}>;

type GraphNodeItem = NonNullable<IntrospectionSnapshot["graph"]>["nodes"][number];
type GraphEdgeItem = NonNullable<IntrospectionSnapshot["graph"]>["edges"][number];

type GraphOverviewBadgesProps = Readonly<{ snapshot: IntrospectionSnapshot }>;
type GraphNodesGridProps = Readonly<{
  nodes: GraphNodeItem[];
  selectedGraphNodeId: string | null;
  onSelectGraphNode: (id: string) => void;
}>;
type GraphRelationsCardProps = Readonly<{ edges: GraphEdgeItem[] }>;
type GraphSelectedNodeCardProps = Readonly<{
  selectedGraphNode: GraphNodeItem | null;
  selectedGraphNodeDetails: GraphNodeDetails | null;
  typeHintText: string;
}>;
type GraphContextSummaryProps = Readonly<{
  snapshot: IntrospectionSnapshot;
  analysisActive: boolean;
  nodeCount: number;
}>;

function getGraphNodes(snapshot: IntrospectionSnapshot): GraphNodeItem[] {
  return snapshot.graph?.nodes ?? [];
}

function getGraphEdges(snapshot: IntrospectionSnapshot): GraphEdgeItem[] {
  return snapshot.graph?.edges ?? [];
}

function getGraphSummary(
  snapshot: IntrospectionSnapshot,
): NonNullable<IntrospectionSnapshot["graph"]>["summary"] {
  return (
    snapshot.graph?.summary ?? {
      nodes: 0,
      edges: 0,
      available_packages: 0,
      missing_packages: 0,
      drift_issues: 0,
    }
  );
}

function GraphOverviewBadges(props: GraphOverviewBadgesProps) {
  const { snapshot } = props;
  const summary = getGraphSummary(snapshot);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge tone="neutral">nodes {formatCount(summary.nodes)}</Badge>
      <Badge tone="neutral">edges {formatCount(summary.edges)}</Badge>
      <Badge tone="success">available {formatCount(summary.available_packages)}</Badge>
      <Badge tone="warning">missing {formatCount(summary.missing_packages)}</Badge>
      <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
        drift issues {formatCount(summary.drift_issues)}
      </Badge>
    </div>
  );
}

function GraphNodesGrid(props: GraphNodesGridProps) {
  const { nodes, selectedGraphNodeId, onSelectGraphNode } = props;
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {nodes.map((node) => (
        <GraphNodeCard
          key={node.id}
          label={node.label}
          kind={node.kind}
          status={node.status}
          selected={selectedGraphNodeId === node.id}
          onClick={() => onSelectGraphNode(node.id)}
        />
      ))}
    </div>
  );
}

function GraphRelationsCard(props: GraphRelationsCardProps) {
  const { edges } = props;
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">Relations</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {edges.map((edge, index) => (
          <Badge
            key={`${edge.from}-${edge.to}-${edge.label}-${index}`}
            tone="neutral"
          >
            {edge.from} → {edge.to} ({edge.label})
          </Badge>
        ))}
      </div>
      <div className="mt-4 rounded-xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-300">
        Click any node to open the drilldown panel on the right. Package and reuse nodes are
        treated the same way as runtime nodes so the graph stays uniform.
      </div>
    </div>
  );
}

function GraphSelectedNodeCard(props: GraphSelectedNodeCardProps) {
  const { selectedGraphNode, selectedGraphNodeDetails, typeHintText } = props;
  return (
    <div className="rounded-2xl border border-violet-400/20 bg-white/5 p-4 xl:sticky xl:top-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Graph drilldown</p>
        <Badge tone={selectedGraphNode ? "success" : "neutral"}>
          {selectedGraphNode ? "node selected" : "awaiting selection"}
        </Badge>
      </div>
      {selectedGraphNode ? (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{selectedGraphNode.kind}</Badge>
            <Badge tone="neutral">{selectedGraphNode.status}</Badge>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Label</p>
            <p className="mt-1 font-mono text-sm text-white">{selectedGraphNode.label}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {selectedGraphNodeDetails?.title ?? "Details"}
            </p>
            <div className="mt-2 space-y-1 text-sm text-zinc-300">
              {selectedGraphNodeDetails?.lines.map((line) => (
                <p key={line}>{line}</p>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Type hint</p>
            <p className="mt-1 text-sm text-zinc-300">{typeHintText}</p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-300">
          Select a runtime, package or reuse node to inspect its details here.
        </p>
      )}
    </div>
  );
}

function GraphContextSummary(props: GraphContextSummaryProps) {
  const { snapshot, analysisActive, nodeCount } = props;
  const summary = getGraphSummary(snapshot);
  const totalPackages =
    snapshot.available_packages.length + snapshot.missing_packages.length;
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-zinc-300">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">runtime {snapshot.summary.runtime_label}</Badge>
        <Badge tone={analysisActive ? "success" : "neutral"}>
          analysis {analysisActive ? "live" : "idle"}
        </Badge>
        <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
          drift {snapshot.runtime_drift.drift_detected ? "present" : "clean"}
        </Badge>
        <Badge tone={snapshot.missing_packages.length === 0 ? "success" : "warning"}>
          packages {formatCount(snapshot.available_packages.length)}/{formatCount(totalPackages)}
        </Badge>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Runtime</p>
          <p className="mt-1 font-mono text-sm text-white">{snapshot.runtime.provider}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Model</p>
          <p className="mt-1 font-mono text-sm text-white">{snapshot.runtime.model}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Analysis nodes</p>
          <p className="mt-1 font-mono text-sm text-white">{formatCount(nodeCount)}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Relations</p>
          <p className="mt-1 font-mono text-sm text-white">
            {formatCount(summary.edges)} edges
          </p>
        </div>
      </div>
      <p className="mt-3 text-sm text-zinc-300">
        Graph data is derived from the same snapshot as the runtime view, so the graph stays
        lightweight while still reflecting active model, diagnostics reuse, package coverage and
        drift state.
      </p>
    </div>
  );
}

export function GraphPanel(props: GraphPanelProps) {
  const {
    snapshot,
    analysisActive,
    selectedGraphNodeId,
    onSelectGraphNode,
    selectedGraphNode,
    selectedGraphNodeDetails,
    typeHintText,
    title,
    description,
  } = props;
  const nodes = getGraphNodes(snapshot);
  const edges = getGraphEdges(snapshot);
  const analysisNodeCount = nodes.filter((node) => node.kind === "analysis").length;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
      <div className="space-y-1">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{"// graph"}</p>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="text-sm text-zinc-300">{description}</p>
      </div>
      <div className="mt-4 space-y-4">
        <GraphOverviewBadges snapshot={snapshot} />
        <GraphNodesGrid
          nodes={nodes}
          selectedGraphNodeId={selectedGraphNodeId}
          onSelectGraphNode={onSelectGraphNode}
        />
        <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <GraphRelationsCard edges={edges} />
          <GraphSelectedNodeCard
            selectedGraphNode={selectedGraphNode}
            selectedGraphNodeDetails={selectedGraphNodeDetails}
            typeHintText={typeHintText}
          />
        </div>
        <GraphContextSummary
          snapshot={snapshot}
          analysisActive={analysisActive}
          nodeCount={analysisNodeCount}
        />
      </div>
    </div>
  );
}

type ArchitectureGraphPanelProps = Readonly<{
  snapshot: IntrospectionSnapshot;
  readiness: ModelArchitectureGraphReadiness;
  layerInternalsPayload: AnalysisLayerInternalsPayload | null;
  title: string;
  description: string;
  typeHintText: string;
}>;

type ArchitectureGraphNode = ModelArchitectureGraphNode;
type ArchitectureGraphEdge = ModelArchitectureGraphEdge;
type TransitionSignificance = "key" | "supporting" | "repeat";

type ArchitectureGraphTransition = Readonly<{
  id: string;
  sourceLabel: string;
  targetLabel: string;
  sourceRole: string;
  targetRole: string;
  label: string;
  effect: string;
  before: string;
  after: string;
  delta: string;
  impact: string;
  significance: TransitionSignificance;
}>;

type ArchitectureGraphOutcome = Readonly<{
  result: string;
  summary: string;
  primaryPath: string;
  evidence: string[];
  supportingSignals: string[];
}>;

type ArchitectureGraphCheckpoint = Readonly<{
  id: string;
  title: string;
  stage: string;
  before: string;
  after: string;
  change: string;
  result: string;
  evidence: string[];
}>;

type AnalysisActivationLayer =
  | AnalysisMlpActivationPayload["mlp_layer"]
  | AnalysisMlpActivationPayload["residual_layer"];

function mapActivationLayer(layer: AnalysisActivationLayer) {
  if (!layer) {
    return null;
  }
  return {
    layer: layer.layer,
    label: layer.label,
    roleHint: layer.role_hint ?? null,
    hiddenSlice: layer.hidden_slice ?? [],
    metrics: {
      mean: layer.metrics.mean,
      norm: layer.metrics.norm,
      maxAbs: layer.metrics.max_abs,
      topDimensions: (layer.metrics.top_dimensions ?? []).map((dimension) => ({
        index: dimension.index,
        value: dimension.value,
        absValue: dimension.abs_value,
      })),
    },
    summary: layer.summary,
    evidence: layer.evidence ?? [],
  };
}

type ArchitectureLayerInternals = Readonly<{
  id: string;
  label: string;
  layer: number;
  status: string;
  summary: string;
  stateDelta: string;
  blocks: Array<{
    kind: string;
    label: string;
    summary: string;
    detail: string;
    impact: string;
    evidence: string[];
    heads?: Array<{
      head: number;
      summary: string;
      detail: string;
      evidence: string[];
    }>;
  }>;
  signals: Array<{
    source: string;
    label: string;
    detail: string;
    evidence: string[];
  }>;
  responseLinkage: {
    status: string;
    layerId: number;
    layerLabel: string;
    coveragePercent: number;
    fragmentCount: number;
    linkedFragmentCount: number;
    linkedFragments: string[];
    evidenceLinks: string[];
    dominantSignals: string[];
    summary: string;
    impact: string;
    evidence: string[];
  } | null;
  mlpActivation: ArchitectureMlpActivation | null;
  evidence: string[];
}>;

type ArchitectureActivationPath = Readonly<{
  source: string;
  status: string;
  selectedLayers: number[];
  layers: Array<{
    layer: number;
    label: string;
    roleHint: string | null;
    hiddenSlice: number[];
    metrics: {
      mean: number;
      norm: number;
      maxAbs: number;
      topDimensions: Array<{
        index: number;
        value: number;
        absValue: number;
      }>;
    };
    summary: string;
    evidence: string[];
  }>;
  transitions: Array<{
    fromLayer: number;
    toLayer: number;
    before: string;
    after: string;
    deltaNorm: number;
    meanShift: number;
    maxAbsShift: number;
    summary: string;
    impact: string;
    evidence: string[];
  }>;
  summary: {
    selectedLayerCount: number;
    transitionCount: number;
    focusLayer: number | null;
    maxDeltaNorm: number;
    averageNorm: number;
  };
  notes: string[];
}>;

type ArchitectureMlpActivation = Readonly<{
  source: string;
  status: string;
  selectedLayers: number[];
  mlpLayer: {
    layer: number;
    label: string;
    roleHint: string | null;
    hiddenSlice: number[];
    metrics: {
      mean: number;
      norm: number;
      maxAbs: number;
      topDimensions: Array<{
        index: number;
        value: number;
        absValue: number;
      }>;
    };
    summary: string;
    evidence: string[];
  } | null;
  residualLayer: {
    layer: number;
    label: string;
    roleHint: string | null;
    hiddenSlice: number[];
    metrics: {
      mean: number;
      norm: number;
      maxAbs: number;
      topDimensions: Array<{
        index: number;
        value: number;
        absValue: number;
      }>;
    };
    summary: string;
    evidence: string[];
  } | null;
  transition: {
    fromLayer: number;
    toLayer: number;
    before: string;
    after: string;
    deltaNorm: number;
    meanShift: number;
    maxAbsShift: number;
    summary: string;
    impact: string;
    evidence: string[];
  } | null;
  tensorActivation?: {
    source: string;
    status: string;
    sliceKind: string;
    focusLayer: number | null;
    residualLayer: number | null;
    vectorLength: number;
    mlpVector: number[];
    residualVector: number[] | null;
    deltaVector: number[] | null;
    norms: {
      mlpL2: number;
      residualL2: number | null;
      deltaL2: number | null;
      cosineSimilarity: number | null;
    };
    topDeltaDimensions: Array<{
      index: number;
      value: number;
      absValue: number;
    }>;
    comparisons: Array<{
      requestId: string | null;
      tsMs: number | null;
      mlpL2: number | null;
      cosineSimilarity: number | null;
      mlpL2Diff: number | null;
      cosineSimilarityDiff: number | null;
    }>;
    stability: {
      stable: boolean;
      statusLabel: string;
      mlpL2Variance: number;
      cosineSimilarityMean: number | null;
    } | null;
    evidence: string[];
    notes: string[];
  } | null;
  summary: {
    selectedLayerCount: number;
    focusLayer: number | null;
    residualLayer: number | null;
    hiddenDimensionCount: number;
    maxDeltaNorm: number;
    averageNorm: number;
    transitionSummary: string | null;
    transitionImpact: string | null;
  };
  notes: string[];
}>;

const ARCHITECTURE_NODE_COLORS: Record<string, string> = {
  input: "#06b6d4",
  embedding: "#8b5cf6",
  layer: "#6366f1",
  attention: "#f59e0b",
  mlp: "#10b981",
  residual: "#f97316",
  output: "#22c55e",
  diagnostic: "#ec4899",
  unknown: "#64748b",
};

const ARCHITECTURE_GRAPH_PADDING_PX = 72;

function getArchitectureGraph(snapshot: IntrospectionSnapshot): ModelArchitectureGraph | null {
  return snapshot.architecture_graph ?? null;
}

function getArchitectureGraphNodes(snapshot: IntrospectionSnapshot): ArchitectureGraphNode[] {
  return getArchitectureGraph(snapshot)?.nodes ?? [];
}

function getArchitectureGraphEdges(snapshot: IntrospectionSnapshot): ArchitectureGraphEdge[] {
  return getArchitectureGraph(snapshot)?.edges ?? [];
}

function getArchitectureGraphSummary(snapshot: IntrospectionSnapshot) {
  return (
    getArchitectureGraph(snapshot)?.summary ?? {
      nodes: 0,
      edges: 0,
      layer_count: 0,
      block_count: 0,
    }
  );
}

function getArchitectureGraphOverview(snapshot: IntrospectionSnapshot) {
  const graph = getArchitectureGraph(snapshot);
  const nodes = graph?.nodes ?? [];
  const sortedNodes = [...nodes].sort((left, right) => {
    const leftLayer = left.layer_index ?? Number.MAX_SAFE_INTEGER;
    const rightLayer = right.layer_index ?? Number.MAX_SAFE_INTEGER;
    if (leftLayer !== rightLayer) {
      return leftLayer - rightLayer;
    }
    return left.label.localeCompare(right.label);
  });
  const entryNode = nodes.find((node) => node.role === "input") ?? sortedNodes[0] ?? null;
  const exitNode = nodes.find((node) => node.role === "output") ?? sortedNodes.at(-1) ?? null;

  return {
    entryLabel: entryNode?.label ?? "n/a",
    exitLabel: exitNode?.label ?? "n/a",
    flowLabel:
      entryNode && exitNode ? `${entryNode.label} → ${exitNode.label}` : "n/a",
  };
}

function getTransitionEffect(
  sourceNode: ArchitectureGraphNode | null,
  targetNode: ArchitectureGraphNode | null,
  edge: ArchitectureGraphEdge,
): string {
  const sourceLabel = sourceNode?.label ?? edge.from;
  const targetLabel = targetNode?.label ?? edge.to;
  const sourceRole = sourceNode?.role ?? "unknown";
  const targetRole = targetNode?.role ?? "unknown";
  const edgeLabel = edge.label.toLowerCase();
  if (sourceRole === "input" && targetRole === "embedding") {
    return "Initial tokens enter embedding space.";
  }
  if (sourceRole === "embedding" && targetRole === "layer") {
    return "The sequence enters the transformer stack.";
  }
  if (targetRole === "output") {
    return "The accumulated state is decoded into the final output.";
  }
  if (edgeLabel.includes("probe")) {
    return "An internal probe signal is exposed for inspection.";
  }
  if (edgeLabel.includes("merge") || edgeLabel.includes("residual")) {
    return "Residual information is merged back into the active path.";
  }
  if (edgeLabel.includes("attention")) {
    return "The state is transformed by an attention operation.";
  }
  if (sourceRole === "layer" && targetRole === "layer") {
    return "The state is propagated into the next block.";
  }
  return `${sourceLabel} continues into ${targetLabel}.`;
}

function getTransitionImpact(significance: TransitionSignificance): string {
  if (significance === "key") {
    return "High-impact transition that changes the active state.";
  }
  if (significance === "repeat") {
    return "Repeated transition; useful for structure, not for major state change.";
  }
  return "Supporting transition that keeps the chain moving.";
}

function getReadinessTone(status: "available" | "partial" | "missing"): BadgeTone {
  if (status === "available") {
    return "success";
  }
  if (status === "partial") {
    return "warning";
  }
  return "neutral";
}

function getTransitionSignificanceTone(
  significance: TransitionSignificance,
): BadgeTone {
  if (significance === "key") {
    return "success";
  }
  if (significance === "repeat") {
    return "warning";
  }
  return "neutral";
}

function getTransitionDelta(
  sourceNode: ArchitectureGraphNode | null,
  targetNode: ArchitectureGraphNode | null,
  edge: ArchitectureGraphEdge,
  effect: string,
  significance: TransitionSignificance,
) {
  const sourceLabel = sourceNode?.label ?? edge.from;
  const targetLabel = targetNode?.label ?? edge.to;
  const sourceRole = sourceNode?.role ?? "unknown";
  const targetRole = targetNode?.role ?? "unknown";
  const before = `${sourceRole}: ${sourceLabel}`;
  const after = `${targetRole}: ${targetLabel}`;
  const label = edge.label.toLowerCase();

  let delta = effect;
  if (sourceRole === "input" && targetRole === "embedding") {
    delta = "Tokens are converted into embedding vectors.";
  } else if (sourceRole === "embedding" && targetRole === "layer") {
    delta = "The representation enters the transformer stack.";
  } else if (sourceRole === "layer" && targetRole === "layer") {
    delta = "The active representation is refined in the next block.";
  } else if (targetRole === "output") {
    delta = "Intermediate state is compressed into final output.";
  } else if (label.includes("probe")) {
    delta = "A probe-specific visibility path is added without changing the main decode flow.";
  } else if (label.includes("merge") || label.includes("residual")) {
    delta = "Residual state is reintroduced into the active path.";
  } else if (label.includes("attention")) {
    delta = "Attention reshapes the active representation before it moves on.";
  }

  const impact = getTransitionImpact(significance);

  return { before, after, delta, impact };
}

function getTransitionSignificance(
  sourceNode: ArchitectureGraphNode | null,
  targetNode: ArchitectureGraphNode | null,
  edge: ArchitectureGraphEdge,
): TransitionSignificance {
  const edgeLabel = edge.label.toLowerCase();
  if (
    sourceNode?.role === "input" ||
    targetNode?.role === "output" ||
    edgeLabel.includes("probe") ||
    edgeLabel.includes("merge") ||
    edgeLabel.includes("decode")
  ) {
    return "key";
  }
  if (edgeLabel.includes("tokenize") || edgeLabel.includes("enter stack")) {
    return "key";
  }
  if (sourceNode?.role === "layer" && targetNode?.role === "layer") {
    return "supporting";
  }
  return "supporting";
}

function getArchitectureGraphTransitions(
  snapshot: IntrospectionSnapshot,
): ArchitectureGraphTransition[] {
  const edges = getArchitectureGraphEdges(snapshot);
  const nodesById = new Map(
    getArchitectureGraphNodes(snapshot).map((node) => [node.id, node] as const),
  );
  const transitions = edges.map((edge, index) => {
    const sourceNode = nodesById.get(edge.from) ?? null;
    const targetNode = nodesById.get(edge.to) ?? null;
    const significance = getTransitionSignificance(sourceNode, targetNode, edge);
    const effect = getTransitionEffect(sourceNode, targetNode, edge);
    const transitionDelta = getTransitionDelta(sourceNode, targetNode, edge, effect, significance);
    return {
      id: `${edge.from}->${edge.to}:${index}`,
      sourceLabel: sourceNode?.label ?? edge.from,
      targetLabel: targetNode?.label ?? edge.to,
      sourceRole: sourceNode?.role ?? "unknown",
      targetRole: targetNode?.role ?? "unknown",
      label: edge.label,
      effect,
      before: transitionDelta.before,
      after: transitionDelta.after,
      delta: transitionDelta.delta,
      impact: transitionDelta.impact,
      significance,
    };
  });

  const scoredTransitions = transitions
    .map((transition, index) => ({
      transition,
      score:
        (transition.significance === "key" ? 3 : 1) +
        (transition.sourceRole === "input" ? 3 : 0) +
        (transition.targetRole === "output" ? 3 : 0) +
        (transition.label.toLowerCase().includes("probe") ? 2 : 0) +
        (transition.label.toLowerCase().includes("merge") ? 2 : 0) +
        (transition.label.toLowerCase().includes("decode") ? 2 : 0) +
        Math.max(0, 2 - index * 0.1),
    }))
    .sort((left, right) => right.score - left.score);

  const selected = scoredTransitions.slice(0, Math.min(4, scoredTransitions.length)).map((entry) => entry.transition);
  if (selected.length > 0) {
    return selected;
  }
  return transitions.slice(0, Math.min(3, transitions.length));
}

function getArchitectureGraphCheckpointEvidence(
  transitions: ArchitectureGraphTransition[],
  predicate: (transition: ArchitectureGraphTransition) => boolean,
  fallback: string[],
): string[] {
  const evidence = transitions
    .filter(predicate)
    .slice(0, 3)
    .map((transition) => `${transition.sourceLabel} → ${transition.targetLabel} (${transition.label})`);
  return evidence.length > 0 ? evidence : fallback;
}

function getArchitectureGraphProgressCheckpoints(
  snapshot: IntrospectionSnapshot,
  transitions: ArchitectureGraphTransition[],
  summary: ReturnType<typeof getArchitectureGraphSummary>,
  overview: ReturnType<typeof getArchitectureGraphOverview>,
): ArchitectureGraphCheckpoint[] {
  const graph = getArchitectureGraph(snapshot);
  const nodes = graph?.nodes ?? [];
  const inputNode = nodes.find((node) => node.role === "input") ?? null;
  const embeddingNode = nodes.find((node) => node.role === "embedding") ?? null;
  const layerNodes = nodes
    .filter((node) => node.role === "layer")
    .sort((left, right) => (left.layer_index ?? Number.MAX_SAFE_INTEGER) - (right.layer_index ?? Number.MAX_SAFE_INTEGER));
  const firstLayerNode = layerNodes[0] ?? null;
  const lastLayerNode = layerNodes.at(-1) ?? null;
  const probeNode = nodes.find((node) => String(node.label).toLowerCase().includes("probe")) ?? null;
  const residualNode = nodes.find((node) => node.role === "residual") ?? null;
  const outputNode = nodes.find((node) => node.role === "output") ?? null;

  const entryTransition =
    transitions.find(
      (transition) =>
        transition.sourceRole === "input" && transition.targetRole === "embedding",
    ) ?? transitions[0] ?? null;
  const stackTransitions = transitions.filter(
    (transition) => transition.sourceRole === "layer" && transition.targetRole === "layer",
  );
  const probeTransition = transitions.find(
    (transition) =>
      transition.label.toLowerCase().includes("probe") ||
      transition.sourceRole === "attention" ||
      transition.targetRole === "diagnostic",
  );
  const exitTransition =
    transitions.find(
      (transition) =>
        transition.targetRole === "output" || transition.label.toLowerCase().includes("decode"),
    ) ?? transitions.at(-1) ?? null;
  const mergeTransition =
    transitions.find(
      (transition) =>
        transition.label.toLowerCase().includes("merge") ||
        transition.label.toLowerCase().includes("residual"),
    ) ?? null;

  return [
    {
      id: "entry",
      title: "Entry state",
      stage: "input → embedding",
      before: inputNode?.label ?? overview.entryLabel,
      after: embeddingNode?.label ?? "embedding",
      change:
        entryTransition?.effect ??
        "The prompt is tokenized and projected into the embedding space.",
      result: "A structured token representation is established for the stack.",
      evidence: getArchitectureGraphCheckpointEvidence(
        transitions,
        (transition) => transition.sourceRole === "input" && transition.targetRole === "embedding",
        [`Entry path: ${overview.flowLabel}`],
      ),
    },
    {
      id: "stack",
      title: "Stack progression",
      stage: "embedding → layers",
      before: embeddingNode?.label ?? "embedding",
      after: firstLayerNode?.label ?? lastLayerNode?.label ?? `layer_${summary.layer_count}`,
      change: `The representation is refined across ${formatCount(summary.layer_count)} layers and ${formatCount(summary.block_count)} blocks.`,
      result: "Context is accumulated and transformed through the transformer stack.",
      evidence: getArchitectureGraphCheckpointEvidence(
        transitions,
        (transition) => transition.sourceRole === "layer" && transition.targetRole === "layer",
        [
          ...stackTransitions.slice(0, 2).map(
            (transition) => `${transition.sourceLabel} → ${transition.targetLabel} (${transition.label})`,
          ),
          `Stack depth: ${formatCount(summary.layer_count)} layers`,
          `Block count: ${formatCount(summary.block_count)} blocks`,
        ],
      ),
    },
    {
      id: "inspection",
      title: "Inspection state",
      stage: "probe and residual",
      before: lastLayerNode?.label ?? `layer_${summary.layer_count}`,
      after: probeNode?.label ?? residualNode?.label ?? "probe surface",
      change:
        probeTransition?.effect ??
        mergeTransition?.effect ??
        "Internal signals become visible through the probe and residual paths.",
      result: "The internal state remains inspectable without replacing the main path.",
      evidence: getArchitectureGraphCheckpointEvidence(
        transitions,
        (transition) =>
          transition.label.toLowerCase().includes("probe") ||
          transition.label.toLowerCase().includes("merge") ||
          transition.label.toLowerCase().includes("residual"),
        [
          probeNode ? `Probe node: ${probeNode.label}` : "Probe path not exposed",
          residualNode ? `Residual node: ${residualNode.label}` : "Residual path not exposed",
        ],
      ),
    },
    {
      id: "exit",
      title: "Exit state",
      stage: "residual → output",
      before: residualNode?.label ?? "residual merge",
      after: outputNode?.label ?? overview.exitLabel,
      change:
        exitTransition?.effect ??
        "The accumulated state is decoded into the final output.",
      result: "The architecture resolves into the final answer text.",
      evidence: getArchitectureGraphCheckpointEvidence(
        transitions,
        (transition) => transition.targetRole === "output" || transition.label.toLowerCase().includes("decode"),
        [`Exit path: ${overview.flowLabel}`],
      ),
    },
  ];
}

function getAnalysisLayerInternals(
  payload: AnalysisLayerInternalsPayload | null | undefined,
): ArchitectureLayerInternals[] {
  const layers = payload?.layers ?? [];
  const mlpActivationPayload = payload?.mlp_activation ?? null;
  const mlpActivationFocusLayer = mlpActivationPayload?.summary.focus_layer ?? null;
  const mapActivationLayer = (
    layer:
      | AnalysisMlpActivationPayload["mlp_layer"]
      | AnalysisMlpActivationPayload["residual_layer"],
  ) =>
    layer
      ? {
          layer: layer.layer,
          label: layer.label,
          roleHint: layer.role_hint ?? null,
          hiddenSlice: layer.hidden_slice ?? [],
          metrics: {
            mean: layer.metrics.mean,
            norm: layer.metrics.norm,
            maxAbs: layer.metrics.max_abs,
            topDimensions: (layer.metrics.top_dimensions ?? []).map((dimension) => ({
              index: dimension.index,
              value: dimension.value,
              absValue: dimension.abs_value,
            })),
          },
          summary: layer.summary,
          evidence: layer.evidence ?? [],
          }
      : null;
  return layers.map((layer) => ({
    id: layer.id,
    label: layer.label,
    layer: layer.layer,
    status: layer.status,
    summary: layer.summary,
    stateDelta: layer.state_delta,
    blocks: layer.blocks,
    signals: layer.signals,
    responseLinkage: layer.response_linkage
      ? {
          status: layer.response_linkage.status,
          layerId: layer.response_linkage.layer_id,
          layerLabel: layer.response_linkage.layer_label,
          coveragePercent: layer.response_linkage.coverage_percent,
          fragmentCount: layer.response_linkage.fragment_count,
          linkedFragmentCount: layer.response_linkage.linked_fragment_count,
          linkedFragments: layer.response_linkage.linked_fragments ?? [],
          evidenceLinks: layer.response_linkage.evidence_links ?? [],
          dominantSignals: layer.response_linkage.dominant_signals ?? [],
          summary: layer.response_linkage.summary,
          impact: layer.response_linkage.impact,
          evidence: layer.response_linkage.evidence ?? [],
        }
      : null,
    mlpActivation:
      mlpActivationPayload && layer.layer === mlpActivationFocusLayer
      ? {
          source: mlpActivationPayload.source,
          status: mlpActivationPayload.status,
          selectedLayers: mlpActivationPayload.selected_layers ?? [],
          mlpLayer: mapActivationLayer(mlpActivationPayload.mlp_layer),
          residualLayer: mapActivationLayer(mlpActivationPayload.residual_layer),
          transition: mlpActivationPayload.transition
            ? {
                fromLayer: mlpActivationPayload.transition.from_layer,
                toLayer: mlpActivationPayload.transition.to_layer,
                before: mlpActivationPayload.transition.before,
                after: mlpActivationPayload.transition.after,
                deltaNorm: mlpActivationPayload.transition.delta_norm,
                meanShift: mlpActivationPayload.transition.mean_shift,
                maxAbsShift: mlpActivationPayload.transition.max_abs_shift,
                summary: mlpActivationPayload.transition.summary,
                impact: mlpActivationPayload.transition.impact,
                evidence: mlpActivationPayload.transition.evidence ?? [],
              }
            : null,
          summary: {
            selectedLayerCount: mlpActivationPayload.summary.selected_layer_count,
            focusLayer: mlpActivationPayload.summary.focus_layer ?? null,
            residualLayer: mlpActivationPayload.summary.residual_layer ?? null,
            hiddenDimensionCount: mlpActivationPayload.summary.hidden_dimension_count,
            maxDeltaNorm: mlpActivationPayload.summary.max_delta_norm,
            averageNorm: mlpActivationPayload.summary.average_norm,
            transitionSummary: mlpActivationPayload.summary.transition_summary ?? null,
            transitionImpact: mlpActivationPayload.summary.transition_impact ?? null,
          },
          notes: mlpActivationPayload.notes ?? [],
        }
      : null,
    evidence: layer.evidence,
  }));
}

function getAnalysisActivationPath(
  payload: AnalysisLayerInternalsPayload | null | undefined,
): ArchitectureActivationPath | null {
  const activationPath = payload?.activation_path;
  if (!activationPath) {
    return null;
  }
  return {
    source: activationPath.source,
    status: activationPath.status,
    selectedLayers: activationPath.selected_layers ?? [],
    layers: (activationPath.layers ?? []).map((layer) => ({
      layer: layer.layer,
      label: layer.label,
      roleHint: layer.role_hint ?? null,
      hiddenSlice: layer.hidden_slice ?? [],
      metrics: {
        mean: layer.metrics.mean,
        norm: layer.metrics.norm,
        maxAbs: layer.metrics.max_abs,
        topDimensions: (layer.metrics.top_dimensions ?? []).map((dimension) => ({
          index: dimension.index,
          value: dimension.value,
          absValue: dimension.abs_value,
        })),
      },
      summary: layer.summary,
      evidence: layer.evidence ?? [],
    })),
    transitions: (activationPath.transitions ?? []).map((transition) => ({
      fromLayer: transition.from_layer,
      toLayer: transition.to_layer,
      before: transition.before,
      after: transition.after,
      deltaNorm: transition.delta_norm,
      meanShift: transition.mean_shift,
      maxAbsShift: transition.max_abs_shift,
      summary: transition.summary,
      impact: transition.impact,
      evidence: transition.evidence ?? [],
    })),
    summary: {
      selectedLayerCount: activationPath.summary.selected_layer_count,
      transitionCount: activationPath.summary.transition_count,
      focusLayer: activationPath.summary.focus_layer ?? null,
      maxDeltaNorm: activationPath.summary.max_delta_norm,
      averageNorm: activationPath.summary.average_norm,
    },
    notes: activationPath.notes ?? [],
  };
}

function getAnalysisMlpActivation(
  payload: AnalysisLayerInternalsPayload | null | undefined,
): ArchitectureMlpActivation | null {
  const mlpActivation = payload?.mlp_activation;
  if (!mlpActivation) {
    return null;
  }

  return {
    source: mlpActivation.source,
    status: mlpActivation.status,
    selectedLayers: mlpActivation.selected_layers ?? [],
    mlpLayer: mapActivationLayer(mlpActivation.mlp_layer),
    residualLayer: mapActivationLayer(mlpActivation.residual_layer),
    transition: mlpActivation.transition
      ? {
          fromLayer: mlpActivation.transition.from_layer,
          toLayer: mlpActivation.transition.to_layer,
          before: mlpActivation.transition.before,
          after: mlpActivation.transition.after,
          deltaNorm: mlpActivation.transition.delta_norm,
          meanShift: mlpActivation.transition.mean_shift,
          maxAbsShift: mlpActivation.transition.max_abs_shift,
          summary: mlpActivation.transition.summary,
          impact: mlpActivation.transition.impact,
          evidence: mlpActivation.transition.evidence ?? [],
        }
      : null,
    tensorActivation: mlpActivation.tensor_activation
      ? {
          source: mlpActivation.tensor_activation.source,
          status: mlpActivation.tensor_activation.status,
          sliceKind: mlpActivation.tensor_activation.slice_kind,
          focusLayer: mlpActivation.tensor_activation.focus_layer,
          residualLayer: mlpActivation.tensor_activation.residual_layer,
          vectorLength: mlpActivation.tensor_activation.vector_length,
          mlpVector: mlpActivation.tensor_activation.mlp_vector ?? [],
          residualVector: mlpActivation.tensor_activation.residual_vector ?? null,
          deltaVector: mlpActivation.tensor_activation.delta_vector ?? null,
          norms: {
            mlpL2: mlpActivation.tensor_activation.norms.mlp_l2,
            residualL2: mlpActivation.tensor_activation.norms.residual_l2,
            deltaL2: mlpActivation.tensor_activation.norms.delta_l2,
            cosineSimilarity: mlpActivation.tensor_activation.norms.cosine_similarity,
          },
          topDeltaDimensions: (mlpActivation.tensor_activation.top_delta_dimensions ?? []).map(
            (dimension) => ({
              index: dimension.index,
              value: dimension.value,
              absValue: dimension.abs_value,
            }),
          ),
          comparisons: (mlpActivation.tensor_activation.comparisons ?? []).map((comp) => ({
            requestId: comp.request_id,
            tsMs: comp.ts_ms,
            mlpL2: comp.mlp_l2,
            cosineSimilarity: comp.cosine_similarity,
            mlpL2Diff: comp.mlp_l2_diff,
            cosineSimilarityDiff: comp.cosine_similarity_diff,
          })),
          stability: mlpActivation.tensor_activation.stability
            ? {
                stable: mlpActivation.tensor_activation.stability.stable,
                statusLabel: mlpActivation.tensor_activation.stability.status_label,
                mlpL2Variance: mlpActivation.tensor_activation.stability.mlp_l2_variance,
                cosineSimilarityMean: mlpActivation.tensor_activation.stability.cosine_similarity_mean,
              }
            : null,
          evidence: mlpActivation.tensor_activation.evidence ?? [],
          notes: mlpActivation.tensor_activation.notes ?? [],
        }
      : null,
    summary: {
      selectedLayerCount: mlpActivation.summary.selected_layer_count,
      focusLayer: mlpActivation.summary.focus_layer ?? null,
      residualLayer: mlpActivation.summary.residual_layer ?? null,
      hiddenDimensionCount: mlpActivation.summary.hidden_dimension_count,
      maxDeltaNorm: mlpActivation.summary.max_delta_norm,
      averageNorm: mlpActivation.summary.average_norm,
      transitionSummary: mlpActivation.summary.transition_summary ?? null,
      transitionImpact: mlpActivation.summary.transition_impact ?? null,
    },
    notes: mlpActivation.notes ?? [],
  };
}

function getArchitectureLayerDominantSignals(
  layer: ArchitectureLayerInternals | null,
): Array<
  ArchitectureLayerInternals["signals"][number] & {
    dominant: boolean;
  }
> {
  if (!layer) {
    return [];
  }
  return layer.signals.slice(0, 3).map((signal, index) => ({
    ...signal,
    dominant: index === 0,
  }));
}

function getArchitectureGraphOutcome(
  readiness: ModelArchitectureGraphReadiness,
  overview: ReturnType<typeof getArchitectureGraphOverview>,
  summary: ReturnType<typeof getArchitectureGraphSummary>,
  transitions: ArchitectureGraphTransition[],
): ArchitectureGraphOutcome {
  const keyTransitions = transitions.filter((transition) => transition.significance === "key");
  const path = overview.flowLabel;
  let result = "Architecture graph payload is missing.";
  if (readiness.status === "available") {
    result = "Native architecture graph resolved.";
  } else if (readiness.status === "partial") {
    result = "Architecture graph is partially resolved.";
  }
  const summaryLine = `The graph captures ${formatCount(summary.layer_count)} layers, ${formatCount(summary.block_count)} blocks, ${formatCount(summary.nodes)} nodes and ${formatCount(summary.edges)} edges.`;
  const evidence = [
    `Source: ${readiness.source}`,
    `Fidelity: ${readiness.fidelity}`,
    `Generated: ${readiness.generatedAt ?? "n/a"}`,
    `Entry to exit: ${path}`,
  ];
  const supportingSignals = [
    readiness.fidelity === "native" ? "native payload" : `fidelity ${readiness.fidelity}`,
    `${formatCount(keyTransitions.length)} key transition(s)`,
    ...keyTransitions.slice(0, 3).map((transition) => `${transition.sourceLabel} → ${transition.targetLabel}`),
    `source: ${readiness.source}`,
  ];
  return {
    result,
    summary: summaryLine,
    primaryPath: path,
    evidence,
    supportingSignals,
  };
}

function getArchitectureGraphNodeDetails(
  snapshot: IntrospectionSnapshot,
  selectedNode: ArchitectureGraphNode | null,
): GraphNodeDetails {
  if (!selectedNode) {
    return {
      title: "Architecture details",
      lines: ["No architecture node selected."],
    };
  }
  const graph = getArchitectureGraph(snapshot);
  return {
    title: "Architecture details",
    lines: [
      `Role: ${selectedNode.role ?? "unknown"}`,
      `Kind: ${selectedNode.kind}`,
      `Status: ${selectedNode.status}`,
      `Layer index: ${selectedNode.layer_index ?? "n/a"}`,
      `Group: ${selectedNode.group ?? "n/a"}`,
      `Graph source: ${graph?.meta.source ?? "n/a"}`,
      `Fidelity: ${graph?.meta.fidelity ?? "unknown"}`,
      `Provider: ${graph?.meta.provider ?? snapshot.runtime.provider}`,
      `Model: ${graph?.meta.model ?? snapshot.runtime.model}`,
    ],
  };
}

function getArchitectureGraphColor(role: string | undefined): string {
  if (!role) return ARCHITECTURE_NODE_COLORS.unknown;
  return ARCHITECTURE_NODE_COLORS[role] ?? ARCHITECTURE_NODE_COLORS.unknown;
}

function getArchitectureGraphLayoutOptions(
  graph: ModelArchitectureGraph,
  containerWidth: number,
  containerHeight: number,
): cytoscapeType.LayoutOptions {
  const usePresetLayout = containerWidth <= 0 || containerHeight <= 0;
  const roots = graph.nodes.find((node) => node.role === "input")?.id;
  const canUseBreadthFirst = !usePresetLayout && graph.nodes.length > 1;
  if (!canUseBreadthFirst) {
    return {
      name: "preset",
      animate: false,
      fit: true,
      padding: ARCHITECTURE_GRAPH_PADDING_PX,
    };
  }
  return {
    name: "breadthfirst",
    animate: false,
    fit: true,
    padding: ARCHITECTURE_GRAPH_PADDING_PX,
    directed: true,
    circle: false,
    spacingFactor: graph.nodes.length >= 8 ? 1.5 : 1.35,
    avoidOverlap: true,
    nodeDimensionsIncludeLabels: true,
    orientation: "horizontal",
    roots: roots ? `#${roots}` : undefined,
  };
}

function useArchitectureGraphSelectionState({
  nodes,
  transitions,
  layerInternals,
  activationPath,
}: {
  nodes: ArchitectureGraphNode[];
  transitions: ArchitectureGraphTransition[];
  layerInternals: ReturnType<typeof getAnalysisLayerInternals>;
  activationPath: ReturnType<typeof getAnalysisActivationPath> | null;
}) {
  const [selectedNodeIdState, setSelectedNodeIdState] = useState<string | null>(
    nodes[0]?.id ?? null,
  );
  const [selectedTransitionId, setSelectedTransitionId] = useState<string | null>(
    transitions[0]?.id ?? null,
  );
  const [selectedLayerIdState, setSelectedLayerIdState] = useState<string | null>(
    layerInternals[0]?.id ?? null,
  );

  const selectedNodeId = useMemo(() => {
    if (selectedNodeIdState && nodes.some((node) => node.id === selectedNodeIdState)) {
      return selectedNodeIdState;
    }
    return nodes[0]?.id ?? null;
  }, [nodes, selectedNodeIdState]);
  const selectedTransitionIdResolved = useMemo(() => {
    if (
      selectedTransitionId &&
      transitions.some((transition) => transition.id === selectedTransitionId)
    ) {
      return selectedTransitionId;
    }
    return transitions[0]?.id ?? null;
  }, [selectedTransitionId, transitions]);
  const selectedLayerId = useMemo(() => {
    if (selectedLayerIdState && layerInternals.some((layer) => layer.id === selectedLayerIdState)) {
      return selectedLayerIdState;
    }
    return layerInternals[0]?.id ?? null;
  }, [layerInternals, selectedLayerIdState]);

  const selectedLayer = useMemo(
    () => layerInternals.find((layer) => layer.id === selectedLayerId) ?? null,
    [layerInternals, selectedLayerId],
  );
  const selectedActivationLayer = useMemo(() => {
    if (!activationPath) {
      return null;
    }
    return (
      activationPath.layers.find((entry) => entry.layer === selectedLayer?.layer) ??
      activationPath.layers[0] ??
      null
    );
  }, [activationPath, selectedLayer]);

  const selectedActivationTransition = useMemo(() => {
    if (!activationPath) {
      return null;
    }
    return (
      activationPath.transitions.find(
        (transition) => transition.toLayer === selectedActivationLayer?.layer,
      ) ?? activationPath.transitions[0] ?? null
    );
  }, [activationPath, selectedActivationLayer]);

  return {
    selectedNodeId,
    setSelectedNodeId: setSelectedNodeIdState,
    selectedTransitionId: selectedTransitionIdResolved,
    setSelectedTransitionId,
    selectedLayerId,
    setSelectedLayerId: setSelectedLayerIdState,
    selectedActivationLayer,
    selectedActivationTransition,
  };
}

function buildCytoscapeElements(
  graph: ModelArchitectureGraph,
  containerWidth: number,
  containerHeight: number,
) {
  return {
    nodes: graph.nodes.map((node, index) => ({
      data: {
        id: node.id,
        label: node.label,
        kind: node.kind,
        role: node.role ?? "unknown",
        status: node.status,
        layer_index: node.layer_index ?? null,
        group: node.group ?? null,
      },
      ...((containerWidth <= 0 || containerHeight <= 0)
        ? {
            position: {
              x: 140 + (node.layer_index ?? index) * 160,
              y: 120 + index * 90,
            },
          }
        : {}),
    })),
    edges: graph.edges.map((edge, index) => ({
      data: {
        id: `${edge.from}->${edge.to}:${index}`,
        source: edge.from,
        target: edge.to,
        label: edge.label,
        kind: edge.kind ?? "relation",
        direction: edge.direction ?? "unknown",
        weight: edge.weight ?? null,
      },
    })),
  };
}

function getCytoscapeStyle(): cytoscapeType.StylesheetStyle[] {
  return [
    {
      selector: "node",
      style: {
        label: "data(label)",
        "background-color": (ele: cytoscapeType.NodeSingular) =>
          getArchitectureGraphColor(String(ele.data("role") || "unknown")),
        color: "#fff",
        "font-size": 10,
        "text-opacity": 0.85,
        "text-valign": "center",
        "text-halign": "center",
      },
    },
    { selector: "node.highlighted", style: { "border-width": 4, "border-color": "#67e8f9" } },
    {
      selector: "edge",
      style: {
        label: "data(label)",
        "font-size": 9,
        color: "#cbd5e1",
        "text-background-color": "#09090b",
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "curve-style": "bezier",
        "target-arrow-shape": "triangle",
        width: 2,
        "line-color": "#475569",
      },
    },
  ];
}

function setupResizeObserver(
  resizeObserverRef: MutableRefObject<ResizeObserver | null>,
  cyRef: MutableRefObject<HTMLDivElement | null>,
  getCy: () => cytoscapeType.Core | null,
) {
  if (typeof ResizeObserver === "undefined" || !cyRef.current) return;
  if (resizeObserverRef.current) {
    resizeObserverRef.current.disconnect();
  }
  resizeObserverRef.current = new ResizeObserver(() => {
    const cy = getCy();
    if (!cy || cy.destroyed()) return;
    cy.resize();
    cy.fit(undefined, ARCHITECTURE_GRAPH_PADDING_PX);
  });
  resizeObserverRef.current.observe(cyRef.current);
}

function registerCytoscapeEvents(
  cy: cytoscapeType.Core,
  setSelectedNodeId: (nodeId: string | null) => void,
) {
  cy.on("tap", "node", (evt: cytoscapeType.EventObject) => {
    if (cy.destroyed()) return;
    const node = evt.target;
    const nodeId = String(node.id() || "");
    if (!nodeId) return;
    setSelectedNodeId(nodeId);
    cy.nodes().removeClass("highlighted");
    node.addClass("highlighted");
  });

  cy.on("tap", (evt: cytoscapeType.EventObject) => {
    if (cy.destroyed()) return;
    if (evt.target === cy) {
      setSelectedNodeId(null);
      cy.nodes().removeClass("highlighted");
    }
  });
}

function useArchitectureGraphCytoscape({
  graph,
  cyRef,
  cyInstanceRef,
  resizeObserverRef,
  setSelectedNodeId,
}: {
  graph: ModelArchitectureGraph | null;
  cyRef: MutableRefObject<HTMLDivElement | null>;
  cyInstanceRef: MutableRefObject<cytoscapeType.Core | null>;
  resizeObserverRef: MutableRefObject<ResizeObserver | null>;
  setSelectedNodeId: (nodeId: string | null) => void;
}) {
  useEffect(() => {
    let cancelled = false;
    let cy: cytoscapeType.Core | null = null;

    const setup = async () => {
      if (cancelled || !cyRef.current || !graph?.nodes?.length) return;
      const cytoscape = (await import("cytoscape")).default;
      if (cancelled || !cyRef.current) return;
      const containerWidth = cyRef.current.clientWidth;
      const containerHeight = cyRef.current.clientHeight;

      if (cyInstanceRef.current && !cyInstanceRef.current.destroyed()) {
        cyInstanceRef.current.destroy();
      }
      cyInstanceRef.current = null;
      const elements = buildCytoscapeElements(graph, containerWidth, containerHeight);

      cy = cytoscape({
        container: cyRef.current,
        elements,
        style: getCytoscapeStyle(),
        layout: getArchitectureGraphLayoutOptions(graph, containerWidth, containerHeight),
      });

      if (cancelled || !cyRef.current) return;

      setupResizeObserver(resizeObserverRef, cyRef, () => cy);

      cy.resize();
      cy.fit(undefined, ARCHITECTURE_GRAPH_PADDING_PX);

      if (cancelled) {
        cy.destroy();
        cy = null;
        return;
      }

      registerCytoscapeEvents(cy, setSelectedNodeId);
      cyInstanceRef.current = cy;
    };

    void setup();
    return () => {
      cancelled = true;
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      if (cy) {
        try {
          cy.destroy();
        } catch {
          // best effort cleanup
        }
      }
      if (cyInstanceRef.current === cy) {
        cyInstanceRef.current = null;
      }
    };
  }, [cyInstanceRef, cyRef, graph, resizeObserverRef, setSelectedNodeId]);
}

type TensorActivationDetailProps = {
  tensorActivation: NonNullable<ArchitectureMlpActivation["tensorActivation"]>;
  layerId: string;
  t: (key: string) => string;
};

function TensorActivationDetail({ tensorActivation, layerId, t }: TensorActivationDetailProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTensorActivation")}
        </Badge>
        <Badge tone="neutral">
          {tensorActivation.vectorLength} dims
        </Badge>
        <Badge tone="neutral">
          {tensorActivation.sliceKind}
        </Badge>
      </div>
      <p className="mt-2 text-sm text-zinc-300">
        {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTensorActivationDescription")}
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <Badge tone="neutral">
          L2 MLP {tensorActivation.norms.mlpL2.toFixed(3)}
        </Badge>
        {tensorActivation.norms.residualL2 === null ? null : (
          <Badge tone="neutral">
            L2 residual {tensorActivation.norms.residualL2.toFixed(3)}
          </Badge>
        )}
        {tensorActivation.norms.deltaL2 === null ? null : (
          <Badge tone="neutral">
            L2 delta {tensorActivation.norms.deltaL2.toFixed(3)}
          </Badge>
        )}
        {tensorActivation.norms.cosineSimilarity === null ? null : (
          <Badge tone="neutral">
            cos {tensorActivation.norms.cosineSimilarity.toFixed(3)}
          </Badge>
        )}
      </div>
      {tensorActivation.topDeltaDimensions.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {tensorActivation.topDeltaDimensions.slice(0, 6).map((dimension) => (
            <Badge key={`${layerId}-tensor-delta-${dimension.index}`} tone="neutral">
              delta dim {dimension.index}: {dimension.value.toFixed(3)}
            </Badge>
          ))}
        </div>
      ) : null}



      {/* Stability section */}
      {tensorActivation.stability ? (
        <div className="mt-4 border-t border-white/10 pt-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTensorActivationStability")}
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={tensorActivation.stability.stable ? "success" : "warning"}>
              {tensorActivation.stability.stable
                ? t("inspector.modelIntrospection.dashboard.graph.stability.stable")
                : t("inspector.modelIntrospection.dashboard.graph.stability.unstable")}{" "}
              ({t(`inspector.modelIntrospection.dashboard.graph.stability.status.${tensorActivation.stability.statusLabel}`)})
            </Badge>
            <Badge tone="neutral">
              {t("inspector.modelIntrospection.dashboard.graph.stability.variance")}:{" "}
              {typeof tensorActivation.stability.mlpL2Variance === "number" && !isNaN(tensorActivation.stability.mlpL2Variance)
                ? tensorActivation.stability.mlpL2Variance.toFixed(6)
                : t("inspector.modelIntrospection.common.na")}
            </Badge>
            {tensorActivation.stability.cosineSimilarityMean !== null && tensorActivation.stability.cosineSimilarityMean !== undefined ? (
              <Badge tone="neutral">
                {t("inspector.modelIntrospection.dashboard.graph.stability.meanCos")}:{" "}
                {!isNaN(tensorActivation.stability.cosineSimilarityMean)
                  ? tensorActivation.stability.cosineSimilarityMean.toFixed(4)
                  : t("inspector.modelIntrospection.common.na")}
              </Badge>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Comparisons section */}
      {tensorActivation.comparisons && tensorActivation.comparisons.length > 0 ? (
        <div className="mt-4 border-t border-white/10 pt-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTensorActivationComparisons")}
          </p>
          <div className="mt-2 max-h-40 overflow-auto space-y-2 pr-1">
            {tensorActivation.comparisons.map((comp, index) => (
              <div key={comp.requestId || index} className="rounded-lg border border-white/5 bg-black/40 p-2 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-1 text-zinc-400">
                  <span className="font-mono">{comp.requestId ? comp.requestId.slice(0, 8) : "N/A"}</span>
                  <span>{comp.tsMs ? new Date(comp.tsMs).toLocaleString() : "N/A"}</span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-zinc-300">
                  <span>L2: {comp.mlpL2 !== null ? comp.mlpL2.toFixed(3) : "N/A"}
                    {comp.mlpL2Diff !== null && (
                      <span className={comp.mlpL2Diff >= 0 ? "text-red-400 ml-1" : "text-green-400 ml-1"}>
                        ({comp.mlpL2Diff >= 0 ? "+" : ""}{comp.mlpL2Diff.toFixed(3)})
                      </span>
                    )}
                  </span>
                  <span>cos: {comp.cosineSimilarity !== null ? comp.cosineSimilarity.toFixed(3) : "N/A"}
                    {comp.cosineSimilarityDiff !== null && (
                      <span className={comp.cosineSimilarityDiff >= 0 ? "text-green-400 ml-1" : "text-red-400 ml-1"}>
                        ({comp.cosineSimilarityDiff >= 0 ? "+" : ""}{comp.cosineSimilarityDiff.toFixed(3)})
                      </span>
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {/* Evidence section */}
      {tensorActivation.evidence && tensorActivation.evidence.length > 0 ? (
        <div className="mt-4 border-t border-white/10 pt-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTensorActivationEvidence")}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tensorActivation.evidence.map((line, idx) => (
              <Badge key={idx} tone="neutral">
                {line}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      {tensorActivation.notes.length > 0 ? (
        <div className="mt-3 border-t border-white/10 pt-2 flex flex-wrap gap-2">
          {tensorActivation.notes.map((note) => (
            <Badge key={`${layerId}-tensor-note-${note}`} tone="neutral">
              {note}
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

type ArchitectureProgressCheckpointsProps = {
  progressCheckpoints: ReturnType<typeof getArchitectureGraphProgressCheckpoints>;
  t: (key: string) => string;
};

function ArchitectureProgressCheckpoints({ progressCheckpoints, t }: ArchitectureProgressCheckpointsProps) {
  return (
    <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureProgressTitle")}
          </p>
          <p className="mt-1 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureProgressDescription")}
          </p>
        </div>
        <Badge tone="neutral">{progressCheckpoints.length} checkpoints</Badge>
      </div>
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        {progressCheckpoints.map((checkpoint) => (
          <div key={checkpoint.id} className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">{checkpoint.title}</p>
                <p className="mt-1 font-mono text-sm text-white">{checkpoint.stage}</p>
              </div>
              <Badge tone="neutral">{checkpoint.id}</Badge>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.graph.architectureProgressBefore")}
                </p>
                <p className="mt-1 text-sm text-zinc-300">{checkpoint.before}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.graph.architectureProgressAfter")}
                </p>
                <p className="mt-1 text-sm text-zinc-300">{checkpoint.after}</p>
              </div>
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.graph.architectureProgressChange")}
                </p>
                <p className="mt-1 text-sm text-zinc-300">{checkpoint.change}</p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.graph.architectureProgressResult")}
                </p>
                <p className="mt-1 text-sm text-zinc-300">{checkpoint.result}</p>
              </div>
            </div>
            <div className="mt-3">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                {t("inspector.modelIntrospection.dashboard.graph.architectureProgressEvidence")}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {checkpoint.evidence.map((line, index) => (
                  <Badge key={`${checkpoint.id}-evidence-${index}-${line}`} tone="neutral">
                    {line}
                  </Badge>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

type ArchitectureOverviewProps = {
  overview: ReturnType<typeof getArchitectureGraphOverview>;
  summary: ReturnType<typeof getArchitectureGraphSummary>;
  readiness: ModelArchitectureGraphReadiness;
  t: (key: string) => string;
};

function ArchitectureOverview({ overview, summary, readiness, t }: ArchitectureOverviewProps) {
  return (
    <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOverviewTitle")}
          </p>
          <p className="mt-1 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOverviewDescription")}
          </p>
        </div>
        <Badge tone={readiness.status === "available" ? "success" : "warning"}>
          {readiness.fidelity}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOverviewFlow")}
          </p>
          <p className="mt-1 font-mono text-sm text-white">{overview.flowLabel}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOverviewScale")}
          </p>
          <p className="mt-1 font-mono text-sm text-white">
            {formatCount(summary.layer_count)} layers · {formatCount(summary.block_count)} blocks
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">Nodes / edges</p>
          <p className="mt-1 font-mono text-sm text-white">
            {formatCount(summary.nodes)} nodes · {formatCount(summary.edges)} edges
          </p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOverviewOrigin")}
          </p>
          <p className="mt-1 font-mono text-sm text-white">{readiness.source}</p>
        </div>
      </div>
    </div>
  );
}

type ArchitectureTransitionsProps = {
  transitions: ReturnType<typeof getArchitectureGraphTransitions>;
  selectedTransitionId: string | null;
  setSelectedTransitionId: (id: string | null) => void;
  t: (key: string) => string;
};

function ArchitectureTransitions({
  transitions,
  selectedTransitionId,
  setSelectedTransitionId,
  t,
}: ArchitectureTransitionsProps) {
  return (
    <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionsTitle")}
          </p>
          <p className="mt-1 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionsDescription")}
          </p>
        </div>
        <Badge tone="neutral">
          {transitions.length} {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionsSelected")}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {transitions.map((transition) => {
          const isSelected = transition.id === selectedTransitionId;
          return (
            <button
              key={transition.id}
              type="button"
              onClick={() => setSelectedTransitionId(transition.id)}
              className={`rounded-xl border p-4 text-left transition-colors ${
                isSelected
                  ? "border-cyan-300 bg-cyan-500/15"
                  : "border-white/10 bg-black/20 hover:border-cyan-300/40 hover:bg-white/10"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-sm text-white">
                    {transition.sourceLabel} → {transition.targetLabel}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
                    {transition.label}
                  </p>
                </div>
                <Badge tone={getTransitionSignificanceTone(transition.significance)}>
                  {transition.significance}
                </Badge>
              </div>
              <p className="mt-3 text-sm text-zinc-300">{transition.effect}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

type ArchitectureOutcomeProps = {
  outcome: ReturnType<typeof getArchitectureGraphOutcome>;
  readiness: ModelArchitectureGraphReadiness;
  readinessTone: BadgeTone;
  t: (key: string) => string;
};

function ArchitectureOutcome({ outcome, readiness, readinessTone, t }: ArchitectureOutcomeProps) {
  return (
    <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeTitle")}
          </p>
          <p className="mt-1 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeDescription")}
          </p>
        </div>
        <Badge tone={readinessTone}>{readiness.status}</Badge>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeResult")}
          </p>
          <p className="mt-2 text-sm text-zinc-300">{outcome.result}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomePrimaryPath")}
          </p>
          <p className="mt-2 font-mono text-sm text-white">{outcome.primaryPath}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeSummary")}
          </p>
          <p className="mt-2 text-sm text-zinc-300">{outcome.summary}</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeEvidence")}
          </p>
          <div className="mt-2 space-y-1 text-sm text-zinc-300">
            {outcome.evidence.map((line, index) => (
              <p key={`outcome-evidence-${index}-${line}`}>{line}</p>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureOutcomeSignals")}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {outcome.supportingSignals.map((signal, index) => (
            <Badge key={`outcome-signal-${index}-${signal}`} tone="neutral">
              {signal}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

type ArchitectureTransitionDetailProps = {
  selectedTransition: ReturnType<typeof getArchitectureGraphTransitions>[number] | null;
  t: (key: string) => string;
};

function ArchitectureTransitionDetail({ selectedTransition, t }: ArchitectureTransitionDetailProps) {
  return (
    <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionDetailTitle")}
        </p>
        <Badge tone={selectedTransition ? "success" : "neutral"}>
          {selectedTransition ? "transition selected" : "awaiting selection"}
        </Badge>
      </div>
      {selectedTransition ? (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{selectedTransition.sourceRole}</Badge>
            <Badge tone="neutral">{selectedTransition.targetRole}</Badge>
            <Badge tone="neutral">{selectedTransition.significance}</Badge>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Transition</p>
            <p className="mt-1 font-mono text-sm text-white">
              {selectedTransition.sourceLabel} → {selectedTransition.targetLabel}
            </p>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionBefore")}
              </p>
              <p className="mt-2 font-mono text-sm text-white">{selectedTransition.before}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionAfter")}
              </p>
              <p className="mt-2 font-mono text-sm text-white">{selectedTransition.after}</p>
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionDelta")}
            </p>
            <p className="mt-2 text-sm text-zinc-300">{selectedTransition.delta}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionImpact")}
            </p>
            <p className="mt-2 text-sm text-zinc-300">{selectedTransition.impact}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionEffect")}
            </p>
            <p className="mt-2 text-sm text-zinc-300">{selectedTransition.effect}</p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-300">
          {t("inspector.modelIntrospection.dashboard.graph.architectureTransitionEmpty")}
        </p>
      )}
    </div>
  );
}

type ArchitectureDrilldownProps = {
  selectedNode: ModelArchitectureGraphNode | null;
  selectedNodeDetails: GraphNodeDetails;
  typeHintText: string;
};

function ArchitectureDrilldown({ selectedNode, selectedNodeDetails, typeHintText }: ArchitectureDrilldownProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Architecture drilldown</p>
        <Badge tone={selectedNode ? "success" : "neutral"}>
          {selectedNode ? "node selected" : "awaiting selection"}
        </Badge>
      </div>
      {selectedNode ? (
        <div className="mt-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{selectedNode.role ?? "unknown"}</Badge>
            <Badge tone="neutral">{selectedNode.status}</Badge>
          </div>
          <div>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Label</p>
            <p className="mt-1 font-mono text-sm text-white">{selectedNode.label}</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {selectedNodeDetails.title}
            </p>
            <div className="mt-2 space-y-1 text-sm text-zinc-300">
              {selectedNodeDetails.lines.map((line, index) => (
                <p key={`node-detail-${index}-${line}`}>{line}</p>
              ))}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">Type hint</p>
            <p className="mt-1 text-sm text-zinc-300">{typeHintText}</p>
          </div>
        </div>
      ) : (
        <p className="mt-3 text-sm text-zinc-300">
          Select a model layer, block or diagnostic node to inspect its architecture details.
        </p>
      )}
    </div>
  );
}

type ArchitectureRelationsProps = {
  edges: ModelArchitectureGraphEdge[];
};

function ArchitectureRelations({ edges }: ArchitectureRelationsProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-zinc-500">Relations</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {edges.map((edge, index) => (
          <Badge key={`${edge.from}-${edge.to}-${edge.label}-${index}`} tone="neutral">
            {edge.from} → {edge.to} ({edge.label})
          </Badge>
        ))}
      </div>
    </div>
  );
}

type LayerInternalsDetailPanelProps = {
  selectedLayer: ArchitectureLayerInternals | null;
  selectedDominantSignals: ReturnType<typeof getArchitectureLayerDominantSignals>;
  activationPath: ArchitectureActivationPath | null;
  selectedActivationLayer: ArchitectureActivationPath["layers"][number] | null;
  selectedActivationTransition: ArchitectureActivationPath["transitions"][number] | null;
  architectureBlocks: AnalysisLayerInternalsBlock[];
  mlpActivation: ArchitectureMlpActivation | null;
  t: (key: string) => string;
};

function LayerInternalsDetailPanel({
  selectedLayer,
  selectedDominantSignals,
  activationPath,
  selectedActivationLayer,
  selectedActivationTransition,
  architectureBlocks,
  mlpActivation,
  t,
}: LayerInternalsDetailPanelProps) {
  if (!selectedLayer) {
    return (
      <p className="mt-3 text-sm text-zinc-300">
        {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsEmptySelection")}
      </p>
    );
  }

  return (
    <div className="mt-3 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">{selectedLayer.status}</Badge>
        <Badge tone="neutral">layer {selectedLayer.layer}</Badge>
      </div>
      <div>
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsLabel")}
        </p>
        <p className="mt-1 font-mono text-sm text-white">{selectedLayer.label}</p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsSummary")}
        </p>
        <p className="mt-2 text-sm text-zinc-300">{selectedLayer.summary}</p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsStateDelta")}
        </p>
        <p className="mt-2 text-sm text-zinc-300">{selectedLayer.stateDelta}</p>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsDominantSignals")}
          </p>
          <Badge tone={selectedDominantSignals.length > 0 ? "success" : "neutral"}>
            {selectedDominantSignals.length}
          </Badge>
        </div>
        <p className="mt-2 text-sm text-zinc-300">
          {selectedDominantSignals.length > 0
            ? t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsDominantSignalsDescription")
            : t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
        </p>
        <div className="mt-3 space-y-2">
          {selectedDominantSignals.length > 0
            ? selectedDominantSignals.map((signal) => (
                <div
                  key={`${selectedLayer.id}-${signal.source}-${signal.label}`}
                  className="rounded-lg border border-white/10 bg-black/20 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={signal.dominant ? "success" : "neutral"}>
                      {signal.dominant ? "dominant" : signal.source}
                    </Badge>
                    <Badge tone="neutral">{signal.source}</Badge>
                    <Badge tone="neutral">{signal.label}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-zinc-300">{signal.detail}</p>
                  {signal.evidence.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {signal.evidence.map((line, index) => (
                        <Badge key={`${selectedLayer.id}-${signal.source}-${signal.label}-dominant-evidence-${index}-${line}`} tone="neutral">
                          {line}
                        </Badge>
                      ))}
                    </div>
                  ) : null}
                </div>
              ))
            : null}
        </div>
      </div>
      {activationPath ? (
        <div className="rounded-xl border border-cyan-400/20 bg-cyan-500/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationPath")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="neutral">
                {activationPath.summary.selectedLayerCount}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationLayers")}
              </Badge>
              <Badge tone="neutral">
                {activationPath.summary.transitionCount}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationTransitions")}
              </Badge>
            </div>
          </div>
          {activationPath.notes.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {activationPath.notes.slice(0, 2).map((note, index) => (
                <Badge key={`${selectedLayer.id}-activation-note-${index}-${note}`} tone="neutral">
                  {note}
                </Badge>
              ))}
            </div>
          ) : null}
          {selectedActivationLayer ? (
            <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                    {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationLayer")}
                  </p>
                  <p className="mt-1 font-mono text-sm text-white">
                    {selectedActivationLayer.label}
                  </p>
                </div>
                <Badge tone="neutral">layer {selectedActivationLayer.layer}</Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone="neutral">
                  mean {selectedActivationLayer.metrics.mean.toFixed(3)}
                </Badge>
                <Badge tone="neutral">
                  norm {selectedActivationLayer.metrics.norm.toFixed(3)}
                </Badge>
                <Badge tone="neutral">
                  max |x| {selectedActivationLayer.metrics.maxAbs.toFixed(3)}
                </Badge>
                {selectedActivationLayer.roleHint ? (
                  <Badge tone="neutral">{selectedActivationLayer.roleHint}</Badge>
                ) : null}
              </div>
              <p className="mt-3 text-sm text-zinc-300">
                {selectedActivationLayer.summary}
              </p>
              {selectedActivationLayer.metrics.topDimensions.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedActivationLayer.metrics.topDimensions.map((dimension) => (
                    <Badge
                      key={`${selectedActivationLayer.layer}-${dimension.index}`}
                      tone="neutral"
                    >
                      dim {dimension.index}: {dimension.value.toFixed(3)}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {selectedActivationTransition ? (
            <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                  {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationTransition")}
                </p>
                <Badge tone="neutral">
                  {selectedActivationTransition.fromLayer} → {selectedActivationTransition.toLayer}
                </Badge>
              </div>
              <p className="mt-2 font-mono text-sm text-white">
                {selectedActivationTransition.before} → {selectedActivationTransition.after}
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Badge tone="neutral">
                  ΔL2 {selectedActivationTransition.deltaNorm.toFixed(3)}
                </Badge>
                <Badge tone="neutral">
                  Δmean {selectedActivationTransition.meanShift.toFixed(3)}
                </Badge>
                <Badge tone="neutral">
                  peak |Δ| {selectedActivationTransition.maxAbsShift.toFixed(3)}
                </Badge>
              </div>
              <p className="mt-3 text-sm text-zinc-300">
                {selectedActivationTransition.summary}
              </p>
              <p className="mt-2 text-sm text-zinc-400">
                {selectedActivationTransition.impact}
              </p>
              {selectedActivationTransition.evidence.length > 0 ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedActivationTransition.evidence.map((line, index) => (
                    <Badge key={`${selectedLayer.id}-activation-transition-evidence-${index}-${line}`} tone="neutral">
                      {line}
                    </Badge>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsBlocks")}
        </p>
        <div className="mt-2 space-y-2">
          {selectedLayer.blocks.length > 0 ? (
            selectedLayer.blocks.map((block) => (
              <div key={`${selectedLayer.id}-${block.kind}-${block.label}`} className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{block.kind}</Badge>
                  <Badge tone="neutral">{block.label}</Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-300">{block.summary}</p>
                <p className="mt-2 text-sm text-zinc-400">{block.detail}</p>
                <p className="mt-2 text-sm text-zinc-400">{block.impact}</p>
                {block.heads?.length ? (
                  <div className="mt-3 rounded-lg border border-white/10 bg-white/5 p-3">
                    <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                      {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsHeads")}
                    </p>
                    <div className="mt-2 space-y-2">
                      {block.heads.map((head) => (
                        <div key={`${selectedLayer.id}-${block.kind}-${block.label}-head-${head.head}`} className="rounded-md border border-white/10 bg-black/20 p-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge tone="neutral">head {head.head}</Badge>
                            <Badge tone="neutral">{head.summary}</Badge>
                          </div>
                          <p className="mt-2 text-sm text-zinc-300">{head.detail}</p>
                          {head.evidence.length > 0 ? (
                            <div className="mt-2 flex flex-wrap gap-2">
                              {head.evidence.map((line, index) => (
                                <Badge key={`${selectedLayer.id}-${block.label}-head-${head.head}-evidence-${index}-${line}`} tone="neutral">
                                  {line}
                                </Badge>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                {block.evidence.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {block.evidence.map((line, index) => (
                      <Badge key={`${selectedLayer.id}-${block.label}-evidence-${index}-${line}`} tone="neutral">
                        {line}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <p className="text-sm text-zinc-300">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
            </p>
          )}
        </div>
      </div>
      {architectureBlocks.length > 0 ? (
        <div className="rounded-xl border border-white/10 bg-white/5 p-4">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsArchitectureBlocks")}
          </p>
          <div className="mt-3 space-y-2">
            {architectureBlocks.map((block) => (
              <div key={`${selectedLayer.id}-${block.kind}-${block.label}`} className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{block.kind}</Badge>
                  <Badge tone="neutral">{block.label}</Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-300">{block.summary}</p>
                <p className="mt-2 text-sm text-zinc-400">{block.detail}</p>
                <p className="mt-2 text-sm text-zinc-400">{block.impact}</p>
                {block.evidence.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {block.evidence.map((line, index) => (
                      <Badge key={`${selectedLayer.id}-${block.label}-arch-evidence-${index}-${line}`} tone="neutral">
                        {line}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsSignals")}
        </p>
        <div className="mt-2 space-y-2">
          {selectedLayer.signals.length > 0 ? (
            selectedLayer.signals.map((signal) => (
              <div key={`${selectedLayer.id}-${signal.source}-${signal.label}`} className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{signal.source}</Badge>
                  <Badge tone="neutral">{signal.label}</Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-300">{signal.detail}</p>
                {signal.evidence.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {signal.evidence.map((line, index) => (
                      <Badge key={`${selectedLayer.id}-${signal.source}-${signal.label}-evidence-${index}-${line}`} tone="neutral">
                        {line}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          ) : (
            <p className="text-sm text-zinc-300">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
            </p>
          )}
        </div>
      </div>
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsResponseLinkage")}
          </p>
          {selectedLayer.responseLinkage ? (
            <Badge tone={selectedLayer.responseLinkage.status === "linked" ? "success" : "warning"}>
              {selectedLayer.responseLinkage.coveragePercent.toFixed(2)}%
            </Badge>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-zinc-300">
          {selectedLayer.responseLinkage
            ? t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsResponseLinkageDescription")
            : t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
        </p>
        {selectedLayer.responseLinkage ? (
          <div className="mt-3 space-y-3">
            <div className="flex flex-wrap gap-2">
              <Badge tone="neutral">
                {selectedLayer.responseLinkage.linkedFragmentCount}/{selectedLayer.responseLinkage.fragmentCount}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsResponseLinkageFragments")}
              </Badge>
              <Badge tone="neutral">
                {selectedLayer.responseLinkage.evidenceLinks.length}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsResponseLinkageEvidence")}
              </Badge>
            </div>
            <p className="text-sm text-zinc-300">{selectedLayer.responseLinkage.summary}</p>
            <p className="text-sm text-zinc-400">{selectedLayer.responseLinkage.impact}</p>
            {selectedLayer.responseLinkage.dominantSignals.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {selectedLayer.responseLinkage.dominantSignals.map((signal) => (
                  <Badge key={`${selectedLayer.id}-response-signal-${signal}`} tone="neutral">
                    {signal}
                  </Badge>
                ))}
              </div>
            ) : null}
            {selectedLayer.responseLinkage.linkedFragments.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {selectedLayer.responseLinkage.linkedFragments.map((fragment) => (
                  <Badge key={`${selectedLayer.id}-response-fragment-${fragment}`} tone="neutral">
                    {fragment}
                  </Badge>
                ))}
              </div>
            ) : null}
            {selectedLayer.responseLinkage.evidenceLinks.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {selectedLayer.responseLinkage.evidenceLinks.map((link) => (
                  <Badge key={`${selectedLayer.id}-response-link-${link}`} tone="neutral">
                    {link}
                  </Badge>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      {mlpActivation ? (
        <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsMlpActivation")}
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={mlpActivation.status === "ok" ? "success" : "warning"}>
                {mlpActivation.status}
              </Badge>
              <Badge tone="neutral">
                {mlpActivation.summary.hiddenDimensionCount}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsMlpActivationDimensions")}
              </Badge>
            </div>
          </div>
          <p className="mt-2 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsMlpActivationDescription")}
          </p>
          <div className="mt-3 space-y-3">
            {mlpActivation.mlpLayer ? (
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{mlpActivation.mlpLayer.label}</Badge>
                  <Badge tone="neutral">
                    layer {mlpActivation.mlpLayer.layer}
                  </Badge>
                  {mlpActivation.mlpLayer.roleHint ? (
                    <Badge tone="neutral">{mlpActivation.mlpLayer.roleHint}</Badge>
                  ) : null}
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  {mlpActivation.mlpLayer.summary}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge tone="neutral">
                    mean {mlpActivation.mlpLayer.metrics.mean.toFixed(3)}
                  </Badge>
                  <Badge tone="neutral">
                    norm {mlpActivation.mlpLayer.metrics.norm.toFixed(3)}
                  </Badge>
                  <Badge tone="neutral">
                    max |x| {mlpActivation.mlpLayer.metrics.maxAbs.toFixed(3)}
                  </Badge>
                </div>
                {mlpActivation.mlpLayer.metrics.topDimensions.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {mlpActivation.mlpLayer.metrics.topDimensions.map((dimension) => (
                      <Badge key={`${selectedLayer.id}-mlp-dim-${dimension.index}`} tone="neutral">
                        dim {dimension.index}: {dimension.value.toFixed(3)}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                {mlpActivation.mlpLayer.evidence.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {mlpActivation.mlpLayer.evidence.map((line) => (
                      <Badge key={`${selectedLayer.id}-mlp-evidence-${line}`} tone="neutral">
                        {line}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {mlpActivation.transition ? (
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">
                    {mlpActivation.transition.before} → {mlpActivation.transition.after}
                  </Badge>
                  <Badge tone="neutral">
                    ΔL2 {mlpActivation.transition.deltaNorm.toFixed(3)}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  {mlpActivation.transition.summary}
                </p>
                <p className="mt-2 text-sm text-zinc-400">
                  {mlpActivation.transition.impact}
                </p>
                {mlpActivation.transition.evidence.length > 0 ? (
                  <div className="mt-2 flex flex-wrap gap-2">
                    {mlpActivation.transition.evidence.map((line) => (
                      <Badge key={`${selectedLayer.id}-mlp-transition-${line}`} tone="neutral">
                        {line}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            {mlpActivation.residualLayer ? (
              <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">{mlpActivation.residualLayer.label}</Badge>
                  <Badge tone="neutral">
                    layer {mlpActivation.residualLayer.layer}
                  </Badge>
                </div>
                <p className="mt-2 text-sm text-zinc-300">
                  {mlpActivation.residualLayer.summary}
                </p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <Badge tone="neutral">
                    mean {mlpActivation.residualLayer.metrics.mean.toFixed(3)}
                  </Badge>
                  <Badge tone="neutral">
                    norm {mlpActivation.residualLayer.metrics.norm.toFixed(3)}
                  </Badge>
                  <Badge tone="neutral">
                    max |x| {mlpActivation.residualLayer.metrics.maxAbs.toFixed(3)}
                  </Badge>
                </div>
              </div>
            ) : null}
            {mlpActivation.tensorActivation ? (
              <TensorActivationDetail
                tensorActivation={mlpActivation.tensorActivation}
                layerId={selectedLayer.id}
                t={t}
              />
            ) : null}
          </div>
          {mlpActivation.notes.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {mlpActivation.notes.slice(0, 3).map((note, index) => (
                <Badge key={`${selectedLayer.id}-mlp-note-${index}-${note}`} tone="neutral">
                  {note}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
      <div className="rounded-xl border border-white/10 bg-white/5 p-4">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">
          {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsEvidence")}
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {selectedLayer.evidence.length > 0 ? (
            selectedLayer.evidence.map((line, index) => (
              <Badge key={`${selectedLayer.id}-layer-evidence-${index}-${line}`} tone="neutral">
                {line}
              </Badge>
            ))
          ) : (
            <p className="text-sm text-zinc-300">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

type ArchitectureLayerInternalsSectionProps = {
  layerInternals: ArchitectureLayerInternals[];
  layerInternalsPayload: AnalysisLayerInternalsPayload | null;
  selectedLayerId: string | null;
  setSelectedLayerId: (id: string | null) => void;
  selectedLayer: ArchitectureLayerInternals | null;
  selectedDominantSignals: ReturnType<typeof getArchitectureLayerDominantSignals>;
  activationPath: ArchitectureActivationPath | null;
  selectedActivationLayer: ArchitectureActivationPath["layers"][number] | null;
  selectedActivationTransition: ArchitectureActivationPath["transitions"][number] | null;
  architectureBlocks: AnalysisLayerInternalsBlock[];
  mlpActivation: ArchitectureMlpActivation | null;
  t: (key: string) => string;
};

function ArchitectureLayerInternalsSection({
  layerInternals,
  layerInternalsPayload,
  selectedLayerId,
  setSelectedLayerId,
  selectedLayer,
  selectedDominantSignals,
  activationPath,
  selectedActivationLayer,
  selectedActivationTransition,
  architectureBlocks,
  mlpActivation,
  t,
}: ArchitectureLayerInternalsSectionProps) {
  return (
    <div className="mt-4 rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-zinc-500">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsTitle")}
          </p>
          <p className="mt-1 text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsDescription")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">
            {layerInternals.length} {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsCount")}
          </Badge>
          {layerInternalsPayload?.summary ? (
            <>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.checkpoint_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsCheckpoints")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.block_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsBlocks")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.architecture_block_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsArchitectureBlocks")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.activation_layer_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationLayers")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.activation_transition_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsActivationTransitions")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.attention_layer_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsAttentionLayers")}
              </Badge>
              <Badge tone="neutral">
                {layerInternalsPayload.summary.saliency_token_count}{" "}
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsSaliencyTokens")}
              </Badge>
            </>
          ) : null}
          {layerInternalsPayload ? <Badge tone="neutral">{layerInternalsPayload.source}</Badge> : null}
        </div>
      </div>
      {layerInternalsPayload?.notes?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {layerInternalsPayload.notes.slice(0, 3).map((note, index) => (
            <Badge key={`internals-note-${index}-${note}`} tone="neutral">
              {note}
            </Badge>
          ))}
        </div>
      ) : null}
      {layerInternals.length > 0 ? (
        <div className="mt-4 grid gap-4 xl:grid-cols-[0.95fr_1.05fr]">
          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsList")}
            </p>
            <div className="mt-3 max-h-80 space-y-2 overflow-auto pr-1">
              {layerInternals.map((layer) => {
                const isSelected = layer.id === selectedLayerId;
                return (
                  <button
                    key={layer.id}
                    type="button"
                    onClick={() => setSelectedLayerId(layer.id)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition-colors ${
                      isSelected
                        ? "border-cyan-300 bg-cyan-500/15"
                        : "border-white/10 bg-white/5 hover:border-cyan-300/40 hover:bg-white/10"
                    }`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-mono text-sm text-white">{layer.label}</p>
                        <p className="mt-1 text-xs uppercase tracking-wide text-zinc-500">
                          {layer.status}
                        </p>
                      </div>
                      <Badge tone={isSelected ? "success" : "neutral"}>{layer.layer}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-zinc-300">{layer.summary}</p>
                  </button>
                );
              })}
            </div>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsSelected")}
              </p>
              <Badge tone={selectedLayer ? "success" : "neutral"}>
                {selectedLayer ? "layer selected" : "awaiting selection"}
              </Badge>
            </div>
            <LayerInternalsDetailPanel
              selectedLayer={selectedLayer}
              selectedDominantSignals={selectedDominantSignals}
              activationPath={activationPath}
              selectedActivationLayer={selectedActivationLayer}
              selectedActivationTransition={selectedActivationTransition}
              architectureBlocks={architectureBlocks}
              mlpActivation={mlpActivation}
              t={t}
            />
          </div>
        </div>
      ) : (
        <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-4">
          <p className="text-sm text-zinc-300">
            {t("inspector.modelIntrospection.dashboard.graph.architectureLayerInternalsNoData")}
          </p>
        </div>
      )}
    </div>
  );
}

export function ArchitectureGraphPanel(props: ArchitectureGraphPanelProps) {
  const {
    snapshot,
    readiness,
    layerInternalsPayload,
    title,
    description,
    typeHintText,
  } = props;
  const t = useTranslation();
  const graph = getArchitectureGraph(snapshot);
  const nodes = useMemo(() => getArchitectureGraphNodes(snapshot), [snapshot]);
  const edges = useMemo(() => getArchitectureGraphEdges(snapshot), [snapshot]);
  const summary = useMemo(() => getArchitectureGraphSummary(snapshot), [snapshot]);
  const overview = useMemo(() => getArchitectureGraphOverview(snapshot), [snapshot]);
  const transitions = useMemo(() => getArchitectureGraphTransitions(snapshot), [snapshot]);
  const layerInternals = useMemo(
    () => getAnalysisLayerInternals(layerInternalsPayload),
    [layerInternalsPayload],
  );
  const activationPath = useMemo(
    () => getAnalysisActivationPath(layerInternalsPayload),
    [layerInternalsPayload],
  );
  const mlpActivation = useMemo(
    () => getAnalysisMlpActivation(layerInternalsPayload),
    [layerInternalsPayload],
  );
  const architectureBlocks = useMemo(
    () => layerInternalsPayload?.architecture_blocks ?? [],
    [layerInternalsPayload],
  );
  const progressCheckpoints = useMemo(
    () => getArchitectureGraphProgressCheckpoints(snapshot, transitions, summary, overview),
    [overview, snapshot, summary, transitions],
  );
  const outcome = useMemo(
    () => getArchitectureGraphOutcome(readiness, overview, summary, transitions),
    [readiness, overview, summary, transitions],
  );
  const readinessTone = getReadinessTone(readiness.status);
  const selection = useArchitectureGraphSelectionState({
    nodes,
    transitions,
    layerInternals,
    activationPath,
  });
  const {
    selectedNodeId,
    setSelectedNodeId,
    selectedTransitionId,
    setSelectedTransitionId,
    selectedLayerId,
    setSelectedLayerId,
    selectedActivationLayer,
    selectedActivationTransition,
  } = selection;
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  );
  const selectedTransition = useMemo(
    () => transitions.find((transition) => transition.id === selectedTransitionId) ?? null,
    [selectedTransitionId, transitions],
  );
  const selectedLayer = useMemo(
    () => layerInternals.find((layer) => layer.id === selectedLayerId) ?? null,
    [layerInternals, selectedLayerId],
  );
  useEffect(() => {
    if (
      selectedNode?.role === "layer" &&
      selectedNode.id !== selectedLayerId &&
      layerInternals.some((layer) => layer.id === selectedNode.id)
    ) {
      setSelectedLayerId(selectedNode.id);
    }
  }, [layerInternals, selectedLayerId, selectedNode, setSelectedLayerId]);
  const selectedDominantSignals = useMemo(
    () => getArchitectureLayerDominantSignals(selectedLayer),
    [selectedLayer],
  );
  const selectedNodeDetails = useMemo(
    () => getArchitectureGraphNodeDetails(snapshot, selectedNode),
    [selectedNode, snapshot],
  );

  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstanceRef = useRef<cytoscapeType.Core | null>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  useArchitectureGraphCytoscape({
    graph,
    cyRef,
    cyInstanceRef,
    resizeObserverRef,
    setSelectedNodeId,
  });

  if (!graph) {
    return null;
  }

  return (
    <div className="rounded-2xl border border-cyan-400/20 bg-cyan-500/5 p-5">
      <div className="space-y-1">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{"// architecture"}</p>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="text-sm text-zinc-300">{description}</p>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Badge tone={getReadinessTone(readiness.status)}>
          ready {readiness.status}
        </Badge>
        <Badge tone="neutral">nodes {formatCount(summary.nodes)}</Badge>
        <Badge tone="neutral">edges {formatCount(summary.edges)}</Badge>
        <Badge tone="neutral">layers {formatCount(summary.layer_count)}</Badge>
        <Badge tone="neutral">blocks {formatCount(summary.block_count)}</Badge>
      </div>

      <ArchitectureProgressCheckpoints
        progressCheckpoints={progressCheckpoints}
        t={t}
      />

      <ArchitectureLayerInternalsSection
        layerInternals={layerInternals}
        layerInternalsPayload={layerInternalsPayload}
        selectedLayerId={selectedLayerId}
        setSelectedLayerId={setSelectedLayerId}
        selectedLayer={selectedLayer}
        selectedDominantSignals={selectedDominantSignals}
        activationPath={activationPath}
        selectedActivationLayer={selectedActivationLayer}
        selectedActivationTransition={selectedActivationTransition}
        architectureBlocks={architectureBlocks}
        mlpActivation={mlpActivation}
        t={t}
      />

      <ArchitectureOverview
        overview={overview}
        summary={summary}
        readiness={readiness}
        t={t}
      />

      <ArchitectureTransitions
        transitions={transitions}
        selectedTransitionId={selectedTransitionId}
        setSelectedTransitionId={setSelectedTransitionId}
        t={t}
      />

      <ArchitectureOutcome
        outcome={outcome}
        readiness={readiness}
        readinessTone={readinessTone}
        t={t}
      />

      <div className="mt-4 grid items-stretch gap-4 xl:grid-cols-[1.45fr_0.85fr]">
        <div className="min-h-[560px] overflow-hidden rounded-2xl border border-white/10 bg-black/20">
          <div
            ref={cyRef}
            data-testid="architecture-graph-container"
            className="h-[clamp(560px,72vh,760px)] w-full"
          />
        </div>
        <div className="flex h-full flex-col space-y-4">
          <ArchitectureTransitionDetail
            selectedTransition={selectedTransition}
            t={t}
          />
          <ArchitectureDrilldown
            selectedNode={selectedNode}
            selectedNodeDetails={selectedNodeDetails}
            typeHintText={typeHintText}
          />
          <ArchitectureRelations edges={edges} />
        </div>
      </div>
      <div className="mt-4 rounded-2xl border border-dashed border-white/10 bg-white/5 p-4 text-sm text-zinc-300">
        Architecture graph data should describe layer flow, residual structure and block-level
        relations. Current diagnostic graph stays available below as a separate surface.
      </div>
    </div>
  );
}

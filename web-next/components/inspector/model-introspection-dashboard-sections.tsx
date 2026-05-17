"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
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
  AttentionModel,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
  LogitLensModel,
  OperatorConclusionModel,
  RagFocusModel,
  SaliencyModel,
  SnapshotComparison,
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
  snapshotReady: boolean;
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
    snapshotReady,
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
          disabled={analysisLoading || !snapshotReady || !analysisMechanismEnabled}
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
  } = props;

  if (!logitLens) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
        <p className="text-xs uppercase tracking-wide text-zinc-500">{title}</p>
        <p className="mt-3 text-sm text-zinc-400">{emptyLabel}</p>
      </div>
    );
  }

  const available = logitLens.status === "ok" && logitLens.checkpoints.length > 0;
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
  const inputPreview = logitLens.input_tokens.slice(0, 6).join(" · ");
  const outputPreview = logitLens.output_tokens.slice(0, 6).join(" · ");

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
      </div>
      {logitLens.source !== "probe_runtime" && (
        <p className="mt-2 text-xs text-amber-200/90">{sourceFallbackWarning}</p>
      )}
      <div className="mt-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-300">
        <p className="uppercase tracking-wide text-zinc-500">{tokensLabel}</p>
        <p className="mt-1">{inputPreview || "—"}</p>
        <p className="mt-1 text-zinc-500">→</p>
        <p className="mt-1">{outputPreview || "—"}</p>
      </div>
      <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">{checkpointsLabel}</p>
      <div className="mt-2 grid gap-2 lg:grid-cols-2">
        {logitLens.checkpoints.map((checkpoint) => {
          const topCandidates = checkpoint.top_k.slice(0, 3);
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
                    {index + 1}. {candidate.token} ({formatCheckpointScore(candidate.score)})
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
        {t("inspector.modelIntrospection.dashboard.results.runTrends.window")}{" "}
        {runTrends.window}
      </Badge>
    </div>
  );
}

export function AnalysisResultsPanel(props: AnalysisResultsPanelProps) {
  const t = useTranslation();
  const {
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
    <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
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
            {analysisTimeline.map((step) => (
              <div key={step.id} className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-white">{step.label}</p>
                    <p className="mt-1 text-xs text-zinc-400">{step.detail}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {step.path && (
                      <Badge tone={getTimelinePathTone(step.path)}>{step.path}</Badge>
                    )}
                    {typeof step.progress === "number" && (
                      <Badge tone="neutral">{formatCount(Math.round(step.progress))}%</Badge>
                    )}
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
  graphViewOpen: boolean;
  onToggleGraphView: () => void;
  selectedGraphNodeId: string | null;
  onSelectGraphNode: (id: string) => void;
  selectedGraphNode: GraphNodeItem | null;
  selectedGraphNodeDetails: GraphNodeDetails | null;
  typeHintText: string;
  title: string;
  description: string;
  drilldownTitle: string;
  hideLabel: string;
  openLabel: string;
  stateOpenLabel: string;
  stateCollapsedLabel: string;
}>;

type GraphNodeItem = NonNullable<IntrospectionSnapshot["graph"]>["nodes"][number];
type GraphEdgeItem = NonNullable<IntrospectionSnapshot["graph"]>["edges"][number];

type GraphOverviewBadgesProps = Readonly<{ snapshot: IntrospectionSnapshot }>;
type GraphDrilldownToggleProps = Readonly<{
  graphViewOpen: boolean;
  onToggleGraphView: () => void;
  drilldownTitle: string;
  hideLabel: string;
  openLabel: string;
  stateOpenLabel: string;
  stateCollapsedLabel: string;
}>;
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

function GraphDrilldownToggle(props: GraphDrilldownToggleProps) {
  const {
    graphViewOpen,
    onToggleGraphView,
    drilldownTitle,
    hideLabel,
    openLabel,
    stateOpenLabel,
    stateCollapsedLabel,
  } = props;
  return (
    <button
      type="button"
      onClick={onToggleGraphView}
      aria-expanded={graphViewOpen}
      className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:border-white/20 hover:bg-white/10"
    >
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{drilldownTitle}</p>
        <p className="mt-1 text-sm text-zinc-200">{graphViewOpen ? hideLabel : openLabel}</p>
      </div>
      <Badge tone={graphViewOpen ? "success" : "neutral"}>
        {graphViewOpen ? stateOpenLabel : stateCollapsedLabel}
      </Badge>
    </button>
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
    graphViewOpen,
    onToggleGraphView,
    selectedGraphNodeId,
    onSelectGraphNode,
    selectedGraphNode,
    selectedGraphNodeDetails,
    typeHintText,
    title,
    description,
    drilldownTitle,
    hideLabel,
    openLabel,
    stateOpenLabel,
    stateCollapsedLabel,
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
        <GraphDrilldownToggle
          graphViewOpen={graphViewOpen}
          onToggleGraphView={onToggleGraphView}
          drilldownTitle={drilldownTitle}
          hideLabel={hideLabel}
          openLabel={openLabel}
          stateOpenLabel={stateOpenLabel}
          stateCollapsedLabel={stateCollapsedLabel}
        />

        {graphViewOpen && (
          <>
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
          </>
        )}
      </div>
    </div>
  );
}

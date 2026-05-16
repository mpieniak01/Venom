"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  clampPercent,
  formatCount,
  getAnalysisProgressBarColor,
  getGraphNodeTone,
  getOrbCoreShadow,
  getPackageRingColor,
  getPhaseLabel,
  getPhaseTone,
  shortenTraceId,
  timelineBadgeTone,
} from "@/components/inspector/model-introspection-dashboard-view-model";
import type {
  AnalysisPhase,
  AnalysisProcessTrace,
  AnalysisTimelineEntry,
  BadgeTone,
  GraphNodeDetails,
  IntrospectionSnapshot,
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
  analysisStreaming: boolean;
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
  waitingTokenLabel: string;
  streamingLabel: string;
  resultsAnswerLabel: string;
  resultsHighlightsLabel: string;
  highlightsEmptyLabel: string;
  resultsVerdictLabel: string;
  resultsVerdictReady: string;
  resultsVerdictPending: string;
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
  const intensity = clampPercent(chunks * 32);
  const elapsedFactor = clampPercent(elapsedMs / 120);
  const packageCoveragePercent = clampPercent(packageCoverage);
  const progressPercent = clampPercent(progress);
  const [displayProgress, setDisplayProgress] = useState(progressPercent);
  const displayProgressRef = useRef(progressPercent);
  const phaseLabel = getPhaseLabel(phase);
  const phaseTone = getPhaseTone(phase);
  const colors = getPhaseStyles(phase);
  const packageRingColor = getPackageRingColor(packageCoveragePercent);
  const isAnimating = active && phase !== "completed";

  useEffect(() => {
    displayProgressRef.current = displayProgress;
  }, [displayProgress]);

  useEffect(() => {
    type FrameHandle = number | ReturnType<typeof globalThis.setTimeout>;
    const hasRaf =
      typeof globalThis.requestAnimationFrame === "function" &&
      typeof globalThis.cancelAnimationFrame === "function";
    const scheduleFrame = (callback: FrameRequestCallback): FrameHandle => {
      if (hasRaf) {
        return globalThis.requestAnimationFrame(callback);
      }
      return globalThis.setTimeout(() => callback(performance.now()), 16);
    };
    let frameId: FrameHandle | null = null;
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
        frameId = scheduleFrame(animate);
      }
    };

    frameId = scheduleFrame(animate);
    return () => {
      if (frameId != null) {
        if (hasRaf) {
          globalThis.cancelAnimationFrame(frameId as number);
        } else {
          globalThis.clearTimeout(frameId as ReturnType<typeof globalThis.setTimeout>);
        }
      }
    };
  }, [progressPercent]);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">Coverage / analysis orb</p>
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
              transform: active
                ? `scale(${1 + (isAnimating ? elapsedFactor / 1000 : 0)})`
                : "scale(1)",
              boxShadow: getOrbCoreShadow(phase),
            }}
          />
          <div className="relative h-full w-full rounded-full" aria-hidden="true" />
        </div>
        <div className="min-w-0 flex-1 space-y-3">
          <p className="text-sm text-zinc-200">{subtitle}</p>
          <div className="flex flex-wrap gap-2">
            <Badge tone={active ? "success" : "neutral"}>
              {active ? "analysis alive" : "analysis idle"}
            </Badge>
            <Badge tone={phaseTone}>{phaseLabel}</Badge>
            <Badge tone="neutral">{formatCount(Math.round(elapsedMs))} ms</Badge>
            <Badge tone={firstChunkMs != null ? "success" : "neutral"}>
              first chunk{" "}
              {firstChunkMs != null ? `${formatCount(Math.round(firstChunkMs))} ms` : "n/a"}
            </Badge>
            <Badge tone={intensity > 0 ? "warning" : "neutral"}>
              intensity {formatCount(Math.round(intensity))}%
            </Badge>
          </div>
          <div className="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
            <div className="flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
              <span>Coverage</span>
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
              <span>Analysis</span>
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
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">Trace</p>
                <p className="mt-1 font-mono text-xs text-white">
                  {traceId ? shortenTraceId(traceId) : "no trace"}
                </p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">Steps</p>
                <p className="mt-1 font-mono text-xs text-white">{formatCount(stepCount)}</p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">First chunk</p>
                <p className="mt-1 font-mono text-xs text-white">
                  {firstChunkMs != null ? `${firstChunkMs.toFixed(1)} ms` : "n/a"}
                </p>
              </div>
              <div className="rounded-lg border border-white/5 bg-white/5 px-2 py-1.5">
                <p className="text-[10px] uppercase tracking-wide text-zinc-500">Rate</p>
                <p className="mt-1 font-mono text-xs text-white">
                  {charsPerSecond != null ? `${charsPerSecond.toFixed(1)} chars/s` : "n/a"}
                </p>
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

function renderManagerMetricsBadge(available: boolean): string {
  return available ? "manager metrics on" : "manager metrics off";
}

function renderProcessFirstChunkLabel(firstChunkMs: number | null | undefined): string {
  if (firstChunkMs != null) {
    return `${firstChunkMs.toFixed(1)} ms`;
  }
  return "n/a";
}

export function AnalysisResultsPanel(props: AnalysisResultsPanelProps) {
  const {
    analysisStreaming,
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
    waitingTokenLabel,
    streamingLabel,
    resultsAnswerLabel,
    resultsHighlightsLabel,
    highlightsEmptyLabel,
    resultsVerdictLabel,
    resultsVerdictReady,
    resultsVerdictPending,
  } = props;

  const managerBadgeText = renderManagerMetricsBadge(managerAvailable);

  return (
    <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <p className="text-xs uppercase tracking-wide text-zinc-500">{resultsAnswerLabel}</p>
          <div className="flex flex-wrap items-center gap-2">
            {analysisStreaming && <Badge tone="warning">typing...</Badge>}
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
              {analysisResponse ? "presented" : "awaiting data"}
            </Badge>
            <Badge tone={managerAvailable ? "success" : "warning"}>{managerBadgeText}</Badge>
          </div>
          <p className="mt-3 text-sm text-zinc-300">
            {renderVerdictCopy({
              hasResponse: Boolean(analysisResponse),
              verdictReady: resultsVerdictReady,
              verdictPending: resultsVerdictPending,
            })}
          </p>
        </div>
      </div>
      <div className="space-y-4">
        <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={analysisAnswerTone}>{answerStatusLabel}</Badge>
            <Badge tone={managerAvailable ? "success" : "warning"}>{managerBadgeText}</Badge>
            <Badge tone="neutral">{eventsCount} stream event(s)</Badge>
          </div>
          <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">Analysis process</p>
          <div className="mt-3 space-y-2">
            {analysisTimeline.map((step) => (
              <div key={step.id} className="rounded-xl border border-white/10 bg-black/20 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm text-white">{step.label}</p>
                    <p className="mt-1 text-xs text-zinc-400">{step.detail}</p>
                  </div>
                  <div className="flex items-center gap-2">
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
          <p className="text-xs uppercase tracking-wide text-zinc-500">Process telemetry</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge tone="neutral">trace {analysisProcess?.status ?? "n/a"}</Badge>
            <Badge tone="neutral">trace steps {formatCount(analysisTraceStepCount)}</Badge>
            <Badge tone="neutral">process steps {formatCount(analysisTimelineStepCount)}</Badge>
            <Badge tone={analysisProcess?.first_chunk_ms ? "warning" : "neutral"}>
              first chunk {renderProcessFirstChunkLabel(analysisProcess?.first_chunk_ms)}
            </Badge>
            <Badge tone="neutral">chunks {analysisProcess?.response_chunks ?? chunkCount}</Badge>
            <Badge tone="neutral">chars {analysisProcess?.response_chars ?? responseChars}</Badge>
            <Badge tone={analysisProcess?.response_truncated ? "warning" : "success"}>
              {analysisProcess?.response_truncated ? "response truncated" : "response complete"}
            </Badge>
            <Badge tone={analysisProcess?.prompt_trimmed ? "warning" : "success"}>
              {analysisProcess?.prompt_trimmed ? "prompt trimmed" : "prompt intact"}
            </Badge>
            <Badge tone={analysisProcess?.context_preview_truncated ? "warning" : "success"}>
              {analysisProcess?.context_preview_truncated ? "context truncated" : "context intact"}
            </Badge>
          </div>
          {analysisProcess && (
            <>
              <p className="mt-3 text-xs uppercase tracking-wide text-zinc-500">
                Request {shortenTraceId(analysisProcess.request_id)}
              </p>
              {analysisProcess.steps.length > 0 && (
                <div className="mt-3 space-y-2">
                  {analysisProcess.steps.slice(0, 4).map((step, index) => (
                    <div
                      key={`${step.action ?? "step"}-${index}`}
                      className="rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-300"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-zinc-100">
                          {step.component ?? "step"}.{step.action ?? "unknown"}
                        </span>
                        <span className="uppercase tracking-wide text-zinc-500">
                          {step.status ?? "ok"}
                        </span>
                      </div>
                      <p className="mt-1 text-zinc-400">{step.details ?? "No details"}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
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
  selectedGraphNode:
    | { id: string; label: string; kind: string; status: string }
    | null;
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
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-5">
      <div className="space-y-1">
        <p className="text-[11px] uppercase tracking-wide text-zinc-500">{"// graph"}</p>
        <h3 className="text-lg font-semibold text-white">{title}</h3>
        <p className="text-sm text-zinc-300">{description}</p>
      </div>
      <div className="mt-4 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">nodes {formatCount(snapshot.graph?.summary.nodes ?? 0)}</Badge>
          <Badge tone="neutral">edges {formatCount(snapshot.graph?.summary.edges ?? 0)}</Badge>
          <Badge tone="success">available {formatCount(snapshot.graph?.summary.available_packages ?? 0)}</Badge>
          <Badge tone="warning">missing {formatCount(snapshot.graph?.summary.missing_packages ?? 0)}</Badge>
          <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
            drift issues {formatCount(snapshot.graph?.summary.drift_issues ?? 0)}
          </Badge>
        </div>
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

        {graphViewOpen && (
          <>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {(snapshot.graph?.nodes ?? []).map((node) => (
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
            <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Relations</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {(snapshot.graph?.edges ?? []).map((edge) => (
                    <Badge key={`${edge.from}-${edge.to}-${edge.label}`} tone="neutral">
                      {edge.from} → {edge.to} ({edge.label})
                    </Badge>
                  ))}
                </div>
                <div className="mt-4 rounded-xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-300">
                  Click any node to open the drilldown panel on the right. Package and reuse nodes
                  are treated the same way as runtime nodes so the graph stays uniform.
                </div>
              </div>
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
            </div>
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
                  packages {formatCount(snapshot.available_packages.length)}/
                  {formatCount(snapshot.available_packages.length + snapshot.missing_packages.length)}
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
                  <p className="mt-1 font-mono text-sm text-white">
                    {(snapshot.graph?.nodes ?? []).filter((node) => node.kind === "analysis").length}
                  </p>
                </div>
                <div className="rounded-xl border border-white/10 bg-black/20 px-4 py-3">
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">Relations</p>
                  <p className="mt-1 font-mono text-sm text-white">
                    {formatCount(snapshot.graph?.summary.edges ?? 0)} edges
                  </p>
                </div>
              </div>
              <p className="mt-3 text-sm text-zinc-300">
                Graph data is derived from the same snapshot as the runtime view, so the graph stays
                lightweight while still reflecting active model, diagnostics reuse, package coverage and drift state.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

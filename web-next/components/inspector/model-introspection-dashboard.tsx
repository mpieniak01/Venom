"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Brain, RefreshCcw, Radar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { getServerApiBaseUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";
import { useModelIntrospectionMechanism } from "@/components/inspector/model-introspection-mechanism";

type PackageProbe = {
  module: string;
  package: string;
  available: boolean;
  version: string | null;
};

type IntrospectionSnapshot = {
  runtime: {
    provider: string;
    model: string;
    endpoint: string | null;
    service_type: string;
    mode: string;
    label: string;
    config_hash: string | null;
    runtime_id: string | null;
  };
  runtime_drift: {
    drift_detected: boolean;
    active_server: string;
    inferred_provider: string;
    model_name: string;
    endpoint: string;
    issues: string[];
  };
  packages: Record<string, PackageProbe>;
  available_packages: string[];
  missing_packages: string[];
  model_manager: {
    available: boolean;
    usage_metrics: Record<string, unknown> | null;
    error: string | null;
  };
  reuse: {
    brain: {
      path: string;
      available: boolean;
      purpose: string;
    };
    diagnostics: Array<{ id: string; purpose: string }>;
  };
  summary: {
    active_model: string;
    provider: string;
    runtime_label: string;
    introspection_ready: boolean;
  };
  graph?: {
    nodes: Array<{
      id: string;
      label: string;
      kind: string;
      status: string;
    }>;
    edges: Array<{
      from: string;
      to: string;
      label: string;
    }>;
    summary: {
      nodes: number;
      edges: number;
      available_packages: number;
      missing_packages: number;
      drift_issues: number;
    };
  };
};

type SnapshotResponse = {
  success: boolean;
  snapshot: IntrospectionSnapshot;
};

type SnapshotComparison = {
  before: {
    label: string;
    drift: boolean;
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
  after: {
    label: string;
    drift: boolean;
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
  delta: {
    available_packages: number;
    missing_packages: number;
    issues: number;
  };
};

type AnalysisTimelineEntry = {
  id: string;
  label: string;
  status: string;
  detail: string;
  at_ms: number;
  progress?: number;
};

type AnalysisProcessStep = {
  component: string | null;
  action: string | null;
  status: string | null;
  details: string | null;
  elapsed_ms?: number | null;
  chunks?: number | null;
  total_ms?: number | null;
  chars?: number | null;
  truncated?: boolean | null;
  prompt_context_truncated?: boolean | null;
  hidden_prompts_count?: number | null;
  prompt_trimmed?: boolean | null;
};

type AnalysisProcessTrace = {
  request_id: string;
  status: string;
  step_count: number;
  steps: AnalysisProcessStep[];
  first_chunk_ms?: number | null;
  response_chunks?: number | null;
  response_chars?: number | null;
  total_ms?: number | null;
  chars_per_second?: number | null;
  response_truncated?: boolean | null;
  prompt_trimmed?: boolean | null;
  context_preview_truncated?: boolean | null;
  adapter_applied?: boolean | null;
  adapter_id?: string | null;
};

type AnalysisResult = {
  status: string;
  analysis: {
    prompt: string;
    response: string;
    chunk_count: number;
    events: string[];
    timeline: AnalysisTimelineEntry[];
    timeline_step_count?: number;
    elapsed_ms: number;
    provider: string;
    model: string;
    runtime_label: string;
    request_ready_ms?: number;
    response_received_ms?: number;
    snapshot_after_ms?: number;
    process?: AnalysisProcessTrace | null;
  } | null;
  snapshot_after?: IntrospectionSnapshot;
  skipped_reason?: string;
};

function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

function timelineBadgeTone(status: string): "success" | "warning" | "neutral" {
  if (status === "done") return "success";
  if (status === "running") return "warning";
  return "neutral";
}

function splitAnswerHighlights(answer: string): string[] {
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

function parseSseBlock(block: string): { event: string; data: string } | null {
  const trimmed = block.trim();
  if (!trimmed) {
    return null;
  }
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of trimmed.split("\n")) {
    const line = rawLine.trimEnd();
    if (line.startsWith("event:")) {
      event = line.slice(6).trim() || "message";
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trim());
    }
  }
  return { event, data: dataLines.join("\n") };
}

function clampPercent(value: number): number {
  if (Number.isNaN(value) || !Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function shortenTraceId(requestId: string | null | undefined): string {
  if (!requestId) {
    return "—";
  }
  return requestId.length > 8 ? `${requestId.slice(0, 8)}…` : requestId;
}

function AnalysisOrb({
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
}: {
  active: boolean;
  phase: "idle" | "requesting" | "streaming" | "first_chunk" | "completed";
  packageCoverage: number;
  chunks: number;
  elapsedMs: number;
  subtitle: string;
  traceId: string | null;
  firstChunkMs: number | null;
  stepCount: number;
  charsPerSecond: number | null;
  progress: number;
}) {
  const intensity = clampPercent(chunks * 32);
  const elapsedFactor = clampPercent(elapsedMs / 120);
  const packageCoveragePercent = clampPercent(packageCoverage);
  const progressPercent = clampPercent(progress);
  const [displayProgress, setDisplayProgress] = useState(progressPercent);
  const displayProgressRef = useRef(progressPercent);
  const phaseLabel = {
    idle: "idle",
    requesting: "requesting",
    streaming: "streaming",
    first_chunk: "first chunk",
    completed: "completed",
  }[phase];
  const phaseTone =
    phase === "completed"
      ? "success"
      : phase === "streaming" || phase === "first_chunk"
        ? "warning"
        : phase === "requesting"
          ? "neutral"
          : "neutral";
  const phaseColors: Record<
    "idle" | "requesting" | "streaming" | "first_chunk" | "completed",
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
  const colors = phaseColors[phase];
  const packageRingColor =
    packageCoveragePercent >= 100 ? "#047857" : packageCoveragePercent >= 80 ? "#059669" : "#f59e0b";
  const isAnimating = active && phase !== "completed";

  useEffect(() => {
    displayProgressRef.current = displayProgress;
  }, [displayProgress]);

  useEffect(() => {
    const scheduleFrame =
      typeof window.requestAnimationFrame === "function"
        ? window.requestAnimationFrame.bind(window)
        : (callback: FrameRequestCallback) =>
            window.setTimeout(() => callback(performance.now()), 16);
    const cancelFrame =
      typeof window.cancelAnimationFrame === "function"
        ? window.cancelAnimationFrame.bind(window)
        : (handle: number) => window.clearTimeout(handle);
    let frameId: number | null = null;
    let startAt = 0;
    const startValue = displayProgressRef.current;
    const targetValue = progressPercent;
    const distance = Math.abs(targetValue - startValue);

    if (distance < 0.25) {
      setDisplayProgress(targetValue);
      return;
    }

    const duration = Math.max(240, Math.min(1200, 160 + distance * 9));
    const animate = (timestamp: number) => {
      if (startAt === 0) {
        startAt = timestamp;
      }
      const elapsed = timestamp - startAt;
      const t = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setDisplayProgress(startValue + (targetValue - startValue) * eased);
      if (t < 1) {
        frameId = scheduleFrame(animate) as number;
      }
    };

    frameId = scheduleFrame(animate) as number;
    return () => {
      if (frameId != null) {
        cancelFrame(frameId);
      }
    };
  }, [progressPercent]);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">Coverage / analysis orb</p>
      <div className="mt-3 flex items-center gap-4">
        <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full">
          <div
            className="absolute inset-0 rounded-full border-2 border-zinc-800 bg-black shadow-[0_0_0_1px_rgba(0,0,0,0.9),0_0_18px_rgba(0,0,0,0.45)]"
          />
          <div
            className="absolute inset-1.5 rounded-full border border-black bg-black"
          />
          <div
            className={`absolute inset-2.5 rounded-full border-[3px] bg-black ${colors.ring} ${
              isAnimating ? "motion-safe:animate-pulse" : ""
            }`}
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
              boxShadow:
                phase === "completed"
                  ? "0 0 16px rgba(4,120,87,0.26)"
                  : phase === "streaming" || phase === "first_chunk"
                    ? "0 0 18px rgba(6,182,212,0.28)"
                    : phase === "requesting"
                      ? "0 0 18px rgba(245,158,11,0.28)"
                      : "0 0 14px rgba(113,113,122,0.22)",
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
            <Badge tone="neutral">
              {formatCount(Math.round(elapsedMs))} ms
            </Badge>
            <Badge tone={firstChunkMs != null ? "success" : "neutral"}>
              first chunk {firstChunkMs != null ? `${formatCount(Math.round(firstChunkMs))} ms` : "n/a"}
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
                  backgroundColor:
                    phase === "completed"
                      ? "#10b981"
                      : phase === "streaming" || phase === "first_chunk"
                        ? "#06b6d4"
                        : phase === "requesting"
                          ? "#f59e0b"
                          : "#71717a",
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

function GraphNodeCard({
  label,
  kind,
  status,
  selected,
  onClick,
}: {
  label: string;
  kind: string;
  status: string;
  selected: boolean;
  onClick: () => void;
}) {
  const tone =
    status === "available" || status === "connected" || status === "ready"
      ? "success"
      : status === "missing" || status === "offline"
        ? "warning"
        : "neutral";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Select graph node ${label}`}
      className={`rounded-2xl border px-4 py-3 text-left transition ${
        selected
          ? "border-violet-400/60 bg-violet-500/10 shadow-[0_0_0_1px_rgba(139,92,246,0.35)]"
          : "border-white/10 bg-black/20 hover:border-white/20 hover:bg-white/10"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <Badge tone={tone}>{kind}</Badge>
        <span className="text-[11px] uppercase tracking-wide text-zinc-500">{status}</span>
      </div>
      <p className="mt-3 font-mono text-sm text-white">{label}</p>
    </button>
  );
}

export function ModelIntrospectionDashboard() {
  const t = useTranslation();
  const { enabled: analysisMechanismEnabled } = useModelIntrospectionMechanism();
  const [snapshot, setSnapshot] = useState<IntrospectionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analysisPrompt, setAnalysisPrompt] = useState("Co to jest slonce?");
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [selectedGraphNodeId, setSelectedGraphNodeId] = useState<string | null>(null);
  const [graphViewOpen, setGraphViewOpen] = useState(false);

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${getServerApiBaseUrl()}/api/v1/models/introspection`, {
        cache: "no-store",
      });
      const data = (await response.json()) as SnapshotResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(
          typeof data === "object" && data && "detail" in data
            ? String(data.detail ?? "Request failed")
            : "Request failed",
        );
      }
      setSnapshot(data.snapshot);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Request failed");
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSnapshot();
  }, [loadSnapshot]);

  const stats = useMemo(() => {
    const packages = snapshot?.packages ?? {};
    const availableCount = snapshot?.available_packages.length ?? 0;
    const missingCount = snapshot?.missing_packages.length ?? 0;
    const driftCount = snapshot?.runtime_drift.issues.length ?? 0;
    return [
      {
        label: t("inspector.modelIntrospection.summary.runtime"),
        value: snapshot?.summary.runtime_label ?? "—",
        hint: snapshot?.summary.provider ?? "—",
        accent: "violet" as const,
      },
      {
        label: t("inspector.modelIntrospection.summary.packages"),
        value: formatCount(availableCount),
        hint: `${formatCount(Object.keys(packages).length)} total`,
        accent: "green" as const,
      },
      {
        label: t("inspector.modelIntrospection.summary.missing"),
        value: formatCount(missingCount),
        hint: snapshot?.runtime_drift.drift_detected ? `${driftCount} drift issue(s)` : "clean",
        accent: "blue" as const,
      },
      {
        label: "ModelManager",
        value: snapshot?.model_manager.available ? "connected" : "offline",
        hint: snapshot?.model_manager.error ?? "read-only",
        accent: "indigo" as const,
      },
    ];
  }, [snapshot, t]);

  const analysisVisible = Boolean(analysisResult?.analysis);
  const analysisRunning = analysisResult?.status === "running";
  const analysisActive = analysisResult?.status === "running" || analysisResult?.status === "completed";
  const analysisCompleted = analysisResult?.status === "completed" && analysisVisible;

  const analysisComparison = useMemo<SnapshotComparison | null>(() => {
    if (!snapshot || !analysisCompleted) {
      return null;
    }
    const before = snapshot;
    const after = analysisResult.snapshot_after ?? snapshot;
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
        missing_packages: after.missing_packages.length - before.missing_packages.length,
        issues: after.runtime_drift.issues.length - before.runtime_drift.issues.length,
      },
    };
  }, [analysisCompleted, analysisResult?.snapshot_after, snapshot]);

  const analysisHighlights = useMemo(() => {
    return splitAnswerHighlights(analysisVisible ? analysisResult?.analysis?.response ?? "" : "");
  }, [analysisResult?.analysis?.response, analysisVisible]);

  const analysisTimeline = useMemo(() => {
    return analysisVisible ? analysisResult?.analysis?.timeline ?? [] : [];
  }, [analysisResult?.analysis?.timeline, analysisVisible]);

  const analysisResponse = analysisResult?.analysis?.response ?? "";
  const analysisProcess = analysisResult?.analysis?.process ?? null;
  const analysisTimelineStepCount =
    analysisResult?.analysis?.timeline_step_count ?? analysisTimeline.length ?? 0;
  const analysisTraceStepCount = analysisProcess?.trace_step_count ?? analysisProcess?.step_count ?? 0;
  const analysisTimelineFirstChunk = analysisTimeline.find((entry) => entry.id === "first_chunk") ?? null;
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
  const analysisPhase: "idle" | "requesting" | "streaming" | "first_chunk" | "completed" = !analysisVisible
    ? analysisLoading
      ? "requesting"
      : "idle"
    : analysisResult?.status === "completed" || analysisTimelineResponseFinalized != null
      ? "completed"
    : analysisRunning
      ? analysisResult?.analysis?.chunk_count
        ? "streaming"
        : "requesting"
      : analysisFirstChunkMs != null
        ? "first_chunk"
      : analysisResult?.analysis?.chunk_count
          ? "first_chunk"
          : "idle";
  const analysisAnswerTone =
    !analysisVisible || !analysisResponse
      ? "neutral"
      : /potrzebuj|need more context|more context/i.test(analysisResponse)
      ? "warning"
      : "success";

  const visualMetrics = useMemo(() => {
    const available = snapshot?.available_packages.length ?? 0;
    const missing = snapshot?.missing_packages.length ?? 0;
    const total = available + missing;
    const packageCoverage = total > 0 ? (available / total) * 100 : 0;
    const driftIntensity = total > 0 ? (snapshot?.runtime_drift.issues.length ?? 0) / total : 0;
    const analysisProgress = analysisVisible
      ? analysisTimelineProgress > 0
        ? clampPercent(analysisTimelineProgress)
        : clampPercent(
            Math.min(
              100,
              (analysisStepCount ?? analysisResult?.analysis?.chunk_count ?? 0) * 18 +
                (analysisProcess?.first_chunk_ms != null ? 20 : 0),
            ),
          )
      : 0;
    return {
      packageCoverage,
      driftIntensity: clampPercent(driftIntensity * 100),
      analysisProgress,
    };
  }, [analysisResult?.analysis, analysisVisible, analysisStepCount, analysisTimelineProgress, analysisProcess?.first_chunk_ms, snapshot]);

  useEffect(() => {
    const firstGraphNodeId = snapshot?.graph?.nodes?.[0]?.id ?? null;
    setSelectedGraphNodeId((current) => {
      if (!snapshot?.graph?.nodes?.length) {
        return null;
      }
      if (current && snapshot.graph.nodes.some((node) => node.id === current)) {
        return current;
      }
      return firstGraphNodeId;
    });
  }, [snapshot?.graph?.nodes]);

  const selectedGraphNode = useMemo(() => {
    if (!snapshot?.graph?.nodes?.length || !selectedGraphNodeId) {
      return null;
    }
    return snapshot.graph.nodes.find((node) => node.id === selectedGraphNodeId) ?? null;
  }, [selectedGraphNodeId, snapshot?.graph?.nodes]);

  const selectedGraphNodeDetails = useMemo(() => {
    if (!snapshot || !selectedGraphNode) {
      return null;
    }
    switch (selectedGraphNode.id) {
      case "runtime":
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
      case "model":
        return {
          title: "Model details",
          lines: [
            `Active model: ${snapshot.summary.active_model}`,
            `Runtime label: ${snapshot.summary.runtime_label}`,
            `Drift issues: ${snapshot.runtime_drift.issues.length}`,
          ],
        };
      case "analysis":
        return {
          title: "Analysis details",
          lines: [
            `Mechanism: ${analysisMechanismEnabled ? "enabled" : "disabled"}`,
            `Status: ${analysisResult?.status ?? "idle"}`,
            `Content chunks: ${analysisVisible ? analysisResult?.analysis?.chunk_count ?? 0 : 0}`,
            `Elapsed: ${analysisVisible ? `${(analysisResult?.analysis?.elapsed_ms ?? 0).toFixed(1)} ms` : "—"}`,
          ],
        };
      case "manager":
        return {
          title: "ModelManager details",
          lines: [
            `Available: ${snapshot.model_manager.available ? "yes" : "no"}`,
            `Metrics: ${snapshot.model_manager.usage_metrics ? "present" : "absent"}`,
            `Error: ${snapshot.model_manager.error ?? "—"}`,
          ],
        };
      case "brain":
        return {
          title: "Reuse details",
          lines: [
            `Path: ${snapshot.reuse.brain.path}`,
            `Available: ${snapshot.reuse.brain.available ? "yes" : "no"}`,
            `Purpose: ${snapshot.reuse.brain.purpose}`,
          ],
        };
      case "diagnostics":
        return {
          title: "Diagnostics reuse",
          lines: snapshot.reuse.diagnostics.map(
            (entry) => `${entry.id}: ${entry.purpose}`,
          ),
        };
      default: {
        const packageNode = snapshot.packages[selectedGraphNode.id.replace("package:", "")];
        return {
          title: "Package details",
          lines: packageNode
            ? [
                `Package: ${packageNode.package}`,
                `Module: ${packageNode.module}`,
                `Available: ${packageNode.available ? "yes" : "no"}`,
                `Version: ${packageNode.version ?? "n/a"}`,
              ]
            : [
                `Node: ${selectedGraphNode.label}`,
                `Status: ${selectedGraphNode.status}`,
              ],
        };
      }
    }
  }, [analysisMechanismEnabled, analysisResult?.analysis, analysisVisible, selectedGraphNode, snapshot]);

  const runAnalysis = useCallback(async () => {
    if (!analysisPrompt.trim()) {
      setAnalysisError("Prompt cannot be empty.");
      return;
    }
    setAnalysisLoading(true);
    setAnalysisError(null);
    setAnalysisResult(null);
    try {
      const response = await fetch(
        `${getServerApiBaseUrl()}/api/v1/models/introspection/analyze/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            prompt: analysisPrompt,
            live_analysis_enabled: analysisMechanismEnabled,
            max_tokens: 128,
            temperature: 0.2,
          }),
        },
      );
      if (!response.ok) {
        const errorBody = await response.text();
        let message = errorBody || "Analysis failed";
        try {
          const parsed = JSON.parse(errorBody) as { detail?: string };
          message = parsed.detail ?? message;
        } catch {
          // fall back to raw body
        }
        throw new Error(message);
      }
      if (!response.body) {
        throw new Error("Streaming response unavailable.");
      }
      const decoder = new TextDecoder();
      const streamStartedAt = performance.now();
      let buffer = "";
      let liveResult: AnalysisResult | null = null;
      let sawFirstChunk = false;
      const pushAnalysisResult = (nextResult: AnalysisResult) => {
        liveResult = nextResult;
        setAnalysisResult(nextResult);
      };
      const updatePartialAnalysis = (
        updater: (analysis: NonNullable<AnalysisResult["analysis"]>) => NonNullable<AnalysisResult["analysis"]>,
      ) => {
        if (!liveResult?.analysis) {
          return;
        }
        liveResult = {
          ...liveResult,
          analysis: updater(liveResult.analysis),
        };
        setAnalysisResult(liveResult);
      };
      const handleEvent = (eventName: string, dataText: string) => {
        if (eventName === "analysis_start" || eventName === "analysis_done") {
          const parsed = JSON.parse(dataText) as AnalysisResult;
          pushAnalysisResult(parsed);
          return;
        }
        if (!liveResult?.analysis) {
          return;
        }
        if (eventName === "error") {
          throw new Error(dataText || "Analysis stream failed");
        }
        if (eventName === "start") {
          updatePartialAnalysis((analysis) => ({
            ...analysis,
            events: analysis.events.includes("start")
              ? analysis.events
              : [...analysis.events, "start"],
          }));
          return;
        }
        if (eventName === "content") {
          const payload = dataText ? (JSON.parse(dataText) as { text?: string }) : {};
          const text = String(payload.text ?? "");
          if (!text) {
            return;
          }
          updatePartialAnalysis((analysis) => {
            const nextTimeline = [...analysis.timeline];
            const nextChunkCount = analysis.chunk_count + 1;
            const nowMs = performance.now() - streamStartedAt;
            if (!sawFirstChunk) {
              sawFirstChunk = true;
              nextTimeline.push({
                id: "first_chunk",
                label: "First content chunk",
                status: "done",
                detail: `${nextChunkCount} chunk(s) total`,
                at_ms: nowMs,
                progress: 40,
              });
            }
            return {
              ...analysis,
              response: `${analysis.response}${text}`,
              chunk_count: nextChunkCount,
              events: [...analysis.events, "content"],
              timeline: nextTimeline,
              elapsed_ms: nowMs,
            };
          });
          return;
        }
        if (eventName === "done") {
          updatePartialAnalysis((analysis) => {
            const nextTimeline = [...analysis.timeline];
            if (!nextTimeline.some((entry) => entry.id === "response_finalized")) {
              nextTimeline.push({
                id: "response_finalized",
                label: "Response assembled",
                status: "done",
                detail: `${analysis.response.length} chars`,
                at_ms: performance.now() - streamStartedAt,
                progress: 90,
              });
            }
            return {
              ...analysis,
              events: [...analysis.events, "done"],
              timeline: nextTimeline,
              elapsed_ms: performance.now() - streamStartedAt,
            };
          });
        }
      };
      const reader = response.body.getReader();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            break;
          }
          buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
          let separatorIndex = buffer.indexOf("\n\n");
          while (separatorIndex !== -1) {
            const block = buffer.slice(0, separatorIndex);
            buffer = buffer.slice(separatorIndex + 2);
            const parsed = parseSseBlock(block);
            if (parsed) {
              handleEvent(parsed.event, parsed.data);
            }
            separatorIndex = buffer.indexOf("\n\n");
          }
        }
        buffer += decoder.decode().replace(/\r\n/g, "\n");
        const tail = parseSseBlock(buffer);
        if (tail) {
          handleEvent(tail.event, tail.data);
        }
      } finally {
        reader.releaseLock();
      }
    } catch (analysisRunError) {
      setAnalysisError(
        analysisRunError instanceof Error
          ? analysisRunError.message
          : "Analysis failed",
      );
      setAnalysisResult(null);
    } finally {
      setAnalysisLoading(false);
    }
  }, [analysisMechanismEnabled, analysisPrompt]);

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
            <Button variant="outline" onClick={() => void loadSnapshot()} disabled={loading}>
              <RefreshCcw className="h-4 w-4" />
              {loading
                ? t("common.loading")
                : t("inspector.modelIntrospection.actions.refresh")}
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
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs uppercase tracking-wide text-zinc-500" htmlFor="model-introspection-prompt">
                  {t("inspector.modelIntrospection.dashboard.analysis.promptLabel")}
                </label>
                <textarea
                  id="model-introspection-prompt"
                  value={analysisPrompt}
                  onChange={(event) => setAnalysisPrompt(event.target.value)}
                  className="min-h-28 w-full rounded-2xl border border-white/10 bg-black/30 px-4 py-3 font-mono text-sm text-white outline-none transition focus:border-violet-400/60"
                  placeholder={t("inspector.modelIntrospection.dashboard.analysis.promptPlaceholder")}
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  onClick={() => void runAnalysis()}
                  disabled={analysisLoading || !snapshot || !analysisMechanismEnabled}
                >
                  {analysisLoading
                    ? t("inspector.modelIntrospection.dashboard.analysis.running")
                    : t("inspector.modelIntrospection.dashboard.analysis.run")}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setAnalysisPrompt("Co to jest slonce?")}
                  disabled={analysisLoading}
                >
                  {t("inspector.modelIntrospection.dashboard.analysis.reset")}
                </Button>
              </div>
              {!analysisMechanismEnabled && (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-300">
                  {t("inspector.modelIntrospection.dashboard.analysis.disabled")}
                </div>
              )}
              {analysisError && (
                <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  {analysisError}
                </div>
              )}
              {analysisResult?.status === "skipped" && (
                <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-zinc-300">
                  {t("inspector.modelIntrospection.dashboard.analysis.skipped")}
                </div>
              )}
            </div>
            <div className="space-y-4">
              <AnalysisOrb
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
                subtitle={
                  analysisResult?.status === "completed"
                      ? `${analysisResult?.analysis?.chunk_count ?? 0} chunk(s) · ${analysisStepCount} step(s) · completed`
                    : analysisActive
                      ? `${analysisResult?.analysis?.chunk_count ?? 0} chunk(s) · ${analysisStepCount} step(s)`
                      : t("inspector.modelIntrospection.dashboard.analysis.orbIdle")
                }
              />
            </div>
          </div>
        </Panel>
      )}

      {analysisVisible && analysisResult.analysis && (
        <Panel
          eyebrow="// results"
          title={t("inspector.modelIntrospection.dashboard.results.title")}
          description={t("inspector.modelIntrospection.dashboard.results.description")}
        >
          <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.results.answer")}</p>
                <div className="flex flex-wrap items-center gap-2">
                  {analysisStreaming && <Badge tone="warning">typing...</Badge>}
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm text-zinc-200">
                  {analysisResult.analysis.response || t("inspector.modelIntrospection.dashboard.results.waitingToken")}
                  {analysisStreaming && (
                    <span
                      aria-hidden="true"
                      className="ml-1 inline-block h-4 w-[2px] translate-y-[2px] animate-pulse bg-cyan-300"
                    />
                  )}
                </p>
                {analysisStreaming && (
                  <p className="mt-2 text-xs uppercase tracking-wide text-cyan-200/80">
                    {t("inspector.modelIntrospection.dashboard.results.streaming")}
                  </p>
                )}
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.results.highlights")}</p>
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
                    <p className="text-sm text-zinc-400">{t("inspector.modelIntrospection.dashboard.results.highlightsEmpty")}</p>
                  )}
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.results.verdict")}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Badge tone={analysisAnswerTone}>
                    {analysisResult.analysis.response ? "presented" : "awaiting data"}
                  </Badge>
                  <Badge tone={snapshot.model_manager.available ? "success" : "warning"}>
                    {snapshot.model_manager.available ? "manager metrics on" : "manager metrics off"}
                  </Badge>
                </div>
                <p className="mt-3 text-sm text-zinc-300">
                  {analysisResult.analysis
                    ? t("inspector.modelIntrospection.dashboard.results.verdictReady")
                    : t("inspector.modelIntrospection.dashboard.results.verdictPending")}
                </p>
              </div>
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={analysisAnswerTone}>
                    {analysisResult?.analysis?.response
                      ? "model answered"
                      : analysisRunning
                        ? "streaming answer"
                        : "awaiting answer"}
                  </Badge>
                  <Badge tone={snapshot.model_manager.available ? "success" : "warning"}>
                    {snapshot.model_manager.available ? "manager metrics on" : "manager metrics off"}
                  </Badge>
                  <Badge tone="neutral">
                    {analysisResult?.analysis?.events.length ?? 0} stream event(s)
                  </Badge>
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
                <div className="mt-4 flex flex-wrap gap-2">
                  {analysisResult?.analysis?.events.length ? (
                    analysisResult.analysis.events.slice(0, 6).map((event, index) => (
                      <Badge key={`${event}-${index}`} tone="neutral">
                        {event}
                      </Badge>
                    ))
                  ) : (
                    <Badge tone="neutral">no stream events</Badge>
                  )}
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">Process telemetry</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Badge tone="neutral">trace {analysisProcess?.status ?? "n/a"}</Badge>
                  <Badge tone="neutral">trace steps {formatCount(analysisTraceStepCount)}</Badge>
                  <Badge tone="neutral">process steps {formatCount(analysisTimelineStepCount)}</Badge>
                  <Badge tone={analysisProcess?.first_chunk_ms ? "warning" : "neutral"}>
                    first chunk{" "}
                    {analysisProcess?.first_chunk_ms
                      ? `${analysisProcess.first_chunk_ms.toFixed(1)} ms`
                      : "n/a"}
                  </Badge>
                  <Badge tone="neutral">
                    chunks {analysisProcess?.response_chunks ?? analysisResult.analysis.chunk_count}
                  </Badge>
                  <Badge tone="neutral">
                    chars {analysisProcess?.response_chars ?? analysisResult.analysis.response.length}
                  </Badge>
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
        </Panel>
      )}

      {analysisResult?.snapshot_after && (
        <div className="mt-2">
          {analysisComparison ? (
            <div className="mt-6 rounded-2xl border border-white/15 bg-black/25 p-4 shadow-[0_14px_32px_rgba(0,0,0,0.18)]">
              <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.snapshotComparison.title")}</p>
              <div className="mt-3 grid gap-4 xl:grid-cols-3 xl:gap-5">
                <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.snapshotComparison.before")}</p>
                  <p className="mt-2 font-mono text-sm text-white">{analysisComparison.before.label}</p>
                  <p className="mt-2 text-xs text-zinc-400">
                    drift: {analysisComparison.before.drift ? "yes" : "no"} · issues: {analysisComparison.before.issues}
                  </p>
                  <p className="text-xs text-zinc-400">
                    available: {formatCount(analysisComparison.before.available_packages)} · missing: {formatCount(analysisComparison.before.missing_packages)}
                  </p>
                </div>
                <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.snapshotComparison.after")}</p>
                  <p className="mt-2 font-mono text-sm text-white">{analysisComparison.after.label}</p>
                  <p className="mt-2 text-xs text-zinc-400">
                    drift: {analysisComparison.after.drift ? "yes" : "no"} · issues: {analysisComparison.after.issues}
                  </p>
                  <p className="text-xs text-zinc-400">
                    available: {formatCount(analysisComparison.after.available_packages)} · missing: {formatCount(analysisComparison.after.missing_packages)}
                  </p>
                </div>
                <div className="rounded-xl border border-white/12 bg-black/30 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.03),0_10px_24px_rgba(0,0,0,0.18)]">
                  <p className="text-[11px] uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.snapshotComparison.delta")}</p>
                  <p className="mt-2 font-mono text-sm text-white">
                    packages {analysisComparison.delta.available_packages >= 0 ? "+" : ""}
                    {analysisComparison.delta.available_packages}
                  </p>
                  <p className="text-xs text-zinc-400">
                    missing {analysisComparison.delta.missing_packages >= 0 ? "+" : ""}
                    {analysisComparison.delta.missing_packages} · issues{" "}
                    {analysisComparison.delta.issues >= 0 ? "+" : ""}
                    {analysisComparison.delta.issues}
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <p className="mt-2 text-sm text-zinc-300">
              {t("inspector.modelIntrospection.dashboard.snapshotComparison.fallback")}
            </p>
          )}
        </div>
      )}

      {snapshot && (
        <Panel
          eyebrow="// graph"
          title={t("inspector.modelIntrospection.dashboard.graph.title")}
          description={t("inspector.modelIntrospection.dashboard.graph.description")}
        >
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="neutral">
                nodes {formatCount(snapshot.graph?.summary.nodes ?? 0)}
              </Badge>
              <Badge tone="neutral">
                edges {formatCount(snapshot.graph?.summary.edges ?? 0)}
              </Badge>
              <Badge tone="success">
                available {formatCount(snapshot.graph?.summary.available_packages ?? 0)}
              </Badge>
              <Badge tone="warning">
                missing {formatCount(snapshot.graph?.summary.missing_packages ?? 0)}
              </Badge>
              <Badge tone={snapshot.runtime_drift.drift_detected ? "warning" : "success"}>
                drift issues {formatCount(snapshot.graph?.summary.drift_issues ?? 0)}
              </Badge>
            </div>
            <button
              type="button"
              onClick={() => setGraphViewOpen((current) => !current)}
              aria-expanded={graphViewOpen}
              className="flex w-full items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-left transition hover:border-white/20 hover:bg-white/10"
            >
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">{t("inspector.modelIntrospection.dashboard.graph.drilldownTitle")}</p>
                <p className="mt-1 text-sm text-zinc-200">
                  {graphViewOpen
                    ? t("inspector.modelIntrospection.dashboard.graph.hide")
                    : t("inspector.modelIntrospection.dashboard.graph.open")}
                </p>
              </div>
              <Badge tone={graphViewOpen ? "success" : "neutral"}>
                {graphViewOpen
                  ? t("inspector.modelIntrospection.dashboard.graph.stateOpen")
                  : t("inspector.modelIntrospection.dashboard.graph.stateCollapsed")}
              </Badge>
            </button>

            {graphViewOpen ? (
              <>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {(snapshot.graph?.nodes ?? []).map((node) => (
                    <GraphNodeCard
                      key={node.id}
                      label={node.label}
                      kind={node.kind}
                      status={node.status}
                      selected={selectedGraphNodeId === node.id}
                      onClick={() => setSelectedGraphNodeId(node.id)}
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
                      <p className="text-xs uppercase tracking-wide text-zinc-500">
                        Graph drilldown
                      </p>
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
                          <p className="mt-1 text-sm text-zinc-300">
                            {selectedGraphNode.kind === "package"
                              ? "Package drilldown uses the same snapshot as runtime health, so it is safe to inspect without triggering extra probes."
                              : selectedGraphNode.kind === "reuse"
                              ? "Reuse drilldown helps confirm that Brain and diagnostics stay shared rather than duplicated."
                              : "Runtime drilldown summarizes the active runtime, model and analysis attachment points."}
                          </p>
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
                  <Badge tone="neutral">
                    runtime {snapshot.summary.runtime_label}
                  </Badge>
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
            ) : null}
          </div>
        </Panel>
      )}

    </div>
  );
}

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
  GraphNodeDetails,
  IntrospectionSnapshot,
  SnapshotComparison,
} from "@/components/inspector/model-introspection-dashboard-types";
import {
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

function buildSummaryCards(args: {
  snapshot: IntrospectionSnapshot;
  t: (key: string) => string;
}): SummaryCard[] {
  const { snapshot, t } = args;
  const packages = snapshot.packages;
  const availableCount = snapshot.available_packages.length;
  const missingCount = snapshot.missing_packages.length;
  const driftCount = snapshot.runtime_drift.issues.length;
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
        : "clean",
      accent: "blue",
    },
    {
      label: "ModelManager",
      value: snapshot.model_manager.available ? "connected" : "offline",
      hint: snapshot.model_manager.error ?? "read-only",
      accent: "indigo",
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
  const [graphViewOpen, setGraphViewOpen] = useState(false);

  const stats = useMemo(() => {
    if (!snapshot) {
      return [] as SummaryCard[];
    }
    return buildSummaryCards({ snapshot, t });
  }, [snapshot, t]);

  const analysisVisible = Boolean(analysisResult?.analysis);
  const analysisRunning = analysisResult?.status === "running";
  const analysisActive =
    analysisResult?.status === "running" || analysisResult?.status === "completed";
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
  const analysisTimeline = analysisVisible ? analysisResult?.analysis?.timeline ?? [] : [];
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

  const visualMetrics = useMemo(() => {
    const available = snapshot?.available_packages.length ?? 0;
    const missing = snapshot?.missing_packages.length ?? 0;
    const total = available + missing;
    const packageCoverage = total > 0 ? (available / total) * 100 : 0;
    const analysisProgress = computeAnalysisProgress({
      analysisVisible,
      analysisTimelineProgress,
      analysisStepCount,
      chunkCount: analysisResult?.analysis?.chunk_count ?? 0,
      firstChunkMs: analysisProcess?.first_chunk_ms,
      elapsedMs: analysisResult?.analysis?.elapsed_ms ?? 0,
      analysisStatus: analysisResult?.status,
    });
    return {
      packageCoverage,
      analysisProgress,
    };
  }, [
    analysisProcess?.first_chunk_ms,
    analysisResult?.analysis,
    analysisResult?.status,
    analysisStepCount,
    analysisTimelineProgress,
    analysisVisible,
    snapshot?.available_packages.length,
    snapshot?.missing_packages.length,
  ]);

  const selectedGraphNodeIdEffective = useMemo(() => {
    const nodes = snapshot?.graph?.nodes ?? [];
    if (nodes.length === 0) {
      return null;
    }
    const currentExists = Boolean(
      selectedGraphNodeId && nodes.some((node) => node.id === selectedGraphNodeId),
    );
    if (currentExists) {
      return selectedGraphNodeId;
    }
    return nodes[0]?.id ?? null;
  }, [selectedGraphNodeId, snapshot?.graph?.nodes]);

  const selectedGraphNode = useMemo(() => {
    const nodes = snapshot?.graph?.nodes ?? [];
    if (nodes.length === 0 || !selectedGraphNodeIdEffective) {
      return null;
    }
    return nodes.find((node) => node.id === selectedGraphNodeIdEffective) ?? null;
  }, [selectedGraphNodeIdEffective, snapshot?.graph?.nodes]);

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

  const selectedGraphTypeHint = useMemo(() => {
    if (!selectedGraphNode) {
      return "";
    }
    return getTypeHintText(selectedGraphNode.kind);
  }, [selectedGraphNode]);

  const handleRefreshSnapshot = useCallback(() => {
    loadSnapshot().catch(() => undefined);
  }, [loadSnapshot]);

  const handleRunAnalysis = useCallback(() => {
    runAnalysis().catch(() => undefined);
  }, [runAnalysis]);

  const handleResetPrompt = useCallback(() => {
    setAnalysisPrompt("Co to jest slonce?");
  }, []);

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

      {stats.length > 0 && (
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
      )}

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
                })}
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
          <AnalysisResultsPanel
            analysisStreaming={analysisStreaming}
            analysisResponse={analysisResponse}
            analysisHighlights={analysisHighlights}
            answerStatusLabel={getAnswerStatusLabel({
              response: analysisResponse,
              analysisRunning,
            })}
            analysisAnswerTone={analysisAnswerTone}
            managerAvailable={snapshot.model_manager.available}
            eventsCount={analysisResult.analysis.events.length}
            analysisTimeline={analysisTimeline}
            analysisProcess={analysisProcess}
            analysisTraceStepCount={analysisTraceStepCount}
            analysisTimelineStepCount={analysisTimelineStepCount}
            responseChars={analysisResponse.length}
            chunkCount={analysisResult.analysis.chunk_count}
            waitingTokenLabel={t("inspector.modelIntrospection.dashboard.results.waitingToken")}
            streamingLabel={t("inspector.modelIntrospection.dashboard.results.streaming")}
            resultsAnswerLabel={t("inspector.modelIntrospection.dashboard.results.answer")}
            resultsHighlightsLabel={t("inspector.modelIntrospection.dashboard.results.highlights")}
            highlightsEmptyLabel={t("inspector.modelIntrospection.dashboard.results.highlightsEmpty")}
            resultsVerdictLabel={t("inspector.modelIntrospection.dashboard.results.verdict")}
            resultsVerdictReady={t("inspector.modelIntrospection.dashboard.results.verdictReady")}
            resultsVerdictPending={t("inspector.modelIntrospection.dashboard.results.verdictPending")}
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

      {snapshot && (
        <GraphPanel
          snapshot={snapshot}
          analysisActive={analysisActive}
          graphViewOpen={graphViewOpen}
          onToggleGraphView={() => setGraphViewOpen((current) => !current)}
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
      )}
    </div>
  );
}

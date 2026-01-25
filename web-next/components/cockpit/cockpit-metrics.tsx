"use client";

import { CockpitKpiSection } from "@/components/cockpit/cockpit-kpi-section";
import { CockpitTelemetryPanel } from "@/components/cockpit/cockpit-telemetry-panel";
import type { TelemetryFeedEntry } from "@/components/cockpit/cockpit-utils";
import type { TokenSample } from "@/components/cockpit/token-types";

type QueueSnapshot = {
  active?: number | null;
  limit?: number | string | null;
};

type CockpitMetricsProps = {
  metrics: Record<string, unknown> | null;
  metricsLoading: boolean;
  successRate: number | null;
  tasksCreated: number;
  queue: QueueSnapshot | null;
  feedbackScore: number | null;
  feedbackUp: number;
  feedbackDown: number;
  tokenMetricsLoading: boolean;
  tokenSplits: { label: string; value: number }[];
  tokenHistory: TokenSample[];
  tokenTrendDelta: number | null;
  tokenTrendLabel: string;
  totalTokens: number | string;
  showReferenceSections: boolean;
  telemetryFeed: TelemetryFeedEntry[];
};

export function CockpitMetrics({
  metrics,
  metricsLoading,
  successRate,
  tasksCreated,
  queue,
  feedbackScore,
  feedbackUp,
  feedbackDown,
  tokenMetricsLoading,
  tokenSplits,
  tokenHistory,
  tokenTrendDelta,
  tokenTrendLabel,
  totalTokens,
  showReferenceSections,
  telemetryFeed,
}: CockpitMetricsProps) {
  return (
    <>
      <CockpitKpiSection
        metrics={metrics}
        metricsLoading={metricsLoading}
        successRate={successRate}
        tasksCreated={tasksCreated}
        queue={queue}
        feedbackScore={feedbackScore}
        feedbackUp={feedbackUp}
        feedbackDown={feedbackDown}
        tokenMetricsLoading={tokenMetricsLoading}
        tokenSplits={tokenSplits}
        tokenHistory={tokenHistory}
        tokenTrendDelta={tokenTrendDelta}
        tokenTrendLabel={tokenTrendLabel}
        totalTokens={totalTokens}
        showReferenceSections={showReferenceSections}
      />
      {showReferenceSections && (
        <CockpitTelemetryPanel telemetryFeed={telemetryFeed} />
      )}
    </>
  );
}

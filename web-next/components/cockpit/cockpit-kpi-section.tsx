"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { CockpitMetricCard, CockpitTokenCard } from "@/components/cockpit/kpi-card";
import { TokenChart } from "@/components/cockpit/token-chart";
import type { TokenSample } from "@/components/cockpit/token-types";
import { Bot } from "lucide-react";
import { memo, useEffect, useState } from "react";
import type { Metrics } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

type QueueSnapshot = {
  active?: number | null;
  limit?: number | string | null;
};

type CockpitKpiSectionProps = {
  metrics: Metrics | null;
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
  totalTokens: number;
  showReferenceSections: boolean;
};

const formatSystemClock = (date: Date) =>
  date.toLocaleTimeString("pl-PL", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

type SystemTimeStatProps = {
  label: string;
  hint: string;
};

const SystemTimeStat = memo(function SystemTimeStat({ label, hint }: SystemTimeStatProps) {
  const [systemTime, setSystemTime] = useState(() => formatSystemClock(new Date()));
  useEffect(() => {
    const timer = globalThis.window.setInterval(() => {
      setSystemTime(formatSystemClock(new Date()));
    }, 1000);
    return () => globalThis.window.clearInterval(timer);
  }, []);

  return <StatCard label={label} value={systemTime} hint={hint} suppressHydrationWarning />;
});

const formatUptime = (totalSeconds: number) => {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
};

const getTasksSummaryLabel = (
  tasksCreated: number,
  t: (key: string) => string,
): string => {
  if (tasksCreated > 0) {
    return `${tasksCreated.toLocaleString("pl-PL")} ${t("cockpit.metrics.queue.tasksSuffix")}`;
  }
  return t("cockpit.metrics.queue.noTasks");
};

const getUptimeLabel = (metrics: Metrics | null): string => {
  if (metrics?.uptime_seconds === undefined) return "Uptime: —";
  return `Uptime: ${formatUptime(metrics.uptime_seconds)}`;
};

const getTokenTrendTone = (tokenTrendDelta: number | null): "success" | "warning" => {
  if (tokenTrendDelta !== null && tokenTrendDelta < 0) return "success";
  return "warning";
};

const getTokenSplits = (
  tokenSplits: { label: string; value: number }[],
  t: (key: string) => string,
) => {
  if (tokenSplits.length > 0) return tokenSplits;
  return [{ label: t("cockpit.metrics.tokens.noData"), value: 0 }];
};

export function CockpitKpiSection({
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
}: CockpitKpiSectionProps) {
  const t = useTranslation();
  const tasksSummaryLabel = getTasksSummaryLabel(tasksCreated, t);
  const uptimeLabel = getUptimeLabel(metrics);
  const tokenTrendTone = getTokenTrendTone(tokenTrendDelta);
  const displayTokenSplits = getTokenSplits(tokenSplits, t);

  return (
    <>
      <Panel
        eyebrow={t("cockpit.metrics.title")}
        title={t("cockpit.metrics.statusTitle")}
        description={t("cockpit.metrics.statusDescription")}
        className="kpi-panel"
      >
        <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-5">
          <StatCard
            label={t("cockpit.metrics.kpi.tasks")}
            value={metrics?.tasks?.created ?? "—"}
            hint={t("cockpit.metrics.labels.created")}
          />
          <StatCard
            label={t("cockpit.metrics.labels.quality")}
            value={successRate !== null ? `${successRate}%` : "—"}
            hint={t("cockpit.metrics.labels.currentQuality")}
            accent="green"
          />
          <SystemTimeStat
            label={t("cockpit.metrics.labels.time")}
            hint={t("cockpit.metrics.labels.systemTime")}
          />
          <StatCard
            label={t("cockpit.metrics.kpi.queue")}
            value={queue ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}` : "—"}
            hint={t("cockpit.metrics.labels.activeLimit")}
            accent="blue"
          />
          <StatCard
            label={t("cockpit.metrics.labels.quality")}
            value={feedbackScore !== null ? `${feedbackScore}%` : "—"}
            hint={`${feedbackUp} 👍 / ${feedbackDown} 👎`}
            accent="violet"
          />
        </div>
      </Panel>
      {showReferenceSections && (
        <div className="grid gap-6">
          <Panel
            eyebrow={t("cockpit.metrics.queue.eyebrow")}
            title={t("cockpit.metrics.queue.title")}
            description={t("cockpit.metrics.queue.description")}
            className="kpi-panel"
          >
            {(() => {
              if (metricsLoading && !metrics) {
                return (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-400">
                    {t("cockpit.metrics.queue.loading")}
                  </div>
                );
              }
              if (successRate === null) {
                return (
                  <EmptyState
                    icon={<Bot className="h-4 w-4" />}
                    title={t("cockpit.metrics.queue.emptyTitle")}
                    description={t("cockpit.metrics.queue.emptyDescription")}
                  />
                );
              }
              return (
                <CockpitMetricCard
                  primaryValue={`${successRate}%`}
                  secondaryLabel={tasksSummaryLabel}
                  progress={successRate}
                  footer={uptimeLabel}
                />
              );
            })()}
          </Panel>
          <Panel
            eyebrow={t("cockpit.metrics.tokens.eyebrow")}
            title={t("cockpit.metrics.tokens.title")}
            description={t("cockpit.metrics.tokens.description")}
            className="kpi-panel"
          >
            {tokenMetricsLoading ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-400">
                {t("cockpit.metrics.tokens.loading")}
              </div>
            ) : (
              <CockpitTokenCard
                totalValue={totalTokens}
                splits={displayTokenSplits}
                chartSlot={
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-caption">{t("cockpit.metrics.tokens.trend")}</p>
                      <Badge tone={tokenTrendTone}>
                        {tokenTrendLabel}
                      </Badge>
                    </div>
                    {tokenHistory.length < 2 ? (
                      <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
                        {t("cockpit.metrics.tokens.insufficientData")}
                      </p>
                    ) : (
                      <div className="rounded-2xl box-subtle p-4">
                        <p className="text-caption">{t("cockpit.metrics.tokens.history")}</p>
                        <div className="mt-3 h-32">
                          <TokenChart history={tokenHistory} height={128} />
                        </div>
                      </div>
                    )}
                  </div>
                }
              />
            )}
          </Panel>
        </div>
      )}
    </>
  );
}

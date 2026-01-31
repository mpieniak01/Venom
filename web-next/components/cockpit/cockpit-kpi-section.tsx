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

const SystemTimeStat = memo(function SystemTimeStat() {
  const [systemTime, setSystemTime] = useState(() => formatSystemClock(new Date()));
  useEffect(() => {
    const timer = window.setInterval(() => {
      setSystemTime(formatSystemClock(new Date()));
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  return <StatCard label="Czas" value={systemTime} hint="Aktualny czas systemowy" />;
});

const formatUptime = (totalSeconds: number) => {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
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
  return (
    <>
      <Panel
        eyebrow="System KPIs"
        title="Status operacyjny"
        description="Najważniejsze liczby backendu."
        className="kpi-panel"
      >
        <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-5">
          <StatCard
            label="Zadania"
            value={metrics?.tasks?.created ?? "—"}
            hint="Łącznie utworzonych"
          />
          <StatCard
            label="Skuteczność"
            value={successRate !== null ? `${successRate}%` : "—"}
            hint="Aktualna skuteczność"
            accent="green"
          />
          <SystemTimeStat />
          <StatCard
            label="Kolejka"
            value={queue ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}` : "—"}
            hint="Aktywne / limit"
            accent="blue"
          />
          <StatCard
            label="Jakość"
            value={feedbackScore !== null ? `${feedbackScore}%` : "—"}
            hint={`${feedbackUp} 👍 / ${feedbackDown} 👎`}
            accent="violet"
          />
        </div>
      </Panel>
      {showReferenceSections && (
        <div className="grid gap-6">
          <Panel
            eyebrow="KPI kolejki"
            title="Skuteczność operacji"
            description="Monitoruj SLA tasków i uptime backendu."
            className="kpi-panel"
          >
            {metricsLoading && !metrics ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-400">
                Ładuję metryki zadań…
              </div>
            ) : successRate === null ? (
              <EmptyState
                icon={<Bot className="h-4 w-4" />}
                title="Brak danych SLA"
                description="Po uruchomieniu zadań i aktualizacji /metrics pojawi się trend skuteczności."
              />
            ) : (
              <CockpitMetricCard
                primaryValue={`${successRate}%`}
                secondaryLabel={
                  tasksCreated > 0
                    ? `${tasksCreated.toLocaleString("pl-PL")} zadań`
                    : "Brak zadań"
                }
                progress={successRate}
                footer={`Uptime: ${metrics?.uptime_seconds !== undefined
                  ? formatUptime(metrics.uptime_seconds)
                  : "—"
                  }`}
              />
            )}
          </Panel>
          <Panel
            eyebrow="KPI kolejki"
            title="Zużycie tokenów"
            description="Trend prompt/completion/cached."
            className="kpi-panel"
          >
            {tokenMetricsLoading ? (
              <div className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-4 py-3 text-sm text-zinc-400">
                Ładuję statystyki tokenów…
              </div>
            ) : (
              <CockpitTokenCard
                totalValue={totalTokens}
                splits={
                  tokenSplits.length > 0
                    ? tokenSplits
                    : [{ label: "Brak danych", value: 0 }]
                }
                chartSlot={
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <p className="text-caption">Trend próbek</p>
                      <Badge
                        tone={
                          tokenTrendDelta !== null && tokenTrendDelta < 0
                            ? "success"
                            : "warning"
                        }
                      >
                        {tokenTrendLabel}
                      </Badge>
                    </div>
                    {tokenHistory.length < 2 ? (
                      <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
                        Za mało danych, poczekaj na kolejne odczyty `/metrics/tokens`.
                      </p>
                    ) : (
                      <div className="rounded-2xl box-subtle p-4">
                        <p className="text-caption">Przebieg ostatnich próbek</p>
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

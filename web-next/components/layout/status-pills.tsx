"use client";

import { useMemo } from "react";
import { useQueueStatus, useMetrics, useTasks } from "@/hooks/use-api";
import type { Metrics, QueueStatus, Task } from "@/lib/types";
import { cn } from "@/lib/utils";

export type StatusPillsInitialData = {
  queue?: QueueStatus | null;
  metrics?: Metrics | null;
  tasks?: Task[] | null;
};

export function StatusPills({ initialData }: { initialData?: StatusPillsInitialData }) {
  const { data: queue, loading: queueLoading } = useQueueStatus(10000);
  const { data: metrics, loading: metricsLoading } = useMetrics(15000);
  const { data: tasks, loading: tasksLoading } = useTasks(15000);

  const queueData = queue ?? initialData?.queue ?? null;
  const metricsData = metrics ?? initialData?.metrics ?? null;
  const tasksData = tasks ?? initialData?.tasks ?? null;

  const successRateRaw = metricsData?.tasks?.success_rate;
  const metricsAvailable = typeof successRateRaw === "number";
  const queueAvailable = Boolean(queueData);
  const tasksAvailable = Array.isArray(tasksData);
  const queuePendingLoading = queueLoading && !queueData;
  const metricsPendingLoading = metricsLoading && !metricsData;
  const tasksPendingLoading = tasksLoading && !tasksData;

  const successRate = successRateRaw ?? 0;
  const activeTasks = tasksData?.length ?? 0;
  const queueActive = queueData?.active ?? 0;
  const queuePending = queueData?.pending ?? 0;

  const pills = useMemo(
    () => [
      {
        id: "queue",
        label: "Kolejka",
        value: queueAvailable ? `${queueActive}/${queueData?.limit ?? "∞"}` : "—",
        hint: queuePendingLoading ? "Ładuję dane..." : queueAvailable ? `${queuePending} oczekujących` : "Brak danych",
        tone: queueAvailable ? (queueData?.paused ? "warning" : "success") : "neutral",
        loading: queuePendingLoading,
      },
      {
        id: "success",
        label: "Skuteczność",
        value: metricsAvailable ? `${successRate}%` : "—",
        hint: metricsPendingLoading ? "Ładuję dane..." : metricsAvailable ? "ostatnie zadania" : "Metryki offline",
        tone: metricsAvailable ? (successRate > 70 ? "success" : "danger") : "neutral",
        loading: metricsPendingLoading,
      },
      {
        id: "tasks",
        label: "Zadania",
        value: tasksAvailable ? activeTasks : "—",
        hint: tasksPendingLoading ? "Ładuję dane..." : tasksAvailable ? "aktywnych" : "Brak danych",
        tone: tasksAvailable ? (activeTasks > 0 ? "warning" : "neutral") : "neutral",
        loading: tasksPendingLoading,
      },
    ],
    [
      queueAvailable,
      queueActive,
      queuePending,
      queueData?.limit,
      queueData?.paused,
      metricsAvailable,
      successRate,
      tasksAvailable,
      activeTasks,
      queuePendingLoading,
      metricsPendingLoading,
      tasksPendingLoading,
    ],
  );

  return (
    <div className="hidden items-center gap-3 lg:flex">
      {pills.map((pill) => (
        <div
          key={pill.id}
          data-testid={`status-pill-${pill.id}`}
          className={cn(
            "flex min-w-[120px] flex-col rounded-2xl border px-3 py-2 text-xs",
            pill.tone === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-100"
              : pill.tone === "warning"
                ? "border-amber-500/30 bg-amber-500/10 text-amber-100"
                : pill.tone === "danger"
                  ? "border-rose-500/30 bg-rose-500/10 text-rose-100"
                  : "border-white/10 bg-white/5 text-zinc-200",
          )}
        >
          <span className="text-[11px] uppercase tracking-[0.3em]">{pill.label}</span>
          <span className="text-lg font-semibold" data-testid={`status-pill-${pill.id}-value`}>
            {pill.loading ? (
              <span className="text-sm">Ładuje…</span>
            ) : (
              pill.value
            )}
          </span>
          <span className="text-[11px] text-white/70">{pill.hint}</span>
        </div>
      ))}
    </div>
  );
}

"use client";

import { useMemo } from "react";
import { useQueueStatus, useMetrics, useTasks } from "@/hooks/use-api";
import { cn } from "@/lib/utils";

export function StatusPills() {
  const { data: queue } = useQueueStatus(10000);
  const { data: metrics } = useMetrics(15000);
  const { data: tasks } = useTasks(15000);

  const successRateRaw = metrics?.tasks?.success_rate;
  const metricsAvailable = typeof successRateRaw === "number";
  const queueAvailable = Boolean(queue);
  const tasksAvailable = Array.isArray(tasks);

  const successRate = successRateRaw ?? 0;
  const activeTasks = tasks?.length ?? 0;
  const queueActive = queue?.active ?? 0;
  const queuePending = queue?.pending ?? 0;

  const pills = useMemo(
    () => [
      {
        id: "queue",
        label: "Queue",
        value: queueAvailable ? `${queueActive}/${queue?.limit ?? "∞"}` : "—",
        hint: queueAvailable ? `${queuePending} pending` : "Brak danych",
        tone: queueAvailable ? (queue?.paused ? "warning" : "success") : "neutral",
      },
      {
        id: "success",
        label: "Success",
        value: metricsAvailable ? `${successRate}%` : "—",
        hint: metricsAvailable ? "ostatnie zadania" : "Metryki offline",
        tone: metricsAvailable ? (successRate > 70 ? "success" : "danger") : "neutral",
      },
      {
        id: "tasks",
        label: "Tasks",
        value: tasksAvailable ? activeTasks : "—",
        hint: tasksAvailable ? "aktywnych" : "Brak danych",
        tone: tasksAvailable ? (activeTasks > 0 ? "warning" : "neutral") : "neutral",
      },
    ],
    [
      queueAvailable,
      queueActive,
      queuePending,
      queue?.limit,
      queue?.paused,
      metricsAvailable,
      successRate,
      tasksAvailable,
      activeTasks,
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
          <span className="text-lg font-semibold">{pill.value}</span>
          <span className="text-[11px] text-white/70">{pill.hint}</span>
        </div>
      ))}
    </div>
  );
}

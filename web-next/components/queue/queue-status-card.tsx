"use client";

import type { QueueStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";

type QueueStatusCardProps = {
  queue?: QueueStatus | null;
  offlineMessage?: string;
  testId?: string;
};

export function QueueStatusCard({
  queue,
  offlineMessage = "Brak danych kolejki – sprawdź połączenie API.",
  testId,
}: QueueStatusCardProps) {
  const offline =
    !queue ||
    (queue.active === undefined &&
      queue.pending === undefined &&
      queue.limit === undefined &&
      queue.paused === undefined);

  if (offline) {
    return (
      <div data-testid={testId}>
        <EmptyState
          title="Kolejka offline"
          description={offlineMessage}
          className="rounded-3xl border border-white/10 bg-white/5 p-4 text-sm"
        />
      </div>
    );
  }

  const metrics = [
    { label: "Active", value: queue.active ?? 0 },
    { label: "Pending", value: queue.pending ?? 0 },
    { label: "Limit", value: queue.limit ?? "∞" },
  ];

  return (
    <div
      className="rounded-3xl border border-white/10 bg-gradient-to-br from-emerald-500/5 via-emerald-500/0 to-cyan-500/5 p-4 text-sm text-white shadow-card"
      data-testid={testId ? `${testId}-online` : undefined}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Queue</p>
          <p className="text-base font-semibold">/api/v1/queue/status</p>
        </div>
        <Badge tone={queue.paused ? "warning" : "success"}>
          {queue.paused ? "Wstrzymana" : "Aktywna"}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-2xl border border-white/10 bg-black/30 px-3 py-2 text-center"
          >
            <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-500">
              {metric.label}
            </p>
            <p className="text-xl font-semibold text-white">{metric.value}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

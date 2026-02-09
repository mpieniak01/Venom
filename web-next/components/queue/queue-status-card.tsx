"use client";

import type { QueueStatus } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useTranslation } from "@/lib/i18n";

type QueueStatusCardProps = Readonly<{
  queue?: QueueStatus | null;
  offlineMessage?: string;
  testId?: string;
  loading?: boolean;
}>;

export function QueueStatusCard({
  queue,
  offlineMessage,
  testId,
  loading,
}: QueueStatusCardProps) {
  const t = useTranslation();
  const offlineDescription = offlineMessage ?? t("queueCard.offlineDescription");
  const offline =
    !queue ||
    (queue.active === undefined &&
      queue.pending === undefined &&
      queue.limit === undefined &&
      queue.paused === undefined);

  if (offline) {
    return (
      <div data-testid={testId}>
        {loading ? (
          <div className="card-shell card-base flex items-center justify-center p-4 text-sm text-zinc-300">
            Ładuję status kolejki…
          </div>
        ) : (
          <EmptyState
            title={t("queueCard.offlineTitle")}
            description={offlineDescription}
            className="card-shell card-base p-4 text-sm"
          />
        )}
      </div>
    );
  }

  const metrics = [
    { label: t("queueCard.metricActive"), value: queue.active ?? 0 },
    { label: t("queueCard.metricPending"), value: queue.pending ?? 0 },
    { label: t("queueCard.metricLimit"), value: queue.limit ?? "∞" },
  ];

  return (
    <div
      className="relative card-shell bg-gradient-to-br from-emerald-500/5 via-emerald-500/0 to-cyan-500/5 p-4 text-sm"
      data-testid={testId ? `${testId}-online` : undefined}
    >
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-caption">
            {t("queueCard.heading")}
          </p>
          <p className="text-base font-semibold">{t("queueCard.endpoint")}</p>
        </div>
        <Badge tone={queue.paused ? "warning" : "success"}>
          {queue.paused ? t("queueCard.statusPaused") : t("queueCard.statusActive")}
        </Badge>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="rounded-2xl box-muted px-3 py-2 text-center"
          >
            <p className="text-caption">
              {metric.label}
            </p>
            <p className="text-xl font-semibold text-white">{metric.value}</p>
          </div>
        ))}
      </div>
      {loading && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-[24px] bg-black/60 text-xs text-zinc-300">
          Ładuję status kolejki…
        </div>
      )}
    </div>
  );
}

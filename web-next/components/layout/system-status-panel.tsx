"use client";

import { useMemo } from "react";
import { useQueueStatus } from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useTranslation } from "@/lib/i18n";

type StatusTone = "success" | "warning" | "danger" | "neutral";

type StatusRow = {
  id: string;
  label: string;
  hint: string;
  tone: StatusTone;
};

export function SystemStatusPanel() {
  const { data: queue, error: queueError } = useQueueStatus(10000);
  const { connected } = useTelemetryFeed(5);
  const t = useTranslation();

  const statuses: StatusRow[] = useMemo(() => {
    const hasQueue = Boolean(queue);
    const apiTone: StatusTone = hasQueue ? "success" : queueError ? "danger" : "warning";

    const queueTone: StatusTone = hasQueue
      ? queue?.paused
        ? "warning"
        : "success"
      : "neutral";

    const wsTone: StatusTone = connected ? "success" : hasQueue ? "warning" : "danger";

    return [
      {
        id: "api",
        label: t("systemStatus.api"),
        hint: hasQueue ? "/api/v1/*" : queueError ?? t("systemStatus.hints.waiting"),
        tone: apiTone,
      },
      {
        id: "queue",
        label: t("systemStatus.queue"),
        hint: hasQueue
          ? t("systemStatus.hints.queueDetails", { active: queue?.active ?? 0, pending: queue?.pending ?? 0 })
          : t("systemStatus.hints.queueEmpty"),
        tone: queueTone,
      },
      {
        id: "ws",
        label: t("systemStatus.ws"),
        hint: connected
          ? t("systemStatus.hints.wsLive")
          : hasQueue
            ? t("systemStatus.hints.wsInactive")
            : t("systemStatus.hints.wsChannel"),
        tone: wsTone,
      },
    ];
  }, [connected, queue, queueError, t]);

  return (
    <div className="surface-card p-4 text-sm text-zinc-100" data-testid="system-status-panel">
      <p className="eyebrow">{t("systemStatus.title")}</p>
      <div className="mt-3 space-y-3">
        {statuses.map((status) => (
          <div
            key={status.id}
            className="flex items-start justify-between gap-3"
            data-testid={`system-status-${status.id}`}
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide">{status.label}</p>
              <p className="text-hint">{status.hint}</p>
            </div>
            <span
              className={[
                "mt-1 h-2.5 w-2.5 rounded-full",
                status.tone === "success"
                  ? "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.6)]"
                  : status.tone === "warning"
                    ? "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.6)]"
                    : "bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.6)]",
              ].join(" ")}
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
      {queueError && (
        <p className="mt-3 text-xs text-amber-300" data-testid="system-status-error">
          {queueError}
        </p>
      )}
    </div>
  );
}

"use client";

import { useMemo } from "react";
import { useQueueStatus } from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";

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

  const statuses: StatusRow[] = useMemo(() => {
    const hasQueue = Boolean(queue);
    const apiTone: StatusTone = hasQueue ? "success" : queueError ? "danger" : "warning";

    const queueTone: StatusTone = hasQueue
      ? queue?.paused
        ? "warning"
        : "success"
      : "neutral";

    const wsTone: StatusTone = connected ? "success" : "danger";

    return [
      {
        id: "api",
        label: "API",
        hint: hasQueue ? "/api/v1/*" : queueError ?? "Oczekiwanie na odpowiedź...",
        tone: apiTone,
      },
      {
        id: "queue",
        label: "Kolejka",
        hint: hasQueue
          ? `Aktywne ${queue?.active ?? 0} • Oczekujące ${queue?.pending ?? 0}`
          : "Brak danych kolejki",
        tone: queueTone,
      },
      {
        id: "ws",
        label: "Kanał WS",
        hint: connected ? "Telemetria live" : "Kanał /ws/events",
        tone: wsTone,
      },
    ];
  }, [connected, queue, queueError]);

  return (
    <div className="surface-card p-4 text-sm text-zinc-100" data-testid="system-status-panel">
      <p className="eyebrow">STATUS SYSTEMU</p>
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

"use client";

import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { useQueueStatus } from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";

type StatusTone = "success" | "warning" | "danger" | "neutral";

type StatusRow = {
  id: string;
  label: string;
  value: string;
  hint: string;
  tone: StatusTone;
};

export function SystemStatusPanel() {
  const {
    data: queue,
    error: queueError,
    loading: queueLoading,
  } = useQueueStatus(10000);
  const { connected } = useTelemetryFeed(5);

  const statuses: StatusRow[] = useMemo(() => {
    const hasQueue = Boolean(queue);
    const apiTone: StatusTone = hasQueue ? "success" : queueError ? "danger" : "warning";
    const apiValue = queueLoading
      ? "Łączenie..."
      : hasQueue
        ? "Dostępne"
        : queueError
          ? "Offline"
          : "Brak danych";

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
        value: apiValue,
        hint: hasQueue ? "/api/v1/*" : queueError ?? "Oczekiwanie na odpowiedź...",
        tone: apiTone,
      },
      {
        id: "queue",
        label: "Kolejka",
        value: hasQueue ? (queue?.paused ? "Wstrzymana" : "Aktywna") : "—",
        hint: hasQueue
          ? `Aktywne ${queue?.active ?? 0} • Oczekujące ${queue?.pending ?? 0}`
          : "Brak danych kolejki",
        tone: queueTone,
      },
      {
        id: "ws",
        label: "Kanał WS",
        value: connected ? "Połączony" : "Rozłączony",
        hint: connected ? "Telemetria live" : "Kanał /ws/events",
        tone: wsTone,
      },
    ];
  }, [connected, queue, queueError, queueLoading]);

  return (
    <div className="surface-card p-4 text-sm text-zinc-100" data-testid="system-status-panel">
      <p className="text-xs uppercase tracking-[0.25em] text-zinc-500">STATUS SYSTEMU</p>
      <div className="mt-3 space-y-3">
        {statuses.map((status) => (
          <div
            key={status.id}
            className="flex items-start justify-between gap-3"
            data-testid={`system-status-${status.id}`}
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide">{status.label}</p>
              <p className="text-[11px] text-zinc-500">{status.hint}</p>
            </div>
            <Badge tone={status.tone}>{status.value}</Badge>
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

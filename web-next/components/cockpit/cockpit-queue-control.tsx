"use client";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { Package } from "lucide-react";

type QueueSnapshot = {
  active?: number | null;
  pending?: number | null;
  limit?: number | string | null;
  paused?: boolean | null;
};

type CockpitQueueControlProps = {
  readonly queue: QueueSnapshot | null;
  readonly queueAction: string | null;
  readonly queueActionMessage: string | null;
  readonly onToggleQueue: () => void;
  readonly onExecuteQueueMutation: (action: "purge" | "emergency") => void;
};

export function CockpitQueueControl({
  queue,
  queueAction,
  queueActionMessage,
  onToggleQueue,
  onExecuteQueueMutation,
}: Readonly<CockpitQueueControlProps>) {
  return (
    <Panel
      title="Zarządzanie kolejką"
      description="Stan kolejki `/api/v1/queue/status`, koszty sesji i akcje awaryjne."
      className="queue-panel"
    >
      {queue ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard
              label="Aktywne"
              value={queue.active ?? "—"}
              hint="Zadania w toku"
              accent="violet"
            />
            <StatCard
              label="Oczekujące"
              value={queue.pending ?? "—"}
              hint="Czekają na wykonanie"
              accent="indigo"
            />
            <StatCard
              label="Limit"
              value={queue.limit ?? "∞"}
              hint="Maksymalna pojemność"
              accent="blue"
            />
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="xs"
              onClick={onToggleQueue}
              disabled={queueAction === "pause" || queueAction === "resume"}
            >
              {queue.paused ? "Wznów kolejkę" : "Wstrzymaj kolejkę"}
            </Button>
            <Button
              variant="outline"
              size="xs"
              onClick={() => onExecuteQueueMutation("purge")}
              disabled={queueAction === "purge"}
            >
              Wyczyść kolejkę
            </Button>
            <Button
              variant="danger"
              size="xs"
              onClick={() => onExecuteQueueMutation("emergency")}
              disabled={queueAction === "emergency"}
            >
              Awaryjne zatrzymanie
            </Button>
          </div>
          {queueActionMessage && (
            <p className="mt-2 text-xs text-zinc-400">{queueActionMessage}</p>
          )}
        </>
      ) : (
        <EmptyState
          icon={<Package className="h-4 w-4" />}
          title="Kolejka offline"
          description="Brak danych `/api/v1/queue/status` – sprawdź backend lub użyj Quick Actions."
        />
      )}
    </Panel>
  );
}

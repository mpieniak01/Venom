"use client";

import { useState, type ReactNode } from "react";
import { ListCard } from "@/components/ui/list-card";
import { EmptyState } from "@/components/ui/empty-state";
import { emergencyStop, purgeQueue, toggleQueue, useQueueStatus, useTasks } from "@/hooks/use-api";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Inbox, Pause, Play, Trash2 } from "lucide-react";

type QuickActionsProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

const deriveQueueActionLabel = (paused?: boolean) =>
  paused ? "Wznów kolejkę" : "Wstrzymaj kolejkę";

const deriveQueueActionEndpoint = (paused?: boolean) =>
  paused ? "/api/v1/queue/resume" : "/api/v1/queue/pause";

type QuickActionItem = {
  id: "toggle" | "purge" | "emergency";
  label: string;
  description: string;
  endpoint: string;
  icon: ReactNode;
  tone: "success" | "warning" | "danger";
  confirm?: string;
  handler: () => Promise<unknown>;
};

export function QuickActions({ open, onOpenChange }: QuickActionsProps) {
  const { data: queue, refresh: refreshQueue } = useQueueStatus();
  const { refresh: refreshTasks } = useTasks();
  const [message, setMessage] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const queueAvailable = Boolean(queue);
  const queueOfflineMessage = "Brak danych kolejki – sprawdź połączenie API.";

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    if (running) return;
    setRunning(name);
    setMessage(null);
    try {
      await fn();
      setMessage(`${name} wykonane.`);
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : `Błąd podczas ${name}.`);
    } finally {
      setRunning(null);
    }
  };

  const actions: QuickActionItem[] = [
    {
      id: "toggle",
      label: deriveQueueActionLabel(queue?.paused),
      description: "Kontroluje state kolejki (pause/resume).",
      endpoint: deriveQueueActionEndpoint(queue?.paused),
      icon: queue?.paused ? <Play className="h-4 w-4 text-emerald-300" /> : <Pause className="h-4 w-4 text-amber-300" />,
      tone: queue?.paused ? "success" : "warning",
      handler: () => toggleQueue(queue?.paused ?? false),
    },
    {
      id: "purge",
      label: "Purge queue",
      description: "Oczyszcza wszystkie oczekujące taski.",
      endpoint: "/api/v1/queue/purge",
      icon: <Trash2 className="h-4 w-4" />,
      tone: "warning",
      confirm: "Wyczyścić wszystkie oczekujące zadania?",
      handler: () => purgeQueue(),
    },
    {
      id: "emergency",
      label: "Emergency stop",
      description: "Natychmiast zatrzymuje kolejkę (awaryjnie).",
      endpoint: "/api/v1/queue/emergency-stop",
      icon: <AlertTriangle className="h-4 w-4" />,
      tone: "danger",
      confirm: "Awaryjny stop zatrzyma wszystkie operacje. Kontynuować?",
      handler: () => emergencyStop(),
    },
  ];

  const handleQuickAction = async (action: QuickActionItem) => {
    if (!queueAvailable) {
      setMessage(queueOfflineMessage);
      return;
    }
    if (action.confirm && !confirm(action.confirm)) return;
    await runAction(action.label, action.handler);
  };

  const badgeLabel = (action: QuickActionItem) => {
    if (action.id === "emergency") return "Emergency";
    return "Queue";
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex h-full max-w-lg flex-col gap-4 border-l border-white/10 bg-zinc-950/95">
        <SheetHeader>
          <SheetTitle>Quick Actions</SheetTitle>
          <SheetDescription>
            Najczęstsze akcje operacyjne /api/v1/queue z każdego widoku.
          </SheetDescription>
        </SheetHeader>
        <div className="surface-card w-full bg-white/5 p-4">
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Queue</p>
          {queueAvailable ? (
            <div className="mt-2 flex items-center gap-3 text-sm text-zinc-300">
              <Badge tone={queue?.paused ? "warning" : "success"}>
                {queue?.paused ? "Wstrzymana" : "Aktywna"}
              </Badge>
              <span>
                Active: {queue?.active ?? 0} • Pending: {queue?.pending ?? 0} • Limit:{" "}
                {queue?.limit ?? "∞"}
              </span>
            </div>
          ) : (
            <div data-testid="queue-offline-state">
              <EmptyState
                icon={<Inbox className="h-4 w-4" />}
                title="Brak danych kolejki"
                description={queueOfflineMessage}
                className="mt-2 border-white/10 bg-transparent px-0 py-0 text-sm text-zinc-400"
              />
            </div>
          )}
        </div>
        <div className="space-y-2">
          {actions.map((action) => {
            const isRunning = running === action.id;
            return (
              <ListCard
                key={action.id}
                title={action.label}
                subtitle={action.description}
                badge={<Badge tone={action.tone}>{badgeLabel(action)}</Badge>}
                meta={
                  <div className="flex items-center gap-2 text-[11px] text-zinc-500">
                    <span>{action.endpoint}</span>
                    {isRunning && <span className="text-emerald-300">Wysyłam...</span>}
                  </div>
                }
                icon={action.icon}
                selected={isRunning}
                onClick={() => handleQuickAction(action)}
              />
            );
          })}
        </div>
        {message && (
          <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-xs text-zinc-300">
            {message}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

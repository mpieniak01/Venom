"use client";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { ListCard } from "@/components/ui/list-card";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useMemo } from "react";

type NotificationDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function NotificationDrawer({ open, onOpenChange }: NotificationDrawerProps) {
  const { entries, connected } = useTelemetryFeed(100);

  const notifications = useMemo(
    () =>
      entries
        .map((entry) => {
          const payload = entry.payload;
          if (typeof payload === "object" && payload !== null) {
            const maybe = payload as { level?: string; message?: string };
            if (
              maybe.message &&
              maybe.level &&
              (maybe.level.toLowerCase().includes("warn") ||
                maybe.level.toLowerCase().includes("error") ||
                maybe.level.toLowerCase().includes("fail"))
            ) {
              return {
                id: entry.id,
                ts: entry.ts,
                level: maybe.level.toUpperCase(),
                message: maybe.message,
              };
            }
          }
          return null;
        })
        .filter(Boolean) as Array<{ id: string; ts: number; level: string; message: string }>,
    [entries],
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex h-full max-w-lg flex-col border-l border-white/10 bg-zinc-950/95">
        <SheetHeader>
          <SheetTitle>Notifications</SheetTitle>
          <SheetDescription>
            Ostrzeżenia i błędy z feedu `/ws/events` filtrowane po poziomie logów.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 flex-1 overflow-y-auto space-y-3">
          {!connected ? (
            <div data-testid="notification-offline-state">
              <EmptyState
                icon={<span className="text-lg">📡</span>}
                title="Brak połączenia"
                description="Kanał WebSocket jest offline – powiadomienia pojawią się po wznowieniu."
                className="text-sm"
              />
            </div>
          ) : notifications.length === 0 ? (
            <EmptyState
              icon={<span className="text-lg">🚨</span>}
              title="Brak ostrzeżeń"
              description="Aktualnie brak poziomów warn/error w telemetrii."
              className="text-sm"
            />
          ) : (
            notifications.map((note) => (
              <ListCard
                key={note.id}
                title={note.message}
                badge={<Badge tone={toneFromLevel(note.level)}>{note.level}</Badge>}
                meta={<span className="text-xs text-zinc-400">{new Date(note.ts).toLocaleString()}</span>}
              />
            ))
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function toneFromLevel(level: string) {
  if (level.toLowerCase().includes("error")) return "danger" as const;
  if (level.toLowerCase().includes("warn")) return "warning" as const;
  return "neutral" as const;
}

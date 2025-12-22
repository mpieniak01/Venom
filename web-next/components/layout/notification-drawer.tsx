"use client";

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/list-card";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useMemo } from "react";
import { OverlayFallback } from "./overlay-fallback";
import { useTranslation } from "@/lib/i18n";

type NotificationDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function NotificationDrawer({ open, onOpenChange }: NotificationDrawerProps) {
  const { entries, connected } = useTelemetryFeed(100);
  const t = useTranslation();

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
      <SheetContent
        data-testid="notification-drawer"
        className="flex h-full max-w-lg flex-col border-l border-white/10 bg-zinc-950/95"
      >
        <SheetHeader>
          <SheetTitle>{t("notifications.title")}</SheetTitle>
          <SheetDescription>{t("notifications.description")}</SheetDescription>
        </SheetHeader>
        <div className="mt-4 flex-1 overflow-y-auto space-y-3">
          {!connected ? (
            <OverlayFallback
              icon={<span className="text-lg">📡</span>}
              title={t("notifications.offlineTitle")}
              description={t("notifications.offlineDescription")}
              hint={t("notifications.hint")}
              testId="notification-offline-state"
            />
          ) : notifications.length === 0 ? (
            <OverlayFallback
              icon={<span className="text-lg">🚨</span>}
              title={t("notifications.emptyTitle")}
              description={t("notifications.emptyDescription")}
              hint={t("notifications.hint")}
            />
          ) : (
            notifications.map((note) => (
              <ListCard
                key={note.id}
                title={note.message}
                badge={<Badge tone={toneFromLevel(note.level)}>{note.level}</Badge>}
                meta={<span className="text-hint">{new Date(note.ts).toLocaleString()}</span>}
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

"use client";

import { useMemo, useState, type ReactNode } from "react";
import { ListCard } from "@/components/ui/list-card";
import { emergencyStop, purgeQueue, toggleQueue, useQueueStatus, useTasks } from "@/hooks/use-api";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle, Pause, Play, Trash2 } from "lucide-react";
import { QueueStatusCard } from "@/components/queue/queue-status-card";
import { useTranslation } from "@/lib/i18n";

type QuickActionsProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

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
  const {
    data: queue,
    refresh: refreshQueue,
    loading: queueLoading,
  } = useQueueStatus();
  const { refresh: refreshTasks } = useTasks();
  const [message, setMessage] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const queueAvailable = Boolean(queue) && !queueLoading;
  const t = useTranslation();
  const queueOfflineMessage = t("quickActions.offlineMessage");

  const runAction = async (name: string, fn: () => Promise<unknown>) => {
    if (running) return;
    setRunning(name);
    setMessage(null);
    try {
      await fn();
      setMessage(t("quickActions.successMessage", { action: name }));
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setMessage(
        err instanceof Error ? err.message : t("quickActions.errorMessage", { action: name }),
      );
    } finally {
      setRunning(null);
    }
  };

  const actions: QuickActionItem[] = useMemo(
    () => [
      {
        id: "toggle",
        label: queue?.paused
          ? t("quickActions.actions.toggleResume")
          : t("quickActions.actions.togglePause"),
        description: t("quickActions.actions.toggleDescription"),
        endpoint: deriveQueueActionEndpoint(queue?.paused),
        icon: queue?.paused ? (
          <Play className="h-4 w-4 text-emerald-300" />
        ) : (
          <Pause className="h-4 w-4 text-amber-300" />
        ),
        tone: queue?.paused ? "success" : "warning",
        handler: () => toggleQueue(queue?.paused ?? false),
      },
      {
        id: "purge",
        label: t("quickActions.actions.purgeLabel"),
        description: t("quickActions.actions.purgeDescription"),
        endpoint: "/api/v1/queue/purge",
        icon: <Trash2 className="h-4 w-4" />,
        tone: "warning",
        confirm: t("quickActions.actions.purgeConfirm"),
        handler: () => purgeQueue(),
      },
      {
        id: "emergency",
        label: t("quickActions.actions.emergencyLabel"),
        description: t("quickActions.actions.emergencyDescription"),
        endpoint: "/api/v1/queue/emergency-stop",
        icon: <AlertTriangle className="h-4 w-4" />,
        tone: "danger",
        confirm: t("quickActions.actions.emergencyConfirm"),
        handler: () => emergencyStop(),
      },
    ],
    [queue?.paused, t],
  );

  const handleQuickAction = async (action: QuickActionItem) => {
    if (!queueAvailable) {
      setMessage(queueOfflineMessage);
      return;
    }
    if (action.confirm && !confirm(action.confirm)) return;
    await runAction(action.label, action.handler);
  };

  const badgeLabel = (action: QuickActionItem) => {
    if (action.id === "emergency") return t("quickActions.badgeEmergency");
    return t("quickActions.badgeQueue");
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex h-full max-w-lg flex-col gap-4 border-l border-white/10 bg-zinc-950/95">
        <SheetHeader>
          <SheetTitle>{t("quickActions.title")}</SheetTitle>
          <SheetDescription>{t("quickActions.description")}</SheetDescription>
        </SheetHeader>
        <QueueStatusCard
          queue={queue}
          offlineMessage={t("quickActions.offlineMessage")}
          testId="queue-offline-state"
        />
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
                  <div className="flex items-center gap-2 text-caption">
                    <span>{action.endpoint}</span>
                    {isRunning && <span className="text-emerald-300">{t("quickActions.sending")}</span>}
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
          <div className="rounded-2xl box-base p-3 text-xs text-muted">
            {message}
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}

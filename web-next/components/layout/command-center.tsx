"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import {
  useMetrics,
  useQueueStatus,
  useServiceStatus,
  useTasks,
} from "@/hooks/use-api";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { StatCard } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/list-card";
import { ArrowUpRight, Compass, Cpu, RefreshCw } from "lucide-react";
import { OverlayFallback } from "./overlay-fallback";
import { useTranslation } from "@/lib/i18n";

type CommandCenterProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function CommandCenter({ open, onOpenChange }: CommandCenterProps) {
  const router = useRouter();
  const { data: queue } = useQueueStatus();
  const { data: tasks } = useTasks();
  const { data: metrics } = useMetrics();
  const { data: services } = useServiceStatus();
  const t = useTranslation();

  const successRateRaw = metrics?.tasks?.success_rate;
  const queueAvailable = Boolean(queue);
  const metricsAvailable = typeof successRateRaw === "number";
  const servicesAvailable = Array.isArray(services) && services.length > 0;
  const queueOffline = !queueAvailable;
  const servicesOffline = !servicesAvailable;

  const successRate = successRateRaw ?? 0;
  const queueStatus = useMemo(
    () => ({
      active: queue?.active ?? 0,
      pending: queue?.pending ?? 0,
      limit: queue?.limit ?? "∞",
      paused: queue?.paused ?? false,
    }),
    [queue?.active, queue?.limit, queue?.paused, queue?.pending],
  );

  const taskSummary = useMemo(() => aggregateTaskStatuses(tasks || []), [tasks]);
  const visibleServices = useMemo(
    () => (Array.isArray(services) ? services.slice(0, 5) : []),
    [services],
  );

  const queueOfflineMessage = t("commandCenter.queueOffline");

  const quickLinks = useMemo(
    () => [
      {
        label: t("commandCenter.shortcuts.links.cockpit.label"),
        description: t("commandCenter.shortcuts.links.cockpit.description"),
        href: "/",
      },
      {
        label: t("commandCenter.shortcuts.links.inspector.label"),
        description: t("commandCenter.shortcuts.links.inspector.description"),
        href: "/inspector",
      },
      {
        label: t("commandCenter.shortcuts.links.brain.label"),
        description: t("commandCenter.shortcuts.links.brain.description"),
        href: "/brain",
      },
      // {
      //   label: t("commandCenter.shortcuts.links.strategy.label"),
      //   description: t("commandCenter.shortcuts.links.strategy.description"),
      //   href: "/strategy",
      // },
    ],
    [t],
  );

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="command-center-drawer"
        className="flex h-full max-w-2xl flex-col gap-6 overflow-y-auto border-l border-white/10 bg-zinc-950/95"
      >
        <SheetHeader>
          <SheetTitle>{t("commandCenter.title")}</SheetTitle>
          <SheetDescription>{t("commandCenter.description")}</SheetDescription>
        </SheetHeader>

        <div className="grid gap-4 md:grid-cols-3">
          <StatCard
            label={t("commandCenter.stats.queueLabel")}
            value={queueAvailable ? `${queueStatus.active}/${queueStatus.limit}` : "—"}
            hint={
              queueAvailable
                ? queueStatus.paused
                  ? t("commandCenter.stats.queueHintPaused")
                  : t("commandCenter.stats.queueHintActive")
                : t("commandCenter.stats.queueHintOffline")
            }
            accent="blue"
          />
          <StatCard
            label={t("commandCenter.stats.pendingLabel")}
            value={queueAvailable ? queueStatus.pending : "—"}
            hint={
              queueAvailable
                ? t("commandCenter.stats.pendingHint")
                : t("commandCenter.stats.queueHintOffline")
            }
            accent="purple"
          />
          <StatCard
            label={t("commandCenter.stats.successLabel")}
            value={metricsAvailable ? `${successRate}%` : "—"}
            hint={
              metricsAvailable
                ? t("commandCenter.stats.successHint")
                : t("commandCenter.stats.successOffline")
            }
            accent="green"
          />
        </div>
        {queueOffline && (
          <p className="text-xs text-zinc-500" data-testid="command-center-queue-offline">
            {queueOfflineMessage}
          </p>
        )}

        <section className="surface-card p-4">
          <header className="mb-3 flex items-center justify-between">
            <div>
              <p className="eyebrow">
                {t("commandCenter.shortcuts.eyebrow")}
              </p>
              <h3 className="heading-h3">
                {t("commandCenter.shortcuts.title")}
              </h3>
            </div>
            <Compass className="h-5 w-5 text-violet-300" />
          </header>
          <div className="space-y-2">
            {quickLinks.map((link) => (
              <ListCard
                key={link.href}
                title={link.label}
                subtitle={link.description}
                meta={<span className="text-xs text-zinc-400">{t("commandCenter.shortcuts.goTo")}</span>}
                badge={<ArrowUpRight className="h-4 w-4" />}
                onClick={() => {
                  router.push(link.href);
                  onOpenChange(false);
                }}
              />
            ))}
          </div>
        </section>

        <section className="surface-card p-4">
          <header className="flex items-center justify-between">
            <div>
              <p className="eyebrow">
                {t("commandCenter.tasks.eyebrow")}
              </p>
              <h3 className="heading-h3">
                {t("commandCenter.tasks.title")}
              </h3>
            </div>
            <Cpu className="h-5 w-5 text-emerald-300" />
          </header>
          <div className="mt-4 space-y-2">
            {taskSummary.length === 0 ? (
              <OverlayFallback
                icon={<Cpu className="h-4 w-4 text-emerald-300" />}
                title={t("commandCenter.tasks.fallbackTitle")}
                description={t("commandCenter.tasks.fallbackDescription")}
                hint={t("commandCenter.tasks.fallbackHint")}
              />
            ) : (
              taskSummary.map((entry) => (
                <ListCard
                  key={entry.status}
                  title={entry.status}
                  badge={<Badge tone={toneFromStatus(entry.status)}>{entry.count}</Badge>}
                />
              ))
            )}
          </div>
        </section>

        <section className="surface-card p-4" data-testid="command-center-services-section">
          <header className="flex items-center justify-between">
            <div>
              <p className="eyebrow">
                {t("commandCenter.services.eyebrow")}
              </p>
              <h3 className="heading-h3">
                {t("commandCenter.services.title")}
              </h3>
            </div>
            <RefreshCw className="h-5 w-5 text-sky-300" />
          </header>
          <div className="mt-4 space-y-2" data-testid="command-center-services-list">
            {visibleServices.map((svc) => (
              <ListCard
                key={svc.name}
                title={svc.name}
                subtitle={t(svc.detail ?? "common.noDescription")}
                badge={<Badge tone={toneFromStatus(svc.status)}>{t(svc.status)}</Badge>}
              />
            ))}
            {servicesOffline && (
              <OverlayFallback
                icon={<RefreshCw className="h-4 w-4 text-sky-300" />}
                title={t("commandCenter.services.fallbackTitle")}
                description={t("commandCenter.services.fallbackDescription")}
                hint={t("commandCenter.services.fallbackHint")}
                testId="command-center-services-offline"
              />
            )}
          </div>
        </section>
      </SheetContent>
    </Sheet>
  );
}

function aggregateTaskStatuses(
  tasks: Array<{ status: string | undefined }>,
): Array<{ status: string; count: number }> {
  if (!tasks || tasks.length === 0) return [];
  const bucket: Record<string, number> = {};
  tasks.forEach((task) => {
    const key = (task.status || "UNKNOWN").toUpperCase();
    bucket[key] = (bucket[key] || 0) + 1;
  });
  return Object.entries(bucket).map(([status, count]) => ({ status, count }));
}

function toneFromStatus(status?: string) {
  if (!status) return "neutral" as const;
  const upper = status.toUpperCase();
  if (upper.includes("COMPLETE") || upper.includes("HEALTH")) return "success" as const;
  if (upper.includes("PROCESS") || upper.includes("DEGRADED") || upper.includes("WARN"))
    return "warning" as const;
  if (upper.includes("FAIL") || upper.includes("DOWN")) return "danger" as const;
  return "neutral" as const;
}

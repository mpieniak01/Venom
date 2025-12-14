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
import { EmptyState } from "@/components/ui/empty-state";
import { ArrowUpRight, Compass, Cpu, RefreshCw } from "lucide-react";

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

  const successRateRaw = metrics?.tasks?.success_rate;
  const queueAvailable = Boolean(queue);
  const metricsAvailable = typeof successRateRaw === "number";
  const servicesAvailable = Boolean(services && services.length);

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
  const visibleServices = useMemo(() => services?.slice(0, 5) ?? [], [services]);

  const queueOfflineMessage = "Brak danych kolejki – sprawdź połączenie API.";

  const quickLinks = [
    { label: "Cockpit", description: "Czat i logi runtime", href: "/" },
    { label: "Inspector", description: "RequestTracer + kroki", href: "/inspector" },
    { label: "Brain", description: "Graf wiedzy i lekcje", href: "/brain" },
    { label: "Strategy", description: "War Room & KPI", href: "/strategy" },
  ];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="flex h-full max-w-2xl flex-col gap-6 overflow-y-auto border-l border-white/10 bg-zinc-950/95">
        <SheetHeader>
          <SheetTitle>Command Center</SheetTitle>
          <SheetDescription>
            Globalny podgląd kolejki, tasków i usług z szybkimi skrótami nawigacyjnymi.
          </SheetDescription>
        </SheetHeader>

        <div className="grid gap-4 md:grid-cols-3">
          <StatCard
            label="Kolejka"
            value={queueAvailable ? `${queueStatus.active}/${queueStatus.limit}` : "—"}
            hint={queueAvailable ? (queueStatus.paused ? "Wstrzymana" : "Aktywna") : "Brak danych"}
            accent="blue"
          />
          <StatCard
            label="Pending"
            value={queueAvailable ? queueStatus.pending : "—"}
            hint={queueAvailable ? "Oczekujące zadania" : "Brak danych"}
            accent="purple"
          />
          <StatCard
            label="Success rate"
            value={metricsAvailable ? `${successRate}%` : "—"}
            hint={metricsAvailable ? "Metryki /api/v1/metrics" : "Metryki offline"}
            accent="green"
          />
        </div>
        {!queueAvailable && (
          <p className="text-xs text-zinc-500" data-testid="command-center-queue-offline">
            {queueOfflineMessage}
          </p>
        )}

        <section className="surface-card p-4">
          <header className="mb-3 flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Skróty</p>
              <h3 className="text-lg font-semibold text-white">Nawigacja operacyjna</h3>
            </div>
            <Compass className="h-5 w-5 text-violet-300" />
          </header>
          <div className="space-y-2">
            {quickLinks.map((link) => (
              <ListCard
                key={link.href}
                title={link.label}
                subtitle={link.description}
                meta={<span className="text-xs text-zinc-400">Przejdź</span>}
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
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Aktywne taski</p>
              <h3 className="text-lg font-semibold text-white">Status agentów</h3>
            </div>
            <Cpu className="h-5 w-5 text-emerald-300" />
          </header>
          <div className="mt-4 space-y-2">
            {taskSummary.length === 0 ? (
              <EmptyState
                icon={<Cpu className="h-4 w-4 text-emerald-300" />}
                title="Brak aktywnych zadań"
                description="Kolejka chwilowo nie przetwarza tasków."
                className="text-sm"
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

        <section className="surface-card p-4">
          <header className="flex items-center justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                System Services
              </p>
              <h3 className="text-lg font-semibold text-white">Status integracji</h3>
            </div>
            <RefreshCw className="h-5 w-5 text-sky-300" />
          </header>
          <div className="mt-4 space-y-2">
            {visibleServices.map((svc) => (
              <ListCard
                key={svc.name}
                title={svc.name}
                subtitle={svc.detail ?? "Brak opisu"}
                badge={<Badge tone={toneFromStatus(svc.status)}>{svc.status}</Badge>}
              />
            ))}
            {!servicesAvailable && (
              <div data-testid="command-center-services-offline">
                <EmptyState
                  icon={<RefreshCw className="h-4 w-4 text-sky-300" />}
                  title="Brak usług"
                  description="Sprawdź połączenie z backendem."
                  className="text-sm"
                />
              </div>
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

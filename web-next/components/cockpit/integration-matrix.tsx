import { Panel } from "@/components/ui/panel";
import { Badge } from "@/components/ui/badge";
import { ListCard } from "@/components/ui/list-card";
import type { ServiceStatus } from "@/lib/types";

type IntegrationMatrixProps = Readonly<{
  services: ServiceStatus[] | null | undefined;
  events: Array<{ id: string; ts: number; payload: unknown }>;
}>;

export function IntegrationMatrix({ services, events }: IntegrationMatrixProps) {
  const grouped = groupServices(services || []);
  const latestEvents = events.slice(0, 4);

  return (
    <Panel
      title="Integracje i operacje"
      description="Status usług operacyjnych (/api/v1/system/services) + najnowsze eventy z /ws/events."
    >
      <div className="grid gap-4 md:grid-cols-3">
        {grouped.map((group) => (
          <div key={group.name} className="rounded-2xl box-base p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">{group.name}</p>
              <Badge tone={group.statusTone}>{group.statusLabel}</Badge>
            </div>
            <div className="space-y-2 text-sm text-zinc-300">
              {group.services.length === 0 ? (
                <p className="text-xs text-zinc-500">Brak danych usług.</p>
              ) : (
                group.services.map((svc) => (
                  <div key={svc.name} className="rounded-xl box-muted px-3 py-2">
                    <p className="font-semibold text-white">{svc.name}</p>
                    <p className="text-xs text-zinc-500">{svc.detail ?? "Brak opisu."}</p>
                    <Badge tone={serviceTone(svc.status)}>{svc.status}</Badge>
                  </div>
                ))
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 rounded-2xl box-muted p-4">
        <div className="flex items-center justify-between">
          <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">Aktywne operacje</p>
          <span className="text-xs text-zinc-400">/ws/events</span>
        </div>
        <div className="mt-3 space-y-2">
          {latestEvents.length === 0 ? (
            <p className="text-xs text-zinc-500">Brak sygnałów w kolejce.</p>
          ) : (
            latestEvents.map((evt) => (
              <ListCard
                key={evt.id}
                title={deriveEventTitle(evt.payload)}
                subtitle={deriveEventDescription(evt.payload)}
                badge={<Badge tone="neutral">{new Date(evt.ts).toLocaleTimeString()}</Badge>}
              />
            ))
          )}
        </div>
      </div>
    </Panel>
  );
}

function groupServices(services: ServiceStatus[]) {
  const buckets: Record<string, ServiceStatus[]> = {
    "Agent Core": [],
    "Integracje": [],
    "System": [],
  };
  services.forEach((svc) => {
    if (svc.name.toLowerCase().includes("agent") || svc.name.toLowerCase().includes("llm")) {
      buckets["Agent Core"].push(svc);
    } else if (svc.name.toLowerCase().includes("watch") || svc.name.toLowerCase().includes("daemon")) {
      buckets["Integracje"].push(svc);
    } else {
      buckets["System"].push(svc);
    }
  });
  return Object.entries(buckets).map(([name, list]) => ({
    name,
    services: list,
    statusTone: deduceTone(list),
    statusLabel: summaryLabel(list),
  }));
}

function deduceTone(services: ServiceStatus[]) {
  if (services.length === 0) return "neutral" as const;
  if (services.some((svc) => (svc.status || "").toLowerCase().includes("down"))) return "danger" as const;
  if (services.some((svc) => (svc.status || "").toLowerCase().includes("degraded"))) return "warning" as const;
  return "success" as const;
}

function summaryLabel(services: ServiceStatus[]) {
  if (services.length === 0) return "Brak danych";
  const healthy = services.filter((svc) => (svc.status || "").toLowerCase().includes("healthy")).length;
  return `${healthy}/${services.length} online`;
}

function deriveEventTitle(payload: unknown) {
  if (typeof payload === "string") return payload.slice(0, 60);
  if (isRecord(payload) && typeof payload.event === "string") return payload.event;
  if (isRecord(payload) && typeof payload.type === "string") return payload.type;
  return "Sygnał systemowy";
}

function deriveEventDescription(payload: unknown) {
  if (isRecord(payload) && typeof payload.detail === "string") {
    return payload.detail;
  }
  return typeof payload === "string" ? payload : "Patrz konsola.";
}

function serviceTone(status?: string) {
  if (!status) return "neutral" as const;
  const lower = status.toLowerCase();
  if (lower.includes("healthy")) return "success" as const;
  if (lower.includes("degraded") || lower.includes("warn")) return "warning" as const;
  if (lower.includes("down") || lower.includes("error")) return "danger" as const;
  return "neutral" as const;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";
import {
  useGraphSummary,
  useMetrics,
  useQueueStatus,
  useServiceStatus,
  useTasks,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";

export default function Home() {
  const { data: metrics } = useMetrics();
  const { data: tasks } = useTasks();
  const { data: queue } = useQueueStatus();
  const { data: services } = useServiceStatus();
  const { data: graph } = useGraphSummary();
  const { connected, entries } = useTelemetryFeed();

  const taskItems = (tasks || []).slice(0, 4);

  return (
    <div className="flex flex-col gap-8">
      <section className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-sm text-[--color-muted]">Cockpit Next</p>
            <h1 className="mt-2 text-3xl font-semibold">
              Kontroluj Venom w czasie rzeczywistym
            </h1>
            <p className="mt-3 max-w-2xl text-sm text-[--color-muted]">
              Nowy frontend w Next.js: telemetria WebSocket, kolejka zadań, modele,
              git, historia i governance w jednym miejscu.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge tone="success">WS: /ws/events</Badge>
              <Badge tone="neutral">API: /api/v1/**</Badge>
              <Badge tone="warning">Lab Mode ready</Badge>
            </div>
          </div>
          <div className="grid w-full max-w-md grid-cols-2 gap-3">
            <StatCard
              label="Zadania"
              value={metrics?.tasks?.created ?? "—"}
              hint="total (API /tasks)"
            />
            <StatCard
              label="Success rate"
              value={
                metrics?.tasks?.success_rate !== undefined
                  ? `${metrics.tasks.success_rate}%`
                  : "—"
              }
              hint="metrics.success_rate"
              accent="green"
            />
            <StatCard
              label="Uptime"
              value={
                metrics?.uptime_seconds !== undefined
                  ? formatUptime(metrics.uptime_seconds)
                  : "—"
              }
              hint="metrics.uptime_seconds"
            />
            <StatCard
              label="Kolejka"
              value={
                queue
                  ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}`
                  : "—"
              }
              hint="active / limit"
              accent="blue"
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-3">
        <Panel
          title="Live feed (WS)"
          description="Strumień z /ws/events z auto-reconnect i filtrami logów."
          action={
            <Badge tone={connected ? "success" : "warning"}>
              {connected ? "Połączono" : "Rozłączony"}
            </Badge>
          }
        >
          <div className="space-y-2 text-sm text-[--color-muted]">
            {entries.length === 0 && (
              <p className="text-[--color-muted]">Brak danych z telemetrii.</p>
            )}
            {entries.slice(0, 6).map((entry) => (
              <div
                key={entry.id}
                className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2"
              >
                <p className="text-[11px] text-[--color-muted]">
                  {new Date(entry.ts).toLocaleTimeString()}
                </p>
                <pre className="mt-1 max-h-24 overflow-auto text-xs text-slate-200">
                  {formatPayload(entry.payload)}
                </pre>
              </div>
            ))}
          </div>
        </Panel>

        <Panel
          title="Aktywne zadania"
          description="Dane z /api/v1/tasks + historia /history/requests."
        >
          <ul className="space-y-3">
            {taskItems.length === 0 && (
              <li className="rounded-lg border border-[--color-border] bg-white/5 p-3 text-sm text-[--color-muted]">
                Brak zadań – spróbuj wysłać nowe żądanie w Cockpit.
              </li>
            )}
            {taskItems.map((task) => (
              <li
                key={task.task_id}
                className="rounded-lg border border-[--color-border] bg-white/5 p-3"
              >
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{task.content}</span>
                  <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                </div>
                <p className="mt-1 text-xs text-[--color-muted]">
                  {task.created_at
                    ? new Date(task.created_at).toLocaleString()
                    : "—"}
                </p>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title="Aktywne operacje"
          description="Kolejka governance, model manager, repo sync."
        >
          <ul className="space-y-2 text-sm text-[--color-muted]">
            {(services || []).length === 0 && (
              <li className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2">
                Brak danych o statusie usług.
              </li>
            )}
            {(services || []).map((svc) => (
              <li
                key={svc.name}
                className="flex items-center justify-between rounded-lg border border-[--color-border] bg-white/5 px-3 py-2"
              >
                <span className="text-white">{svc.name}</span>
                <Badge tone={serviceTone(svc.status)}>{svc.status}</Badge>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel
        title="Mapa funkcji do przeniesienia"
        description="Parowanie starego Cockpitu z nowymi komponentami Next.js"
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
            <h4 className="text-sm font-semibold text-white">Widoki</h4>
            <ul className="mt-2 space-y-2 text-sm text-[--color-muted]">
              <li>• Cockpit → strona główna</li>
              <li>• Flow Inspector → /flow</li>
              <li>• Brain → /brain (graf Cytoscape)</li>
              <li>• War Room → /strategy</li>
            </ul>
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
            <h4 className="text-sm font-semibold text-white">Integracje</h4>
            <ul className="mt-2 space-y-2 text-sm text-[--color-muted]">
              <li>• WS: /ws/events (telemetria)</li>
              <li>• REST: /api/v1/tasks, /metrics, /queue, /models, /git</li>
              <li>• Markdown/HTML render (DOMPurify + marked)</li>
              <li>
                • Graph: /api/v1/graph/summary, /graph/scan (nodes:{" "}
                {graph?.nodes ?? "—"})
              </li>
            </ul>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function statusTone(status: string | undefined) {
  if (!status) return "neutral" as const;
  if (status === "COMPLETED") return "success" as const;
  if (status === "PROCESSING") return "warning" as const;
  if (status === "FAILED") return "danger" as const;
  return "neutral" as const;
}

function serviceTone(status: string | undefined) {
  if (!status) return "neutral" as const;
  const s = status.toLowerCase();
  if (s.includes("healthy") || s.includes("ok")) return "success" as const;
  if (s.includes("degraded") || s.includes("warn")) return "warning" as const;
  if (s.includes("down") || s.includes("error") || s.includes("fail"))
    return "danger" as const;
  return "neutral" as const;
}

function formatUptime(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function formatPayload(payload: unknown) {
  if (typeof payload === "string") return payload;
  try {
    return JSON.stringify(payload, null, 2);
  } catch {
    return String(payload);
  }
}

import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";

const stubTasks = [
  { title: "Research: Python 3.12", status: "COMPLETED", time: "2m ago" },
  { title: "Sync repo & apply patch", status: "PROCESSING", time: "30s ago" },
  { title: "Run E2E smoke", status: "PENDING", time: "queued" },
];

const stubOperations = [
  "WS telemetry pipeline ready",
  "Queue governance endpoints discovered",
  "Model registry API reachable",
];

export default function Home() {
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
            <StatCard label="Zadania" value="128" hint="total (API /tasks)" />
            <StatCard
              label="Success rate"
              value="92%"
              hint="metrics.success_rate"
              accent="green"
            />
            <StatCard label="Uptime" value="4h 11m" hint="metrics.uptime_seconds" />
            <StatCard
              label="Kolejka"
              value="2 / 10"
              hint="active / limit"
              accent="blue"
            />
          </div>
        </div>
      </section>

      <div className="grid gap-6 md:grid-cols-3">
        <Panel
          title="Live feed (WS)"
          description="Docelowo strumień z /ws/events z auto-reconnect i filtrami logów."
        >
          <div className="space-y-3 text-sm text-[--color-muted]">
            <p>• Połącz z WS → streamuj AGENT_ACTION / SYSTEM_LOG.</p>
            <p>• Wyświetlaj 100 ostatnich wpisów z opcją pin/clear.</p>
            <p>• Reconnect z backoff (zaimplementowany w VenomWebSocket).</p>
          </div>
        </Panel>

        <Panel
          title="Aktywne zadania"
          description="Dane z /api/v1/tasks + historia /history/requests."
          action={<Badge tone="neutral">stub</Badge>}
        >
          <ul className="space-y-3">
            {stubTasks.map((task) => (
              <li
                key={task.title}
                className="rounded-lg border border-[--color-border] bg-white/5 p-3"
              >
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium">{task.title}</span>
                  <Badge
                    tone={
                      task.status === "COMPLETED"
                        ? "success"
                        : task.status === "PROCESSING"
                          ? "warning"
                          : "neutral"
                    }
                  >
                    {task.status}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-[--color-muted]">{task.time}</p>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel
          title="Aktywne operacje"
          description="Kolejka governance, model manager, repo sync."
        >
          <ul className="space-y-2 text-sm text-[--color-muted]">
            {stubOperations.map((item) => (
              <li
                key={item}
                className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2"
              >
                {item}
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
              <li>• Graph: /api/v1/graph/summary, /graph/scan</li>
            </ul>
          </div>
        </div>
      </Panel>
    </div>
  );
}

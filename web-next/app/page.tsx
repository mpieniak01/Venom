"use client";

import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";
import {
  emergencyStop,
  purgeQueue,
  sendTask,
  toggleQueue,
  useGraphSummary,
  useMetrics,
  useQueueStatus,
  useServiceStatus,
  useTasks,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useState } from "react";

export default function Home() {
  const [taskContent, setTaskContent] = useState("");
  const [labMode, setLabMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const { data: metrics } = useMetrics();
  const { data: tasks, refresh: refreshTasks } = useTasks();
  const { data: queue, refresh: refreshQueue } = useQueueStatus();
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
        title="Nowe zadanie"
        description="Wyślij polecenie do Orchestratora (POST /api/v1/tasks)."
        action={
          <div className="flex items-center gap-2 text-xs text-[--color-muted]">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={labMode}
                onChange={(e) => setLabMode(e.target.checked)}
              />
              Lab Mode (nie zapisuj lekcji)
            </label>
          </div>
        }
      >
        <div className="space-y-3">
          <textarea
            className="min-h-[100px] w-full rounded-xl border border-[--color-border] bg-white/5 p-3 text-sm text-white outline-none focus:border-[--color-accent]"
            placeholder="Opisz zadanie..."
            value={taskContent}
            onChange={(e) => setTaskContent(e.target.value)}
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={async () => {
                if (!taskContent.trim()) {
                  setMessage("Podaj treść zadania.");
                  return;
                }
                setSending(true);
                setMessage(null);
                try {
                  const res = await sendTask(taskContent.trim(), !labMode);
                  setMessage(`Wysłano zadanie: ${res.task_id}`);
                  setTaskContent("");
                  refreshTasks();
                  refreshQueue();
                } catch (err) {
                  setMessage(
                    err instanceof Error ? err.message : "Nie udało się wysłać zadania",
                  );
                } finally {
                  setSending(false);
                }
              }}
              disabled={sending}
              className="rounded-lg bg-[--color-accent] px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-purple-900/30 transition hover:-translate-y-[1px] hover:shadow-purple-800/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {sending ? "Wysyłanie..." : "Wyślij"}
            </button>
            <button
              onClick={() => setTaskContent("")}
              className="rounded-lg border border-[--color-border] px-4 py-2 text-sm text-[--color-muted] hover:bg-white/5"
            >
              Wyczyść
            </button>
            {message && (
              <span className="text-sm text-[--color-muted]">{message}</span>
            )}
          </div>
        </div>
      </Panel>

      <Panel
        title="Queue governance"
        description="Zarządzanie kolejką zadań (/api/v1/queue/*)."
        action={
          <Badge tone={queue?.paused ? "warning" : "success"}>
            {queue?.paused ? "Wstrzymana" : "Aktywna"}
          </Badge>
        }
      >
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
            <p className="text-sm text-white">Stan kolejki</p>
            <p className="text-xs text-[--color-muted]">
              Active: {queue?.active ?? "—"} | Pending: {queue?.pending ?? "—"} | Limit:{" "}
              {queue?.limit ?? "∞"}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-white/5 px-4 py-2 text-sm text-white border border-[--color-border] hover:bg-white/10"
              onClick={async () => {
                try {
                  await toggleQueue(queue?.paused ?? false);
                  refreshQueue();
                } catch (err) {
                  setMessage(
                    err instanceof Error
                      ? err.message
                      : "Nie udało się zmienić stanu kolejki",
                  );
                }
              }}
            >
              {queue?.paused ? "Wznów kolejkę" : "Wstrzymaj kolejkę"}
            </button>
            <button
              className="rounded-lg bg-amber-500/20 px-4 py-2 text-sm text-amber-100 border border-amber-500/40 hover:bg-amber-500/30"
              onClick={async () => {
                if (!confirm("Wyczyścić oczekujące zadania?")) return;
                try {
                  await purgeQueue();
                  refreshQueue();
                  refreshTasks();
                } catch (err) {
                  setMessage(
                    err instanceof Error ? err.message : "Nie udało się wyczyścić kolejki",
                  );
                }
              }}
            >
              Purge queue
            </button>
            <button
              className="rounded-lg bg-rose-600/25 px-4 py-2 text-sm text-rose-100 border border-rose-500/40 hover:bg-rose-600/35"
              onClick={async () => {
                if (
                  !confirm(
                    "Awaryjne zatrzymanie zatrzyma wszystkie zadania. Kontynuować?",
                  )
                )
                  return;
                try {
                  await emergencyStop();
                  refreshQueue();
                  refreshTasks();
                } catch (err) {
                  setMessage(
                    err instanceof Error
                      ? err.message
                      : "Nie udało się wykonać awaryjnego stopu",
                  );
                }
              }}
            >
              Emergency stop
            </button>
          </div>
        </div>
      </Panel>

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

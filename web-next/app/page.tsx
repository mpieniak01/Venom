"use client";

import { Badge } from "@/components/ui/badge";
import { Panel, StatCard } from "@/components/ui/panel";
import {
  emergencyStop,
  fetchHistoryDetail,
  fetchMarkdownContent,
  gitSync,
  gitUndo,
  installModel,
  purgeQueue,
  sendTask,
  setAutonomy,
  setCostMode,
  switchModel,
  toggleQueue,
  useAutonomyLevel,
  useCostMode,
  useGraphSummary,
  useHistory,
  useMarkdownLogs,
  useMetrics,
  useModels,
  useQueueStatus,
  useTokenMetrics,
  useGitStatus,
  useServiceStatus,
  useTasks,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import Chart from "chart.js/auto";
import { useEffect, useRef, useState } from "react";
import type { HistoryRequestDetail } from "@/lib/types";

export default function Home() {
  const [taskContent, setTaskContent] = useState("");
  const [labMode, setLabMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [modelName, setModelName] = useState("");
  const [historyDetail, setHistoryDetail] = useState<HistoryRequestDetail | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [tokenHistory, setTokenHistory] = useState<TokenSample[]>([]);

  const { data: metrics } = useMetrics();
  const { data: tasks, refresh: refreshTasks } = useTasks();
  const { data: queue, refresh: refreshQueue } = useQueueStatus();
  const { data: services } = useServiceStatus();
  const { data: graph } = useGraphSummary();
  const { data: models, refresh: refreshModels } = useModels();
  const { data: git, refresh: refreshGit } = useGitStatus();
  const { data: tokenMetrics } = useTokenMetrics();
  const { data: costMode, refresh: refreshCost } = useCostMode();
  const { data: autonomy, refresh: refreshAutonomy } = useAutonomyLevel();
  const { data: history } = useHistory(6);
  const { connected, entries } = useTelemetryFeed();

  useEffect(() => {
    if (tokenMetrics?.total_tokens === undefined) return;
    setTokenHistory((prev) => {
      const next = [
        ...prev,
        {
          timestamp: new Date().toLocaleTimeString(),
          value: tokenMetrics.total_tokens ?? 0,
        },
      ];
      return next.slice(-20);
    });
  }, [tokenMetrics?.total_tokens]);

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
              <LogEntry key={entry.id} entry={entry} />
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

      <div className="grid gap-6 md:grid-cols-2">
        <Panel
          title="Modele"
          description="Lista modeli lokalnych i aktywacja (/api/v1/models)."
          action={<Badge tone="neutral">{models?.count ?? 0} modeli</Badge>}
        >
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                className="w-full max-w-xs rounded-lg border border-[--color-border] bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[--color-accent]"
                placeholder="Nazwa modelu do instalacji"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
              />
              <button
                className="rounded-lg bg-white/5 px-4 py-2 text-sm text-white border border-[--color-border] hover:bg-white/10"
                onClick={async () => {
                  if (!modelName.trim()) {
                    setMessage("Podaj nazwę modelu.");
                    return;
                  }
                  try {
                    const res = await installModel(modelName.trim());
                    setMessage(res.message || "Rozpoczęto instalację.");
                    setModelName("");
                    refreshModels();
                  } catch (err) {
                    setMessage(err instanceof Error ? err.message : "Błąd instalacji");
                  }
                }}
              >
                Zainstaluj
              </button>
              <button
                className="rounded-lg bg-white/5 px-4 py-2 text-sm text-white border border-[--color-border] hover:bg-white/10"
                onClick={() => {
                  refreshModels();
                  refreshTasks();
                }}
              >
                Odśwież
              </button>
            </div>
            <div className="space-y-2">
              {(models?.models || []).length === 0 && (
                <p className="text-sm text-[--color-muted]">Brak modeli.</p>
              )}
              {(models?.models || []).map((model) => (
                <div
                  key={model.name}
                  className="flex items-center justify-between rounded-lg border border-[--color-border] bg-white/5 px-3 py-2"
                >
                  <div>
                    <p className="text-sm font-semibold text-white">{model.name}</p>
                    <p className="text-xs text-[--color-muted]">
                      {model.size_gb ? `${model.size_gb} GB` : "—"}{" "}
                      {model.source ? ` • ${model.source}` : ""}
                    </p>
                  </div>
                  <button
                    className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                      model.active
                        ? "bg-[--color-accent-2]/20 text-emerald-100 border border-emerald-400/30"
                        : "bg-white/5 text-white border border-[--color-border]"
                    }`}
                    onClick={async () => {
                      try {
                        await switchModel(model.name);
                        setMessage(`Aktywowano model ${model.name}`);
                        refreshModels();
                      } catch (err) {
                        setMessage(
                          err instanceof Error
                            ? err.message
                            : "Nie udało się przełączyć modelu",
                        );
                      }
                    }}
                  >
                    {model.active ? "Aktywny" : "Ustaw jako aktywny"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </Panel>

        <Panel
          title="Repozytorium"
          description="Status i szybkie akcje git (/api/v1/git/*)."
          action={<Badge tone="neutral">{git?.branch ?? "brak"}</Badge>}
        >
          <p className="text-sm text-[--color-muted]">
            Zmiany: {git?.changes ?? git?.status ?? "n/a"}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="rounded-lg bg-white/5 px-4 py-2 text-sm text-white border border-[--color-border] hover:bg-white/10"
              onClick={async () => {
                try {
                  await gitSync();
                  setMessage("Synchronizacja repo zakończona.");
                  refreshGit();
                } catch (err) {
                  setMessage(
                    err instanceof Error ? err.message : "Błąd synchronizacji",
                  );
                }
              }}
            >
              Sync
            </button>
            <button
              className="rounded-lg bg-amber-500/20 px-4 py-2 text-sm text-amber-100 border border-amber-500/40 hover:bg-amber-500/30"
              onClick={async () => {
                if (!confirm("Cofnąć lokalne zmiany?")) return;
                try {
                  await gitUndo();
                  setMessage("Cofnięto zmiany.");
                  refreshGit();
                } catch (err) {
                  setMessage(err instanceof Error ? err.message : "Błąd git undo");
                }
              }}
            >
              Undo
            </button>
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel
          title="Cost Mode"
          description="Global Cost Guard (/api/v1/system/cost-mode)."
          action={
            <Badge tone={costMode?.enabled ? "warning" : "success"}>
              {costMode?.enabled ? "Paid (Pro)" : "Eco"}
            </Badge>
          }
        >
          <p className="text-sm text-[--color-muted]">
            Provider: {costMode?.provider ?? "n/a"}
          </p>
          <button
            className="mt-3 rounded-lg bg-white/5 px-4 py-2 text-sm text-white border border-[--color-border] hover:bg-white/10"
            onClick={async () => {
              try {
                await setCostMode(!(costMode?.enabled ?? false));
                refreshCost();
              } catch (err) {
                setMessage(
                  err instanceof Error ? err.message : "Błąd zmiany cost mode",
                );
              }
            }}
          >
            Przełącz na {costMode?.enabled ? "Eco" : "Paid"}
          </button>
        </Panel>

        <Panel
          title="Autonomy"
          description="Poziom AutonomyGate (/api/v1/system/autonomy)."
          action={<Badge tone="neutral">{autonomy?.current_level_name ?? "n/a"}</Badge>}
        >
          <p className="text-sm text-[--color-muted]">
            Aktualny poziom: {autonomy?.current_level ?? "—"} •{" "}
            {autonomy?.risk_level ?? ""}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {[0, 10, 20, 30, 40].map((level) => (
              <button
                key={level}
                className={`rounded-lg px-3 py-2 text-xs ${
                  autonomy?.current_level === level
                    ? "bg-[--color-accent]/30 text-white border border-[--color-border]"
                    : "bg-white/5 text-white border border-[--color-border] hover:bg-white/10"
                }`}
                onClick={async () => {
                  try {
                    await setAutonomy(level);
                    refreshAutonomy();
                  } catch (err) {
                    setMessage(
                      err instanceof Error
                        ? err.message
                        : "Nie udało się zmienić poziomu autonomii",
                    );
                  }
                }}
              >
                {level}
              </button>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="Tokenomics" description="Zużycie tokenów (/api/v1/metrics/tokens).">
          <div className="grid grid-cols-2 gap-3 text-sm text-[--color-muted]">
            <TokenRow label="Total" value={tokenMetrics?.total_tokens} />
            <TokenRow label="Prompt" value={tokenMetrics?.prompt_tokens} />
            <TokenRow label="Completion" value={tokenMetrics?.completion_tokens} />
            <TokenRow label="Cached" value={tokenMetrics?.cached_tokens} />
          </div>
        </Panel>
        <Panel
          title="Trend tokenów"
          description="Chart.js – próbki z /api/v1/metrics/tokens (ostatnie 20)."
        >
          {tokenHistory.length < 2 ? (
            <p className="text-sm text-[--color-muted]">
              Za mało danych do wizualizacji. Poczekaj na kolejne odczyty.
            </p>
          ) : (
            <TokenChart history={tokenHistory} />
          )}
        </Panel>

        <Panel
          title="Historia"
          description="Ostatnie requesty (/api/v1/history/requests). Kliknij, aby zobaczyć szczegóły."
        >
          <div className="space-y-2 text-sm">
            {(history || []).length === 0 && (
              <p className="text-[--color-muted]">Brak historii.</p>
            )}
            {(history || []).map((item) => (
              <button
                key={item.request_id}
                className="w-full rounded-lg border border-[--color-border] bg-white/5 px-3 py-2 text-left hover:bg-white/10"
                onClick={async () => {
                  setLoadingHistory(true);
                  try {
                    const detail = await fetchHistoryDetail(item.request_id);
                    setHistoryDetail(detail);
                    setHistoryError(null);
                  } catch (err) {
                    setHistoryDetail(null);
                    setHistoryError(
                      err instanceof Error
                        ? err.message
                        : "Nie udało się pobrać szczegółów",
                    );
                  } finally {
                    setLoadingHistory(false);
                  }
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white line-clamp-1">
                    {item.prompt}
                  </span>
                  <Badge tone={statusTone(item.status)}>{item.status}</Badge>
                </div>
                <p className="text-xs text-[--color-muted]">
                  {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
                </p>
              </button>
            ))}
            {loadingHistory && (
              <p className="text-xs text-[--color-muted]">Ładowanie szczegółów...</p>
            )}
            {historyError && (
              <p className="text-xs text-rose-300">{historyError}</p>
            )}
            {historyDetail && (
              <div className="mt-3 rounded-lg border border-[--color-border] bg-black/30 p-3 text-xs text-slate-200">
                <p className="text-sm text-white">Request: {historyDetail.request_id}</p>
                <p className="text-[--color-muted]">
                  Status: {historyDetail.status} • Czas trwania:{" "}
                  {historyDetail.duration_seconds
                    ? `${historyDetail.duration_seconds.toFixed(1)}s`
                    : "n/a"}
                </p>
                <div className="mt-2 max-h-60 overflow-auto">
                  <ol className="space-y-1">
                    {(historyDetail.steps || []).map((step, idx) => (
                      <li
                        key={`${historyDetail.request_id}-${idx}`}
                        className="rounded border border-[--color-border] bg-white/5 px-2 py-1 text-white"
                      >
                        <span className="font-semibold">{step.component || "step"}</span>:{" "}
                        {step.action || step.details || ""}
                      </li>
                    ))}
                    {(historyDetail.steps || []).length === 0 && (
                      <li className="text-[--color-muted]">Brak kroków w historii.</li>
                    )}
                  </ol>
                </div>
              </div>
            )}
          </div>
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

function LogEntry({ entry }: { entry: LogEntryType }) {
  const payload = entry.payload;
  const text =
    typeof payload === "string"
      ? payload
      : payload && typeof payload === "object"
        ? (payload as any).message || JSON.stringify(payload, null, 2)
        : String(payload);
  const level =
    typeof payload === "object" && payload && "level" in payload
      ? String((payload as any).level).toUpperCase()
      : "INFO";
  const type =
    typeof payload === "object" && payload && "type" in payload
      ? String((payload as any).type)
      : "log";

  return (
    <div className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2">
      <div className="flex items-center justify-between text-[11px] text-[--color-muted]">
        <span>{new Date(entry.ts).toLocaleTimeString()}</span>
        <span>
          {type} • {level}
        </span>
      </div>
      <pre className="mt-1 max-h-24 overflow-auto text-xs text-slate-200 whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  );
}

type LogEntryType = {
  id: string;
  ts: number;
  payload: unknown;
};

type TokenRowProps = { label: string; value?: number };

function TokenRow({ label, value }: TokenRowProps) {
  return (
    <div className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2">
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">{label}</p>
      <p className="mt-1 text-lg font-semibold text-white">
        {value !== undefined ? value : "—"}
      </p>
    </div>
  );
}

type TokenSample = { timestamp: string; value: number };

function TokenChart({ history }: { history: TokenSample[] }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    if (!canvasRef.current) return;
    const labels = history.map((h) => h.timestamp);
    const dataPoints = history.map((h) => h.value);

    if (chartRef.current) {
      chartRef.current.data.labels = labels;
      chartRef.current.data.datasets[0].data = dataPoints;
      chartRef.current.update();
      return;
    }

    chartRef.current = new Chart(canvasRef.current, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Total tokens",
            data: dataPoints,
            borderColor: "#8b5cf6",
            backgroundColor: "rgba(139,92,246,0.2)",
            tension: 0.3,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            labels: {
              color: "#e5e7eb",
            },
          },
        },
        scales: {
          x: {
            ticks: { color: "#94a3b8", maxTicksLimit: 5 },
            grid: { color: "rgba(148,163,184,0.2)" },
          },
          y: {
            ticks: { color: "#94a3b8" },
            grid: { color: "rgba(148,163,184,0.2)" },
          },
        },
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [history]);

  return <canvas ref={canvasRef} className="w-full" />;
}

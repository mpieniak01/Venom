"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { ListCard } from "@/components/ui/list-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { MarkdownPreview } from "@/components/ui/markdown";
import { ConversationBubble } from "@/components/cockpit/conversation-bubble";
import { MacroCard, PinnedLogCard } from "@/components/cockpit/macro-card";
import { ModelListItem, RepoActionCard } from "@/components/cockpit/model-card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  fetchHistoryDetail,
  gitSync,
  gitUndo,
  installModel,
  sendTask,
  switchModel,
  useGraphSummary,
  useHistory,
  useMetrics,
  useModels,
  useQueueStatus,
  useTokenMetrics,
  useGitStatus,
  useServiceStatus,
  useTasks,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import type { Chart } from "chart.js/auto";
import { useEffect, useMemo, useRef, useState } from "react";
import type { HistoryRequestDetail, ServiceStatus } from "@/lib/types";
import { LogEntryType, isLogPayload } from "@/lib/logs";
import { statusTone } from "@/lib/status";
import { AnimatePresence, motion } from "framer-motion";
import { CockpitMetricCard, CockpitTokenCard } from "@/components/cockpit/kpi-card";
import { Bot, Pin, PinOff, Inbox, Package } from "lucide-react";
import Link from "next/link";
import { HistoryList } from "@/components/history/history-list";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { RecentRequestList } from "@/components/tasks/recent-request-list";
import { QueueStatusCard } from "@/components/queue/queue-status-card";
import { QuickActions } from "@/components/layout/quick-actions";

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
  const [macroSending, setMacroSending] = useState<string | null>(null);
  const [customMacros, setCustomMacros] = useState<MacroAction[]>([]);
  const [newMacro, setNewMacro] = useState({
    label: "",
    description: "",
    content: "",
  });
  const [pinnedLogs, setPinnedLogs] = useState<LogEntryType[]>([]);
  const [logFilter, setLogFilter] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [copyStepsMessage, setCopyStepsMessage] = useState<string | null>(null);
  const [quickActionsOpen, setQuickActionsOpen] = useState(false);
  const [exportingPinned, setExportingPinned] = useState(false);
  const [gitAction, setGitAction] = useState<"sync" | "undo" | null>(null);

  const { data: metrics } = useMetrics();
  const { data: tasks, refresh: refreshTasks } = useTasks();
  const { data: queue, refresh: refreshQueue } = useQueueStatus();
  const { data: services } = useServiceStatus();
  const { data: graph } = useGraphSummary();
  const { data: models, refresh: refreshModels } = useModels();
  const { data: git, refresh: refreshGit } = useGitStatus();
  const { data: tokenMetrics } = useTokenMetrics();
  const { data: history } = useHistory(6);
  const { connected, entries } = useTelemetryFeed();

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem(MACRO_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MacroAction[];
        if (Array.isArray(parsed)) {
          setCustomMacros(parsed);
        }
      }
    } catch (err) {
      console.error("Nie udało się odczytać makr z localStorage:", err);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(MACRO_STORAGE_KEY, JSON.stringify(customMacros));
    } catch (err) {
      console.error("Nie udało się zapisać makr do localStorage:", err);
    }
  }, [customMacros]);

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

  const tasksPreview = (tasks || []).slice(0, 4);
  const fallbackAgents: ServiceStatus[] = [
    { name: "Orchestrator", status: "healthy", detail: "Tworzenie i analiza zadań" },
    { name: "Watcher", status: "degraded", detail: "Monitoring repo / usług" },
    { name: "Gardener", status: "healthy", detail: "Lekcje i graf wiedzy" },
  ];
  const agentDeck = services && services.length > 0 ? services : fallbackAgents;
  const chatMessages = useMemo(
    () =>
      (history || []).map((item, index) => ({
        id: item.request_id,
        text: item.prompt,
        status: item.status,
        created_at: item.created_at,
        role: index % 2 === 0 ? "user" : "assistant",
      })),
    [history],
  );
  const logEntries = entries.slice(0, 8);
  const tokenSplits = [
    { label: "Prompt", value: tokenMetrics?.prompt_tokens ?? 0 },
    { label: "Completion", value: tokenMetrics?.completion_tokens ?? 0 },
    { label: "Cached", value: tokenMetrics?.cached_tokens ?? 0 },
  ].filter((item) => item.value && item.value > 0);
  const totalTokens = tokenMetrics?.total_tokens ?? 0;
  const promptTokens = tokenMetrics?.prompt_tokens ?? 0;
  const completionTokens = tokenMetrics?.completion_tokens ?? 0;
  const cachedTokens = tokenMetrics?.cached_tokens ?? 0;
  const tasksCreated = metrics?.tasks?.created ?? 0;
  const successRateValue = metrics?.tasks?.success_rate;
  const successRate = typeof successRateValue === "number" ? successRateValue : null;
  const avgTokensPerTask =
    totalTokens > 0 && tasksCreated > 0
      ? Math.round(totalTokens / Math.max(tasksCreated, 1))
      : null;
  const promptShare =
    totalTokens > 0 ? Math.round((promptTokens / totalTokens) * 100) : null;
  const completionShare =
    totalTokens > 0 ? Math.round((completionTokens / totalTokens) * 100) : null;
  const cachedShare =
    totalTokens > 0 ? Math.round((cachedTokens / totalTokens) * 100) : null;
  const lastTokenSample =
    tokenHistory.length > 0 ? tokenHistory[tokenHistory.length - 1]?.value ?? null : null;
  const prevTokenSample =
    tokenHistory.length > 1 ? tokenHistory[tokenHistory.length - 2]?.value ?? null : null;
  const tokenTrendDelta =
    lastTokenSample !== null && prevTokenSample !== null
      ? lastTokenSample - prevTokenSample
      : null;
  const tokenTrendMagnitude =
    tokenTrendDelta !== null ? Math.abs(tokenTrendDelta).toLocaleString("pl-PL") : null;
  const tokenTrendLabel =
    tokenTrendDelta === null
      ? "Stabilny"
      : tokenTrendDelta > 0
        ? `+${tokenTrendDelta.toLocaleString("pl-PL")}↑`
        : `${tokenTrendDelta.toLocaleString("pl-PL")}↓`;
  const promptCompletionRatio =
    completionTokens > 0
      ? (promptTokens / Math.max(completionTokens, 1)).toFixed(1)
      : promptTokens > 0
        ? "∞"
        : null;

  const graphNodes = graph?.summary?.nodes ?? graph?.nodes ?? "—";
  const graphEdges = graph?.summary?.edges ?? graph?.edges ?? "—";
  const historySummary = useMemo(() => {
    const bucket: Record<string, number> = {};
    (history || []).forEach((item) => {
      const key = item.status || "UNKNOWN";
      bucket[key] = (bucket[key] || 0) + 1;
    });
    return Object.entries(bucket)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [history]);
  const historyStatusEntries = historySummary.map((entry) => ({
    label: entry.name,
    value: entry.value,
  }));
  const macroActions = useMemo<MacroAction[]>(
    () => [
      {
        id: "graph-scan",
        label: "Skanuj graf wiedzy",
        description: "Wywołaj /api/v1/graph/scan i odśwież podgląd Brain.",
        content: "Przeskanuj repozytorium i zaktualizuj graf wiedzy.",
      },
      {
        id: "system-health",
        label: "Status usług",
        description: "Sprawdź /api/v1/system/services i zgłoś anomalie.",
        content:
          "Zbadaj kondycję wszystkich usług Venoma i przygotuj raport o stanie wraz z rekomendacjami.",
      },
      {
        id: "roadmap-sync",
        label: "Roadmap sync",
        description: "Poproś Strategy agenta o aktualizację roadmapy.",
        content:
          "Uzgodnij bieżące zadania z roadmapą i wypisz brakujące milestone'y wraz z datami.",
      },
      {
        id: "git-audit",
        label: "Git audit",
        description: "Analiza repo: zmiany, konflikty, propozycje commitów.",
        content:
          "Przeanalizuj repozytorium git, wypisz niezatwierdzone zmiany i zaproponuj strukturę commitów.",
      },
    ],
    [],
  );
  const modelCount = models?.count ?? models?.models?.length ?? 0;

  const allMacros = useMemo(
    () => [...macroActions, ...customMacros],
    [macroActions, customMacros],
  );

  const handleSend = async () => {
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
  };

  const handleMacroRun = async (macro: { id: string; content: string; label: string }) => {
    if (macroSending) return;
    setMacroSending(macro.id);
    setMessage(null);
    try {
      const res = await sendTask(macro.content, !labMode);
      setMessage(`Makro ${macro.label} wysłane: ${res.task_id}`);
      refreshTasks();
      refreshQueue();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Nie udało się wykonać makra.");
    } finally {
      setMacroSending(null);
    }
  };

  const handleExportPinnedLogs = async () => {
    if (pinnedLogs.length === 0) return;
    setExportingPinned(true);
    try {
      const blob = new Blob(
        [JSON.stringify(pinnedLogs.map((log) => log.payload), null, 2)],
        { type: "application/json" },
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "pinned-logs.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Clipboard error:", err);
    } finally {
      setExportingPinned(false);
    }
  };

  const openRequestDetail = async (requestId: string) => {
    setSelectedRequestId(requestId);
    setDetailOpen(true);
    setHistoryDetail(null);
    setHistoryError(null);
    setCopyStepsMessage(null);
    setLoadingHistory(true);
    try {
      const detail = await fetchHistoryDetail(requestId);
      setHistoryDetail(detail);
    } catch (err) {
      setHistoryError(
        err instanceof Error ? err.message : "Nie udało się pobrać szczegółów",
      );
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCopyDetailSteps = async () => {
    if (!historyDetail?.steps || historyDetail.steps.length === 0) {
      setCopyStepsMessage("Brak danych do skopiowania.");
      setTimeout(() => setCopyStepsMessage(null), 2000);
      return;
    }
    try {
      await navigator.clipboard.writeText(JSON.stringify(historyDetail.steps, null, 2));
      setCopyStepsMessage("Skopiowano kroki.");
    } catch (err) {
      console.error("Clipboard error:", err);
      setCopyStepsMessage("Nie udało się skopiować.");
    } finally {
      setTimeout(() => setCopyStepsMessage(null), 2000);
    }
  };

  const handleGitSync = async () => {
    if (gitAction) return;
    setGitAction("sync");
    try {
      await gitSync();
      setMessage("Synchronizacja repo zakończona.");
      refreshGit();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Błąd synchronizacji");
    } finally {
      setGitAction(null);
    }
  };

  const handleGitUndo = async () => {
    if (gitAction) return;
    if (!confirm("Cofnąć lokalne zmiany?")) return;
    setGitAction("undo");
    try {
      await gitUndo();
      setMessage("Cofnięto zmiany.");
      refreshGit();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Błąd git undo");
    } finally {
      setGitAction(null);
    }
  };

  return (
    <div className="space-y-10 pb-14">
      <SectionHeading
        eyebrow="Dashboard Control"
        title="Centrum Dowodzenia AI"
        description="Monitoruj telemetrię, kolejkę i logi w czasie rzeczywistym – reaguj tak szybko, jak Venom OS."
        as="h1"
        size="lg"
      />
      <section className="grid gap-6 lg:grid-cols-[minmax(0,420px)_1fr]">
        <Panel
          title="Live Feed"
          description="/ws/events stream – ostatnie logi operacyjne"
          action={
            <Badge tone={connected ? "success" : "warning"}>
              {connected ? "Połączono" : "Brak sygnału"}
            </Badge>
          }
        >
          <div className="space-y-4">
            <input
              className="w-full rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-white outline-none placeholder:text-zinc-500"
              placeholder="Filtruj logi..."
              value={logFilter}
              onChange={(e) => setLogFilter(e.target.value)}
            />
            <div className="terminal h-64 overflow-y-auto rounded-2xl border border-emerald-500/15 p-4 text-xs shadow-inner shadow-emerald-400/10">
              {logEntries.length === 0 && (
                <p className="text-emerald-200/70">Oczekiwanie na logi...</p>
              )}
              {logEntries
                .filter((entry) => {
                  if (!logFilter.trim()) return true;
                  const payload = entry.payload;
                  const text =
                    typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
                  return text.toLowerCase().includes(logFilter.toLowerCase());
                })
                .map((entry) => (
                  <LogEntry
                    key={entry.id}
                    entry={entry}
                    pinned={pinnedLogs.some((log) => log.id === entry.id)}
                    onPin={() =>
                      setPinnedLogs((prev) =>
                        prev.some((log) => log.id === entry.id)
                          ? prev.filter((log) => log.id !== entry.id)
                          : [...prev, entry],
                      )
                    }
                  />
                ))}
            </div>
            {pinnedLogs.length > 0 && (
              <div className="rounded-3xl border border-emerald-400/20 bg-gradient-to-br from-emerald-500/20 via-emerald-500/5 to-transparent p-4 text-xs text-white shadow-card">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <p className="text-[11px] uppercase tracking-[0.35em] text-emerald-200/80">
                      Przypięte logi
                    </p>
                    <p className="text-sm text-emerald-100/80">
                      Najważniejsze zdarzenia z kanału /ws/events.
                    </p>
                  </div>
                  <div className="ml-auto flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      size="xs"
                      className="px-3 text-white"
                      disabled={exportingPinned}
                      onClick={handleExportPinnedLogs}
                    >
                      {exportingPinned ? "Eksportuję..." : "Eksportuj JSON"}
                    </Button>
                    <Button
                      variant="danger"
                      size="xs"
                      className="px-3"
                      onClick={() => setPinnedLogs([])}
                    >
                      Wyczyść
                    </Button>
                  </div>
                </div>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {pinnedLogs.map((log) => (
                    <PinnedLogCard
                      key={`pinned-${log.id}`}
                      log={log}
                      onUnpin={() =>
                        setPinnedLogs((prev) => prev.filter((entry) => entry.id !== log.id))
                      }
                    />
                  ))}
                </div>
              </div>
            )}
          </div>
        </Panel>
        <div className="grid gap-6">
          <Panel
            eyebrow="KPI kolejki"
            title="Skuteczność operacji"
            description="Monitoruj SLA tasków i uptime backendu."
          >
            <CockpitMetricCard
              primaryValue={successRate !== null ? `${successRate}%` : "—"}
              secondaryLabel={
                tasksCreated > 0
                  ? `${tasksCreated.toLocaleString("pl-PL")} zadań`
                  : "Brak zadań"
              }
              progress={successRate}
              footer={`Uptime: ${
                metrics?.uptime_seconds !== undefined
                  ? formatUptime(metrics.uptime_seconds)
                  : "—"
              }`}
            />
          </Panel>
          <Panel eyebrow="KPI kolejki" title="Zużycie tokenów" description="Trend prompt/completion/cached.">
            <CockpitTokenCard
              totalValue={totalTokens}
              splits={
                tokenSplits.length > 0
                  ? tokenSplits
                  : [{ label: "Brak danych", value: 0 }]
              }
              chartSlot={
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                      Trend próbek
                    </p>
                    <Badge tone={tokenTrendDelta !== null && tokenTrendDelta < 0 ? "success" : "warning"}>
                      {tokenTrendLabel}
                    </Badge>
                  </div>
                  {tokenHistory.length < 2 ? (
                    <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-xs text-zinc-500">
                      Za mało danych, poczekaj na kolejne odczyty `/metrics/tokens`.
                    </p>
                  ) : (
                    <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                      <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
                        Przebieg ostatnich próbek
                      </p>
                      <div className="mt-3 h-32">
                        <TokenChart history={tokenHistory} height={128} />
                      </div>
                    </div>
                  )}
                </div>
              }
            />
          </Panel>
        </div>
      </section>
      <div className="glass-panel relative flex min-h-[520px] flex-col overflow-hidden px-6 py-6">
          <SectionHeading
            eyebrow="Command Console"
            title="Cockpit AI"
            description="Chat operacyjny z Orchestratora i logami runtime."
            as="h1"
            size="lg"
            className="items-center"
            rightSlot={
              <Badge tone={labMode ? "warning" : "success"}>
                {labMode ? "Lab Mode" : "Prod"}
              </Badge>
            }
          />
          <div className="grid-overlay relative mt-5 flex-1 rounded-3xl border border-white/5 bg-black/30 p-6">
            <div className="flex h-full flex-col">
              <div className="flex-1 space-y-4 overflow-y-auto pr-4">
                <AnimatePresence initial={false}>
                  {chatMessages.length === 0 && (
                    <p className="text-sm text-zinc-500">
                      Brak historii – wyślij pierwsze zadanie.
                    </p>
                  )}
                  {chatMessages.map((msg) => {
                    const isSelected = selectedRequestId === msg.id;
                    return (
                      <motion.div
                        key={msg.id}
                        layout
                        initial={{ opacity: 0, y: 12 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -12 }}
                      >
                        <ConversationBubble
                          role={msg.role === "user" ? "user" : "assistant"}
                          timestamp={msg.created_at}
                          text={msg.text}
                          status={msg.status}
                          requestId={msg.id}
                          isSelected={isSelected}
                          onSelect={() => openRequestDetail(msg.id)}
                        />
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
              <div className="sticky bottom-0 mt-4 border-t border-white/5 pt-4">
                <textarea
                  className="min-h-[120px] w-full rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/60"
                  placeholder="Opisz zadanie dla Venoma..."
                  value={taskContent}
                  onChange={(e) => setTaskContent(e.target.value)}
                />
                <div className="mt-3 flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2 text-xs text-zinc-400">
                    <input
                      type="checkbox"
                      checked={labMode}
                      onChange={(e) => setLabMode(e.target.checked)}
                    />
                    Lab Mode (nie zapisuj lekcji)
                  </label>
                  <div className="ml-auto flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setTaskContent("")}
                      className="text-zinc-300"
                    >
                      Wyczyść
                    </Button>
                    <Button
                      onClick={handleSend}
                      disabled={sending}
                      size="sm"
                      className="px-6"
                    >
                      {sending ? "Wysyłanie..." : "Wyślij"}
                    </Button>
      </div>
    </div>

    <QuickActions open={quickActionsOpen} onOpenChange={setQuickActionsOpen} />
                {message && (
                  <p className="mt-2 text-xs text-amber-300">{message}</p>
                )}
              </div>
            </div>
          </div>
        </div>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,320px)]">
        <div className="glass-panel flex flex-col gap-4">
          <header className="flex items-center gap-3">
            <div className="rounded-2xl bg-violet-600/30 p-3 text-violet-100 shadow-neon">
              <Bot className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                Agenci
              </p>
              <h2 className="text-lg font-semibold text-white">
                Aktywność systemowa
              </h2>
            </div>
          </header>
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="neutral">Węzły: {graphNodes}</Badge>
            <Badge tone="neutral">Krawędzie: {graphEdges}</Badge>
          </div>
          <div className="space-y-3">
            {agentDeck.map((svc) => (
              <div
                key={svc.name}
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/5 px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-semibold text-white">{svc.name}</p>
                  <p className="text-xs text-zinc-500">
                    {svc.detail ?? "Brak opisu"}
                  </p>
                </div>
                <Badge tone={serviceTone(svc.status)}>{svc.status}</Badge>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          label="Zadania"
          value={metrics?.tasks?.created ?? "—"}
          hint="Łącznie utworzonych"
        />
        <StatCard
          label="Success rate"
          value={successRate !== null ? `${successRate}%` : "—"}
          hint="Aktualna skuteczność"
          accent="green"
        />
        <StatCard
          label="Uptime"
          value={
            metrics?.uptime_seconds !== undefined
              ? formatUptime(metrics.uptime_seconds)
              : "—"
          }
          hint="Od startu backendu"
        />
        <StatCard
          label="Kolejka"
          value={
            queue ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}` : "—"
          }
          hint="Active / limit"
          accent="blue"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title="Aktywne zadania"
          description="Podgląd ostatnich requestów /api/v1/tasks."
        >
          <div className="space-y-3">
            {tasksPreview.length === 0 && (
              <EmptyState
                icon={<Inbox className="h-4 w-4" />}
                title="Brak zadań"
                description="Wyślij nowe polecenie, aby pojawiło się na liście."
              />
            )}
            {tasksPreview.map((task) => (
              <ListCard
                key={task.task_id}
                title={task.content}
                subtitle={
                  task.created_at
                    ? new Date(task.created_at).toLocaleString()
                    : "—"
                }
                badge={<Badge tone={statusTone(task.status)}>{task.status}</Badge>}
              />
            ))}
          </div>
        </Panel>

        <Panel
          title="Historia requestów"
          description="Ostatnie /api/v1/history/requests – kliknij, by odczytać szczegóły."
        >
          <HistoryList
            entries={history}
            limit={5}
            selectedId={selectedRequestId}
            onSelect={(entry) => openRequestDetail(entry.request_id)}
            variant="preview"
            viewAllHref="/inspector"
            emptyTitle="Brak historii"
            emptyDescription="Historia requestów pojawi się po wysłaniu zadań."
          />
          {loadingHistory && (
            <p className="mt-2 text-xs text-zinc-500">Ładowanie szczegółów...</p>
          )}
          {historyError && (
            <p className="mt-2 text-xs text-rose-300">{historyError}</p>
          )}
          <p className="mt-2 text-[11px] uppercase tracking-[0.25em] text-zinc-500">
            Kliknij element listy, aby otworzyć panel boczny „Szczegóły requestu”.
          </p>
        </Panel>
      </div>

      <Panel
        title="Makra Cockpitu"
        description="Najczęściej używane polecenia wysyłane jednym kliknięciem."
        action={
          <div className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/5 p-3 text-xs text-white">
            <form
              className="flex flex-col gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (!newMacro.label.trim() || !newMacro.content.trim()) return;
                setCustomMacros((prev) => [
                  ...prev,
                  {
                    id: `custom-${prev.length + 1}`,
                    label: newMacro.label.trim(),
                    description: newMacro.description.trim() || "Makro użytkownika",
                    content: newMacro.content.trim(),
                    custom: true,
                  },
                ]);
                setNewMacro({ label: "", description: "", content: "" });
              }}
            >
              <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-400">
                Dodaj makro
              </p>
              <input
                className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Nazwa"
                value={newMacro.label}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, label: e.target.value }))}
              />
              <input
                className="rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Opis"
                value={newMacro.description}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, description: e.target.value }))}
              />
              <textarea
                className="min-h-[60px] rounded-xl border border-white/10 bg-black/30 px-2 py-1 text-white outline-none placeholder:text-zinc-500"
                placeholder="Treść polecenia / prompt"
                value={newMacro.content}
                onChange={(e) => setNewMacro((prev) => ({ ...prev, content: e.target.value }))}
              />
              <Button type="submit" size="xs" variant="outline" className="px-3">
                Dodaj makro
              </Button>
            </form>
            {customMacros.length > 0 && (
              <Button
                type="button"
                size="xs"
                variant="danger"
                className="px-3"
                onClick={() => setCustomMacros([])}
              >
                Resetuj makra użytkownika
              </Button>
            )}
          </div>
        }
      >
        <div className="grid gap-4 lg:grid-cols-2">
          {allMacros.map((macro) => (
            <MacroCard
              key={macro.id}
              title={macro.label}
              description={macro.description}
              isCustom={macro.custom}
              pending={macroSending === macro.id}
              onRun={() => handleMacroRun(macro)}
              onRemove={
                macro.custom
                  ? () =>
                      setCustomMacros((prev) => prev.filter((item) => item.id !== macro.id))
                  : undefined
              }
            />
          ))}
        </div>
      </Panel>

      <Panel
        title="Task Insights"
        description="Podsumowanie statusów i ostatnich requestów /history/requests."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <TaskStatusBreakdown
            title="Statusy"
            datasetLabel="Ostatnie 50 historii"
            totalLabel="Historia"
            totalValue={(history || []).length}
            entries={historyStatusEntries}
            emptyMessage="Brak historii do analizy."
          />
          <RecentRequestList requests={history} />
        </div>
      </Panel>

      <Panel
        title="Queue governance"
        description="Stan kolejki i szybkie akcje – zarządzaj z jednego miejsca."
        action={
          <Badge tone={queue?.paused ? "warning" : "success"}>
            {queue?.paused ? "Wstrzymana" : "Aktywna"}
          </Badge>
        }
      >
        <div className="space-y-4">
          <QueueStatusCard queue={queue} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              Akcje dostępne w panelu Quick Actions.
            </p>
            <Button
              variant="secondary"
              size="sm"
              className="rounded-full border border-emerald-400/40 bg-emerald-500/10 px-4 text-emerald-100 hover:border-emerald-400/60"
              onClick={() => setQuickActionsOpen(true)}
            >
              ⚡ Otwórz Quick Actions
            </Button>
          </div>
        </div>
      </Panel>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel
          title="Modele"
          description="Lista modeli lokalnych i aktywacja (/api/v1/models)."
          action={
            <span data-testid="models-count">
              <Badge tone="neutral">{modelCount} modeli</Badge>
            </span>
          }
        >
          <div className="space-y-4">
            <div className="rounded-3xl border border-white/10 bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Instalacja</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <input
                  className="w-full flex-1 min-w-[220px] rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-emerald-400/60"
                  placeholder="Nazwa modelu do instalacji"
                  value={modelName}
                  onChange={(e) => setModelName(e.target.value)}
                />
                <Button
                  variant="secondary"
                  size="sm"
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
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    refreshModels();
                    refreshTasks();
                  }}
                >
                  Odśwież
                </Button>
              </div>
              <p className="mt-2 text-xs text-zinc-500">
                Obsługiwany format: `phi3:mini`, `mistral:7b` itd. Instalacja rozpoczyna job w tle.
              </p>
            </div>
            {(models?.models || []).length === 0 ? (
              <EmptyState
                icon={<Package className="h-4 w-4" />}
                title="Brak modeli"
                description="Zainstaluj model, aby rozpocząć pracę."
              />
            ) : (
              <div className="grid gap-3">
                {(models?.models || []).map((model) => (
                  <ModelListItem
                    key={model.name}
                    name={model.name}
                    sizeGb={model.size_gb}
                    source={model.source}
                    active={model.active}
                    onActivate={async () => {
                      if (model.active) return;
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
                  />
                ))}
              </div>
            )}
          </div>
        </Panel>

        <Panel
          title="Repozytorium"
          description="Status i szybkie akcje git (/api/v1/git/*)."
          action={<Badge tone="neutral">{git?.branch ?? "brak"}</Badge>}
        >
          <div className="space-y-4">
            <div className="rounded-3xl border border-white/10 bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">Stan repo</p>
              <p className="mt-2 text-sm text-white">
                {git?.changes ?? git?.status ?? "Brak danych z API."}
              </p>
              <p className="text-xs text-zinc-500">
                Aktualna gałąź: <span className="font-semibold text-white">{git?.branch ?? "—"}</span>
              </p>
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <RepoActionCard
                title="Synchronizacja"
                description="Pobierz/publikuj zmiany i odśwież status pipeline’u."
                pending={gitAction === "sync"}
                onClick={handleGitSync}
              />
              <RepoActionCard
                title="Cofnij zmiany"
                description="Przywróć HEAD do stanu origin – operacja nieodwracalna."
                variant="danger"
                pending={gitAction === "undo"}
                onClick={handleGitUndo}
              />
            </div>
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Panel
          title="Efektywność tokenów"
          description="Średnie zużycie i tempo – KPI na bazie /metrics i /metrics/tokens."
        >
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <TokenEfficiencyStat
                label="Śr./zadanie"
                value={
                  avgTokensPerTask !== null
                    ? `${avgTokensPerTask.toLocaleString("pl-PL")} tok`
                    : "—"
                }
                hint="Total tokens ÷ tasks.created"
              />
              <TokenEfficiencyStat
                label="Delta próbki"
                value={tokenTrendMagnitude ? `${tokenTrendMagnitude} tok` : "—"}
                hint="Różnica między dwoma ostatnimi odczytami"
              />
              <TokenEfficiencyStat
                label="Prompt / completion"
                value={promptCompletionRatio ? `${promptCompletionRatio}x` : "—"}
                hint="Większa wartość = dłuższe prompty"
              />
            </div>
            <div className="rounded-3xl border border-emerald-400/20 bg-gradient-to-br from-emerald-500/20 via-sky-500/10 to-emerald-500/5 p-4 text-sm text-emerald-50">
              <p className="text-xs uppercase tracking-[0.35em] text-emerald-100/70">
                Live próbka
              </p>
              <div className="mt-2 flex flex-wrap items-end gap-3">
                <p className="text-3xl font-semibold text-white">
                  {lastTokenSample !== null
                    ? lastTokenSample.toLocaleString("pl-PL")
                    : "—"}
                </p>
                <Badge tone={tokenTrendDelta !== null && tokenTrendDelta < 0 ? "success" : "warning"}>
                  {tokenTrendLabel}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-emerald-100/70">
                {tokenTrendDelta === null
                  ? "Oczekuję kolejnych danych z /metrics/tokens."
                  : tokenTrendDelta >= 0
                    ? "Zużycie rośnie względem poprzedniej próbki – rozważ throttle."
                    : "Zużycie spadło – cache i makra działają."}
              </p>
            </div>
          </div>
        </Panel>
        <Panel
          title="Cache boost"
          description="Udziały prompt/completion/cached – pozwala ocenić optymalizację."
        >
          <div className="space-y-3">
            <TokenShareBar
              label="Prompt"
              percent={promptShare}
              accent="from-emerald-400/70 via-emerald-500/40 to-emerald-500/10"
            />
            <TokenShareBar
              label="Completion"
              percent={completionShare}
              accent="from-sky-400/70 via-blue-500/40 to-violet-500/10"
            />
            <TokenShareBar
              label="Cached"
              percent={cachedShare}
              accent="from-amber-300/70 via-amber-400/40 to-rose-400/10"
            />
            <p className="text-xs text-[--color-muted]">
              Dane z `/api/v1/metrics/tokens`. Dążymy do wysokiego udziału cache przy zachowaniu
              równowagi prompt/completion.
            </p>
          </div>
        </Panel>
      </div>
      <Sheet
        open={detailOpen}
        onOpenChange={(open) => {
          setDetailOpen(open);
          if (!open) {
            setHistoryError(null);
            setSelectedRequestId(null);
          }
        }}
      >
        <SheetContent>
          <SheetHeader>
            <SheetTitle>
              Szczegóły requestu {historyDetail?.request_id ?? selectedRequestId ?? ""}
            </SheetTitle>
            <SheetDescription>
              {"Dane z `/api/v1/history/requests` – kliknięcie w czat lub listę historii otwiera ten panel."}
            </SheetDescription>
          </SheetHeader>
          {!historyDetail && !loadingHistory && !historyError && (
            <p className="text-sm text-zinc-500">
              Wybierz request z Cockpitu, aby zobaczyć szczegóły.
            </p>
          )}
          {loadingHistory && (
            <p className="text-sm text-zinc-400">Ładuję szczegóły requestu...</p>
          )}
          {historyError && (
            <p className="text-sm text-rose-300">{historyError}</p>
          )}
          {historyDetail && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                <Badge tone={statusTone(historyDetail.status)}>
                  {historyDetail.status}
                </Badge>
                <span>Start: {formatDateTime(historyDetail.created_at)}</span>
                <span>Stop: {formatDateTime(historyDetail.finished_at)}</span>
                <span>Czas: {formatDurationSeconds(historyDetail.duration_seconds)}</span>
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-[0.3em] text-zinc-500">
                  Prompt
                </p>
                <div className="mt-2 text-sm text-white">
                  <MarkdownPreview
                    content={historyDetail.prompt}
                    emptyState="Brak promptu dla tego requestu."
                  />
                </div>
              </div>
              <div className="mt-4 space-y-2 rounded-2xl border border-white/10 bg-black/40 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h4 className="text-sm font-semibold text-white">
                      Kroki RequestTracer ({historyDetail.steps?.length ?? 0})
                    </h4>
                    <div className="flex flex-wrap gap-2 text-xs">
                      {copyStepsMessage && (
                        <span className="text-emerald-300">{copyStepsMessage}</span>
                      )}
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={handleCopyDetailSteps}
                      >
                        Kopiuj JSON
                      </Button>
                    </div>
                  </div>
                <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-2">
                  {(historyDetail.steps || []).length === 0 && (
                    <p className="text-sm text-zinc-500">Brak kroków do wyświetlenia.</p>
                  )}
                  {(historyDetail.steps || []).map((step, idx) => (
                    <div
                      key={`${historyDetail.request_id}-${idx}`}
                      className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-white">
                          {step.component || "step"}
                        </span>
                        {step.status && <Badge tone={statusTone(step.status)}>{step.status}</Badge>}
                      </div>
                      <p className="text-xs text-zinc-400">
                        {step.action || step.details || "Brak opisu kroku."}
                      </p>
                      {step.timestamp && (
                        <p className="text-[10px] uppercase tracking-wide text-zinc-500">
                          {formatDateTime(step.timestamp)}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <Link
                  href="/inspector"
                  className="rounded-full border border-white/10 px-4 py-2 text-white hover:bg-white/10"
                >
                  Otwórz w Inspectorze
                </Link>
                {historyDetail.request_id && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setDetailOpen(false);
                    }}
                  >
                    Zamknij
                  </Button>
                )}
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
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

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDurationSeconds(value?: number | null) {
  if (!value || value <= 0) return "—";
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.floor(value % 60);
  return `${minutes}m ${seconds}s`;
}

function LogEntry({
  entry,
  pinned,
  onPin,
}: {
  entry: LogEntryType;
  pinned?: boolean;
  onPin?: () => void;
}) {
  const payload = entry.payload;
  const logObj = isLogPayload(payload) ? payload : null;
  const text = logObj?.message
    ? logObj.message
    : typeof payload === "string"
      ? payload
      : JSON.stringify(payload, null, 2);
  const level = logObj?.level ? logObj.level.toUpperCase() : "INFO";
  const type = logObj?.type || "log";

  return (
    <div className="mb-2 rounded border border-emerald-500/20 bg-black/10 p-2 font-mono text-xs text-emerald-200 shadow-inner">
      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-emerald-300/70">
        <span>{new Date(entry.ts).toLocaleTimeString()}</span>
        <div className="flex items-center gap-2">
          <span>
            {type} • {level}
          </span>
          {onPin && (
            <IconButton
              label={pinned ? "Odepnij log" : "Przypnij log"}
              size="xs"
              variant="outline"
              className={
                pinned
                  ? "border-emerald-400/60 bg-emerald-500/20 text-emerald-100"
                  : "border-emerald-400/30 text-emerald-200"
              }
              icon={pinned ? <PinOff className="h-3.5 w-3.5" /> : <Pin className="h-3.5 w-3.5" />}
              onClick={onPin}
            />
          )}
        </div>
      </div>
      {logObj?.details ? (
        <details className="mt-1">
          <summary className="cursor-pointer text-emerald-200">Szczegóły</summary>
          <pre className="mt-1 max-h-40 overflow-auto text-emerald-100">
            {typeof logObj.details === "string"
              ? logObj.details
              : JSON.stringify(logObj.details, null, 2)}
          </pre>
        </details>
      ) : (
        <pre className="mt-1 whitespace-pre-wrap text-emerald-100">{"> " + text}</pre>
      )}
    </div>
  );
}

type TokenSample = { timestamp: string; value: number };
type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};
const MACRO_STORAGE_KEY = "venom:cockpit-macros";

type TokenEfficiencyStatProps = {
  label: string;
  value: string | number | null;
  hint: string;
};

function TokenEfficiencyStat({ label, value, hint }: TokenEfficiencyStatProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/30 p-3">
      <p className="text-[11px] uppercase tracking-[0.35em] text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value ?? "—"}</p>
      <p className="text-[11px] text-zinc-400">{hint}</p>
    </div>
  );
}

type TokenShareBarProps = {
  label: string;
  percent: number | null;
  accent: string;
};

function TokenShareBar({ label, percent, accent }: TokenShareBarProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
      <div className="flex items-center justify-between text-sm text-white">
        <span>{label}</span>
        <span>{percent !== null ? `${percent}%` : "—"}</span>
      </div>
      <div className="mt-2 h-2 rounded-full bg-white/5">
        <div
          className={`h-full rounded-full bg-gradient-to-r ${accent}`}
          style={{ width: percent !== null ? `${Math.min(percent, 100)}%` : "0%" }}
        />
      </div>
    </div>
  );
}

function TokenChart({ history, height = 220 }: { history: TokenSample[]; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);
  const chartModuleRef = useRef<typeof import("chart.js/auto") | null>(null);

  useEffect(() => {
    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!canvasRef.current) return;
    if (height) {
      canvasRef.current.style.height = `${height}px`;
    }
    const labels = history.map((h) => h.timestamp);
    const dataPoints = history.map((h) => h.value);

    let isMounted = true;
    const renderChart = async () => {
      if (!canvasRef.current) return;
      let chartModule = chartModuleRef.current;
      if (!chartModule) {
        chartModule = await import("chart.js/auto");
        chartModuleRef.current = chartModule;
      }
      if (!isMounted) return;
      const ChartJS = chartModule.default;

      if (chartRef.current) {
        chartRef.current.data.labels = labels;
        chartRef.current.data.datasets[0].data = dataPoints;
        chartRef.current.update();
        return;
      }

      chartRef.current = new ChartJS(canvasRef.current, {
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
    };

    renderChart();

    return () => {
      isMounted = false;
    };
  }, [history, height]);

  return <canvas ref={canvasRef} className="w-full" style={{ height }} />;
}

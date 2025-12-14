"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { ListCard } from "@/components/ui/list-card";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { MarkdownPreview } from "@/components/ui/markdown";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  emergencyStop,
  fetchHistoryDetail,
  gitSync,
  gitUndo,
  installModel,
  purgeQueue,
  sendTask,
  switchModel,
  toggleQueue,
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
import { AnimatePresence, motion } from "framer-motion";
import { Card, Metric, Text, Flex, ProgressBar, BarList } from "@tremor/react";
import { Bot, Pin, PinOff, X, Inbox, History as HistoryIcon, Package } from "lucide-react";
import Link from "next/link";

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
  const tokensBar = [
    { name: "Prompt", value: tokenMetrics?.prompt_tokens ?? 0 },
    { name: "Completion", value: tokenMetrics?.completion_tokens ?? 0 },
    { name: "Cached", value: tokenMetrics?.cached_tokens ?? 0 },
  ].filter((item) => item.value && item.value > 0);

  const successRate = metrics?.tasks?.success_rate ?? 0;
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

  return (
    <div className="space-y-8 pb-12">
      <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="flex flex-col gap-4">
          <div className="glass-panel flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                  Live Feed
                </p>
                <p className="text-sm font-semibold text-white">
                  /ws/events stream
                </p>
              </div>
              <Badge tone={connected ? "success" : "warning"}>
                {connected ? "Połączono" : "Brak sygnału"}
              </Badge>
            </div>
            <input
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-sm text-white outline-none placeholder:text-zinc-500"
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
              <div className="rounded-2xl border border-white/10 bg-white/5 p-3 text-xs text-zinc-200">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] uppercase tracking-[0.3em] text-zinc-500">
                    Pinned
                  </span>
                  <Button
                    variant="outline"
                    size="xs"
                    className="px-3 text-white"
                    onClick={async () => {
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
                      }
                    }}
                  >
                    Eksportuj JSON
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
                <ul className="mt-2 space-y-2">
                  {pinnedLogs.map((log) => (
                    <li
                      key={`pinned-${log.id}`}
                      className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-[11px]"
                    >
                      <div className="flex items-center justify-between text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                        <span>{new Date(log.ts).toLocaleTimeString()}</span>
                        <IconButton
                          label="Usuń przypięty log"
                          size="xs"
                          variant="ghost"
                          className="text-rose-300 hover:text-rose-400"
                          icon={<X className="h-3.5 w-3.5" />}
                          onClick={() =>
                            setPinnedLogs((prev) => prev.filter((entry) => entry.id !== log.id))
                          }
                        />
                      </div>
                      <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-white">
                        {typeof log.payload === "string"
                          ? log.payload
                          : JSON.stringify(log.payload, null, 2)}
                      </pre>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <Card className="border border-white/5 bg-white/5 text-white">
            <Text>Skuteczność operacji</Text>
            <Flex justifyContent="between" className="mt-3">
              <Metric>{successRate ? `${successRate}%` : "—"}</Metric>
              <Text>{metrics?.tasks?.created ?? 0} zadań</Text>
            </Flex>
            <ProgressBar value={successRate} color="violet" className="mt-3" />
            <Text className="mt-2 text-zinc-400">
              Uptime:{" "}
              {metrics?.uptime_seconds !== undefined
                ? formatUptime(metrics.uptime_seconds)
                : "—"}
            </Text>
          </Card>
          <Card className="border border-white/5 bg-white/5 text-white">
            <Text>Zużycie tokenów</Text>
            <Metric>{tokenMetrics?.total_tokens ?? 0}</Metric>
            <BarList
              data={
                tokensBar.length > 0
                  ? tokensBar
                  : [{ name: "Brak danych", value: 0 }]
              }
              className="mt-4 text-xs"
              color="violet"
            />
          </Card>
        </div>
        <div className="glass-panel relative flex min-h-[520px] flex-col overflow-hidden">
          <SectionHeading
            eyebrow="Centrum dowodzenia"
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
                        role="button"
                        tabIndex={0}
                        onClick={() => openRequestDetail(msg.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            openRequestDetail(msg.id);
                          }
                        }}
                        className={`w-fit max-w-2xl cursor-pointer rounded-2xl border px-4 py-3 text-sm shadow-lg transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/50 ${
                          msg.role === "user"
                            ? "ml-auto border-violet-500/30 bg-violet-500/10 text-violet-100"
                            : "border-white/10 bg-white/5 text-zinc-100"
                        } ${isSelected ? "ring-2 ring-violet-400/50" : ""}`}
                        title="Kliknij, aby otworzyć szczegóły requestu"
                      >
                        <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                          <span>{msg.role === "user" ? "Operacja" : "Venom"}</span>
                          <span>{new Date(msg.created_at).toLocaleTimeString()}</span>
                        </div>
                        <div className="mt-2 text-[15px] leading-relaxed text-white">
                          <MarkdownPreview content={msg.text} emptyState="Brak treści." />
                        </div>
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                          <Badge tone={statusTone(msg.status)}>{msg.status}</Badge>
                          <span>#{msg.id.slice(0, 6)}…</span>
                          <span className="ml-auto text-[10px] uppercase tracking-[0.3em] text-zinc-500">
                            Szczegóły ↗
                          </span>
                        </div>
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
                {message && (
                  <p className="mt-2 text-xs text-amber-300">{message}</p>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

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
          value={successRate ? `${successRate}%` : "—"}
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
          <div className="space-y-2 text-sm">
            {(history || []).length === 0 && (
              <EmptyState
                icon={<HistoryIcon className="h-4 w-4" />}
                title="Brak historii"
                description="Historia requestów pojawi się po wysłaniu zadań."
              />
            )}
            {(history || []).map((item) => (
              <ListCard
                key={item.request_id}
                title={item.prompt}
                subtitle={item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
                badge={<Badge tone={statusTone(item.status)}>{item.status}</Badge>}
                selected={selectedRequestId === item.request_id}
                onClick={() => openRequestDetail(item.request_id)}
              />
            ))}
            {loadingHistory && (
              <p className="text-xs text-zinc-500">Ładowanie szczegółów...</p>
            )}
            {historyError && (
              <p className="text-xs text-rose-300">{historyError}</p>
            )}
            <p className="text-[11px] uppercase tracking-[0.25em] text-zinc-500">
              Kliknij element listy, aby otworzyć panel boczny „Szczegóły requestu”.
            </p>
          </div>
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
        <div className="grid gap-3 md:grid-cols-2">
          {allMacros.map((macro) => (
            <div
              key={macro.id}
              className="flex flex-col gap-3 rounded-2xl border border-white/10 bg-white/5 p-4 text-left text-sm text-white"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-base font-semibold">{macro.label}</p>
                  <p className="text-xs text-zinc-400">{macro.description}</p>
                </div>
                {macro.custom && (
                  <Button
                    variant="ghost"
                    size="xs"
                    className="text-zinc-400 hover:text-rose-300"
                    onClick={() =>
                      setCustomMacros((prev) => prev.filter((item) => item.id !== macro.id))
                    }
                  >
                    Usuń
                  </Button>
                )}
              </div>
              <Button
                variant="subtle"
                className="rounded-2xl border-violet-500/30 bg-violet-500/10 px-3 py-2 text-sm font-semibold hover:border-violet-500/60"
                onClick={() => handleMacroRun(macro)}
                disabled={macroSending === macro.id}
              >
                {macroSending === macro.id ? "Wysyłam..." : "Uruchom"}
              </Button>
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Task Insights"
        description="Podsumowanie statusów i ostatnich requestów /history/requests."
      >
        <div className="grid gap-4 md:grid-cols-2">
          <Card className="border border-white/10 bg-white/5 text-white">
            <Text>Statusy (ostatnie)</Text>
            <BarList
              data={
                historySummary.length > 0
                  ? historySummary
                  : [{ name: "Brak danych", value: 0 }]
              }
              className="mt-4 text-xs"
              color="violet"
            />
          </Card>
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white">
            <p className="text-xs uppercase tracking-[0.3em] text-zinc-400">
              Ostatnie requesty
            </p>
            <ul className="mt-3 space-y-2 text-xs text-zinc-300">
              {(history || []).slice(0, 5).map((item) => (
                <li
                  key={`insight-${item.request_id}`}
                  className="rounded-xl border border-white/10 bg-black/30 px-3 py-2"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white">{item.status}</span>
                    <span>{item.finished_at ? new Date(item.finished_at).toLocaleTimeString() : "—"}</span>
                  </div>
                  <p className="text-[11px] text-zinc-500 line-clamp-2">{item.prompt}</p>
                </li>
              ))}
              {(history || []).length === 0 && (
                <li className="rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-zinc-500">
                  Brak historii do analizy.
                </li>
              )}
            </ul>
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
            <Button
              variant="secondary"
              size="sm"
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
            </Button>
            <Button
              variant="warning"
              size="sm"
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
            </Button>
            <Button
              variant="danger"
              size="sm"
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
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <input
                className="w-full max-w-xs rounded-lg border border-[--color-border] bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[--color-accent]"
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
            <div className="space-y-2">
              {(models?.models || []).length === 0 && (
                <EmptyState
                  icon={<Package className="h-4 w-4" />}
                  title="Brak modeli"
                  description="Zainstaluj model, aby rozpocząć pracę."
                />
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
                  <Button
                    size="sm"
                    variant={model.active ? "secondary" : "outline"}
                    className={
                      model.active
                        ? "border-emerald-400/30 bg-[--color-accent-2]/20 text-emerald-100"
                        : ""
                    }
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
                  </Button>
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
            <Button
              variant="secondary"
              size="sm"
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
            </Button>
            <Button
              variant="warning"
              size="sm"
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
            </Button>
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
            {logObj.details}
          </pre>
        </details>
      ) : (
        <pre className="mt-1 whitespace-pre-wrap text-emerald-100">{"> " + text}</pre>
      )}
    </div>
  );
}

type LogEntryType = {
  id: string;
  ts: number;
  payload: unknown;
};

type LogPayload = {
  message?: string;
  level?: string;
  type?: string;
};

function isLogPayload(value: unknown): value is LogPayload {
  return typeof value === "object" && value !== null;
}

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
type MacroAction = {
  id: string;
  label: string;
  description: string;
  content: string;
  custom?: boolean;
};
const MACRO_STORAGE_KEY = "venom:cockpit-macros";

function TokenChart({ history }: { history: TokenSample[] }) {
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
  }, [history]);

  return <canvas ref={canvasRef} className="w-full" />;
}

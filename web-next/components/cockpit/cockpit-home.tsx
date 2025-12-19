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
  controlLlmServer,
  emergencyStop,
  fetchHistoryDetail,
  fetchModelConfig,
  fetchTaskDetail,
  gitSync,
  gitUndo,
  installModel,
  purgeQueue,
  sendTask,
  switchModel,
  toggleQueue,
  unloadAllModels,
  useGitStatus,
  useGraphSummary,
  useHistory,
  useLlmServers,
  useMetrics,
  useModels,
  useModelsUsage,
  useQueueStatus,
  useServiceStatus,
  useTasks,
  useTokenMetrics,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { TaskStreamEvent, useTaskStream } from "@/hooks/use-task-stream";
import type { Chart } from "chart.js/auto";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { GenerationParams, HistoryRequestDetail, ServiceStatus, Task } from "@/lib/types";
import type { CockpitInitialData } from "@/lib/server-data";
import { LogEntryType, isLogPayload } from "@/lib/logs";
import { statusTone } from "@/lib/status";
import { AnimatePresence, motion } from "framer-motion";
import { CockpitMetricCard, CockpitTokenCard } from "@/components/cockpit/kpi-card";
import { Bot, Pin, PinOff, Inbox, Package, Loader2, Settings } from "lucide-react";
import Link from "next/link";
import { DynamicParameterForm, type GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import { HistoryList } from "@/components/history/history-list";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { RecentRequestList } from "@/components/tasks/recent-request-list";
import { QueueStatusCard } from "@/components/queue/queue-status-card";
import { QuickActions } from "@/components/layout/quick-actions";
import { VoiceCommandCenter } from "@/components/voice/voice-command-center";
import { IntegrationMatrix } from "@/components/cockpit/integration-matrix";
import {
  formatDiskUsage,
  formatGbPair,
  formatPercentMetric,
  formatUsd,
  formatVramMetric,
} from "@/lib/formatters";

const TELEMETRY_REFRESH_EVENTS = new Set([
  "AGENT_ACTION",
  "TASK_CREATED",
  "TASK_STARTED",
  "TASK_COMPLETED",
  "TASK_FAILED",
  "TASK_ABORTED",
  "QUEUE_PAUSED",
  "QUEUE_RESUMED",
  "QUEUE_PURGED",
  "EMERGENCY_STOP",
]);

type LlmAlertState = {
  provider?: string | null;
  model?: string | null;
  endpoint?: string | null;
  error?: string | null;
  taskId?: string;
  timestamp?: string | null;
};

type TelemetryEventPayload = {
  type?: string;
  data?: Record<string, unknown>;
  message?: string;
};

const isTelemetryEventPayload = (payload: unknown): payload is TelemetryEventPayload => {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as { type?: unknown };
  return typeof candidate.type === "string";
};

export function CockpitHome({ initialData }: { initialData: CockpitInitialData }) {
  const [isClientReady, setIsClientReady] = useState(false);
  useEffect(() => {
    setIsClientReady(true);
  }, []);
  const [taskContent, setTaskContent] = useState("");
  const [labMode, setLabMode] = useState(false);
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [llmActionPending, setLlmActionPending] = useState<string | null>(null);
  const [llmAlert, setLlmAlert] = useState<LlmAlertState | null>(null);
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
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [copyStepsMessage, setCopyStepsMessage] = useState<string | null>(null);
  const [quickActionsOpen, setQuickActionsOpen] = useState(false);
  const [exportingPinned, setExportingPinned] = useState(false);
  const [gitAction, setGitAction] = useState<"sync" | "undo" | null>(null);
  const [unloadingModels, setUnloadingModels] = useState(false);
  const [queueAction, setQueueAction] = useState<
    null | "pause" | "resume" | "purge" | "emergency"
  >(null);
  const [queueActionMessage, setQueueActionMessage] = useState<string | null>(
    null,
  );
  const [optimisticRequests, setOptimisticRequests] = useState<OptimisticRequestState[]>([]);
  const [lastResponseDurationMs, setLastResponseDurationMs] = useState<number | null>(null);
  const [responseDurations, setResponseDurations] = useState<number[]>([]);
  const lastTelemetryRefreshRef = useRef<string | null>(null);
  const [tuningOpen, setTuningOpen] = useState(false);
  const [generationParams, setGenerationParams] = useState<GenerationParams | null>(null);
  const [modelSchema, setModelSchema] = useState<GenerationSchema | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const streamCompletionRef = useRef<Set<string>>(new Set());
  const promptPresets = useMemo(
    () => [
      {
        id: "preset-creative",
        category: "Kreacja",
        description: "Stwórz logo dla fintechu używając DALL-E",
        prompt: "Stwórz logo dla fintechu używając DALL-E",
        icon: "🎨",
      },
      {
        id: "preset-devops",
        category: "DevOps",
        description: "Sprawdź status serwerów w infrastrukturze",
        prompt: "Sprawdź status serwerów w infrastrukturze",
        icon: "☁️",
      },
      {
        id: "preset-project",
        category: "Status projektu",
        description: "Pokaż status projektu i roadmapy",
        prompt: "Pokaż status projektu",
        icon: "📊",
      },
      {
        id: "preset-research",
        category: "Research",
        description: "Zrób research o trendach AI w 2024",
        prompt: "Zrób research o trendach AI w 2024",
        icon: "🧠",
      },
      {
        id: "preset-code",
        category: "Kod",
        description: "Napisz testy jednostkowe dla modułu API",
        prompt: "Napisz testy jednostkowe dla modułu API",
        icon: "🛠️",
      },
      {
        id: "preset-help",
        category: "Pomoc",
        description: "Co potrafisz? Pokaż dostępne funkcje systemu",
        prompt: "Co potrafisz?",
        icon: "❓",
      },
    ],
    [],
  );
  const modelProviderMeta: Record<
    string,
    { title: string; description: string; installHint?: string }
  > = useMemo(
    () => ({
      vllm: {
        title: "Modele vLLM",
        description: "Pakiety Hugging Face / safetensors w katalogu ./models lub ./data/models.",
        installHint: "Dodaj model do katalogu i zrestartuj serwer vLLM.",
      },
      ollama: {
        title: "Modele Ollama",
        description: "Modele GGUF zarządzane przez daemon Ollama (port 11434).",
        installHint: "Użyj formularza instalacji lub `ollama pull <model>`.",
      },
    }),
    [],
  );

  const { data: liveMetrics, loading: metricsLoading } = useMetrics();
  const metrics = liveMetrics ?? initialData.metrics ?? null;
  const { data: liveTasks, refresh: refreshTasks } = useTasks();
  const tasks = liveTasks ?? initialData.tasks ?? null;
  const { data: liveQueue, loading: queueLoading, refresh: refreshQueue } = useQueueStatus();
  const queue = liveQueue ?? initialData.queue ?? null;
  const { data: liveServices } = useServiceStatus();
  const {
    data: liveLlmServers,
    loading: llmServersLoading,
    refresh: refreshLlmServers,
  } = useLlmServers();
  const services = liveServices ?? initialData.services ?? null;
  const { data: liveGraph } = useGraphSummary();
  const graph = liveGraph ?? initialData.graphSummary ?? null;
  const { data: liveModels, refresh: refreshModels } = useModels();
  const models = liveModels ?? initialData.models ?? null;
  const { data: liveGit, refresh: refreshGit } = useGitStatus();
  const git = liveGit ?? initialData.gitStatus ?? null;
  const { data: liveTokenMetrics, loading: tokenMetricsLoading } = useTokenMetrics();
  const tokenMetrics = liveTokenMetrics ?? initialData.tokenMetrics ?? null;
  const { data: liveHistory, loading: historyLoading, refresh: refreshHistory } = useHistory(6);
  const history = liveHistory ?? initialData.history ?? null;
  const trackedRequestIds = useMemo(() => {
    const ids = new Set<string>();
    optimisticRequests.forEach((entry) => {
      if (entry.requestId) ids.add(entry.requestId);
    });
    (history ?? [])
      .filter((item) => item.status === "PENDING" || item.status === "PROCESSING")
      .forEach((item) => ids.add(item.request_id));
    if (selectedRequestId) ids.add(selectedRequestId);
    return Array.from(ids);
  }, [optimisticRequests, history, selectedRequestId]);
  const handleTaskEvent = useCallback(
    (event: TaskStreamEvent) => {
      if (event.llmStatus === "error" || event.llmRuntimeError) {
        setLlmAlert({
          provider: event.llmProvider,
          model: event.llmModel,
          endpoint: event.llmEndpoint,
          error:
            event.llmRuntimeError ||
            `Błąd podczas wykonywania zadania ${event.taskId}`,
          taskId: event.taskId,
          timestamp: event.timestamp ?? new Date().toISOString(),
        });
      } else if (event.llmStatus === "ready") {
        setLlmAlert((current) =>
          current && (!current.taskId || current.taskId === event.taskId)
            ? null
            : current,
        );
      }
    },
    [],
  );
  const { streams: taskStreams } = useTaskStream(trackedRequestIds, {
    enabled: isClientReady && trackedRequestIds.length > 0,
    onEvent: handleTaskEvent,
  });
  const { data: liveModelsUsageResponse, refresh: refreshModelsUsage } = useModelsUsage(10000);
  const modelsUsageResponse =
    liveModelsUsageResponse ?? initialData.modelsUsage ?? null;
  const { connected, entries } = useTelemetryFeed();
  const usageMetrics = modelsUsageResponse?.usage ?? null;
  const llmServers = liveLlmServers ?? [];
  const activeRuntime = models?.active;
  const runtimeStatus = useMemo(() => {
    if (!activeRuntime) return "unknown";
    const statusValue = activeRuntime.status;
    if (typeof statusValue === "string" && statusValue.length > 0) {
      return statusValue.toLowerCase();
    }
    return "unknown";
  }, [activeRuntime]);
  const runtimeIsOnline = runtimeStatus === "online" || runtimeStatus === "ready";
  const runtimeStatusLabel = useMemo(() => {
    if (runtimeIsOnline) return "Online";
    if (!runtimeStatus || runtimeStatus === "unknown") return "Unknown";
    return runtimeStatus.charAt(0).toUpperCase() + runtimeStatus.slice(1);
  }, [runtimeIsOnline, runtimeStatus]);
  const runtimeAlert = useMemo(() => {
    if (llmAlert) return llmAlert;
    if (!runtimeIsOnline) {
      return {
        provider: activeRuntime?.provider,
        model: activeRuntime?.model,
        endpoint: activeRuntime?.endpoint,
        error:
          activeRuntime?.error ??
          `Runtime (${runtimeStatusLabel.toLowerCase()}) jest niedostępny.`,
      };
    }
    return null;
  }, [llmAlert, runtimeIsOnline, activeRuntime, runtimeStatusLabel]);
  const runtimeAlertDismissible = Boolean(llmAlert);
  const tasksByPrompt = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      if (task.content) {
        bucket.set(task.content.trim(), task);
      }
    });
    return bucket;
  }, [tasks]);
  const tasksById = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      const key = task.task_id || task.id;
      if (key) {
        bucket.set(key, task);
      }
    });
    return bucket;
  }, [tasks]);
  const serviceStatusMap = useMemo(() => {
    const map = new Map<string, ServiceStatus>();
    (services || []).forEach((svc) => {
      if (svc?.name) {
        map.set(svc.name.toLowerCase(), svc);
      }
    });
    return map;
  }, [services]);
  const selectedTaskRuntime = useMemo(() => {
    const runtime = selectedTask?.context_history?.["llm_runtime"];
    if (runtime && typeof runtime === "object") {
      const ctx = runtime as Record<string, unknown>;
      const statusValue = ctx["status"];
      const errorValue = ctx["error"];
      return {
        status: typeof statusValue === "string" ? statusValue : null,
        error: typeof errorValue === "string" ? errorValue : null,
      };
    }
    return null;
  }, [selectedTask]);
  const findTaskMatch = useCallback(
    (requestId?: string, prompt?: string | null) => {
      if (requestId) {
        const byId = tasksById.get(requestId);
        if (byId) return byId;
      }
      if (prompt) {
        const trimmed = prompt.trim();
        if (trimmed.length > 0) {
          return tasksByPrompt.get(trimmed) ?? null;
        }
      }
      return null;
    },
    [tasksById, tasksByPrompt],
  );

  const handleLlmServerAction = useCallback(
    async (server: string, action: "start" | "stop" | "restart") => {
      try {
        setLlmActionPending(`${server}:${action}`);
        const response = await controlLlmServer(server, action);
        setMessage(
          response.message ||
            `Akcja ${action.toUpperCase()} dla ${server} ${
              response.status === "success" ? "zakończona pomyślnie" : "zwróciła błąd"
            }.`,
        );
      } catch (err) {
        const fallback =
          err instanceof Error ? err.message : `Nie udało się wykonać akcji ${action}`;
        setMessage(fallback);
      } finally {
        setLlmActionPending(null);
        refreshLlmServers();
      }
    },
    [refreshLlmServers],
  );

  const resolveServerStatus = useCallback(
    (serverName: string, fallback?: string | null) => {
      const lowered = serverName.toLowerCase();
      const match =
        serviceStatusMap.get(lowered) ||
        serviceStatusMap.get(serverName.toLowerCase());
      return (fallback || match?.status || "unknown").toLowerCase();
    },
    [serviceStatusMap],
  );

  const statusToneFor = (status: string) => {
    const normalized = status.toLowerCase();
    if (["online", "healthy", "success"].includes(normalized)) return "success" as const;
    if (["offline", "down", "error"].includes(normalized)) return "danger" as const;
    if (["degraded", "warning"].includes(normalized)) return "warning" as const;
    return "neutral" as const;
  };

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

  useEffect(() => {
    if (!detailOpen || !selectedRequestId) return;
    const fallback = findTaskMatch(selectedRequestId, historyDetail?.prompt);
    if (!fallback) return;
    if (
      !selectedTask ||
      (fallback.logs?.length ?? 0) !== (selectedTask.logs?.length ?? 0) ||
      (fallback.result ?? "") !== (selectedTask.result ?? "")
    ) {
      setSelectedTask(fallback);
    }
  }, [detailOpen, selectedRequestId, historyDetail?.prompt, findTaskMatch, selectedTask]);

  useEffect(() => {
    if (!history || history.length === 0) return;
    let latestDuration: number | null = null;
    setOptimisticRequests((prev) => {
      if (prev.length === 0) return prev;
      let mutated = false;
      const next = prev.filter((entry) => {
        if (!entry.requestId) return true;
        const match = history.find((item) => item.request_id === entry.requestId);
        if (match) {
          mutated = true;
          const finishTs = match.finished_at ?? match.created_at ?? entry.createdAt;
          if (finishTs) {
            const duration = new Date(finishTs).getTime() - entry.startedAt;
            if (Number.isFinite(duration)) {
              latestDuration = duration;
            }
          }
          return false;
        }
        return true;
      });
      return mutated ? next : prev;
    });
    const measuredDuration = latestDuration;
    if (typeof measuredDuration === "number") {
      setLastResponseDurationMs(measuredDuration);
      setResponseDurations((prev) => {
        const next = [...prev, measuredDuration];
        return next.slice(-10);
      });
    }
  }, [history]);

  useEffect(() => {
    if (!entries.length) return;
    const latest = entries[0];
    if (!latest || lastTelemetryRefreshRef.current === latest.id) return;
    lastTelemetryRefreshRef.current = latest.id;
    if (!isTelemetryEventPayload(latest.payload)) return;
    if (!latest.payload.type || !TELEMETRY_REFRESH_EVENTS.has(latest.payload.type)) {
      return;
    }
    const debounce = setTimeout(() => {
      refreshQueue();
      refreshTasks();
      refreshHistory();
    }, 250);
    return () => clearTimeout(debounce);
  }, [entries, refreshQueue, refreshTasks, refreshHistory]);

  useEffect(() => {
    const activeIds = new Set(Object.keys(taskStreams));
    streamCompletionRef.current.forEach((trackedId) => {
      if (!activeIds.has(trackedId)) {
        streamCompletionRef.current.delete(trackedId);
      }
    });

    const entries = Object.entries(taskStreams);
    if (entries.length === 0) return;

    const terminalStatuses = new Set(["COMPLETED", "FAILED", "LOST"]);
    let shouldRefresh = false;
    for (const [taskId, state] of entries) {
      if (!state?.status) continue;
      if (!terminalStatuses.has(state.status)) continue;
      if (streamCompletionRef.current.has(taskId)) continue;
      streamCompletionRef.current.add(taskId);
      shouldRefresh = true;
    }
    if (shouldRefresh) {
      refreshHistory();
      refreshTasks();
    }
  }, [taskStreams, refreshHistory, refreshTasks]);

  const tasksPreview = (tasks || []).slice(0, 4);
  const fallbackAgents: ServiceStatus[] = [
    { name: "Orchestrator", status: "healthy", detail: "Tworzenie i analiza zadań" },
    { name: "Watcher", status: "degraded", detail: "Monitoring repo / usług" },
    { name: "Gardener", status: "healthy", detail: "Lekcje i graf wiedzy" },
  ];
  const agentDeck = services && services.length > 0 ? services : fallbackAgents;
  const cpuUsageValue = formatPercentMetric(usageMetrics?.cpu_usage_percent);
  const gpuUsageValue =
    usageMetrics?.gpu_usage_percent !== undefined
      ? formatPercentMetric(usageMetrics.gpu_usage_percent)
      : usageMetrics?.vram_usage_mb && usageMetrics.vram_usage_mb > 0
        ? "Aktywne"
        : "—";
  const ramValue = formatGbPair(usageMetrics?.memory_used_gb, usageMetrics?.memory_total_gb);
  const vramValue = formatVramMetric(usageMetrics?.vram_usage_mb, usageMetrics?.vram_total_mb);
  const diskValue = formatDiskUsage(usageMetrics?.disk_usage_gb, usageMetrics?.disk_limit_gb);
  const diskPercent =
    usageMetrics?.disk_usage_percent !== undefined
      ? `${usageMetrics.disk_usage_percent.toFixed(1)}%`
      : null;
  const sessionCostValue = formatUsd(tokenMetrics?.session_cost_usd);
  const historyMessages = useMemo<ChatMessage[]>(() => {
    if (!history) return [];
    return history.flatMap((item) => {
      const prompt = item.prompt?.trim() ?? "";
      const matchedTask = findTaskMatch(item.request_id, prompt);
      const assistantText =
        matchedTask?.result?.trim() ??
        (item.status === "COMPLETED"
          ? "Brak zapisanej odpowiedzi – sprawdź szczegóły zadania."
          : "Odpowiedź w trakcie generowania…");
      const assistantStatus = matchedTask?.status ?? item.status;
      const assistantTimestamp =
        matchedTask?.updated_at ||
        matchedTask?.created_at ||
        item.finished_at ||
        item.created_at;
      return [
        {
          bubbleId: `${item.request_id}-prompt`,
          requestId: item.request_id,
          role: "user",
          text: prompt || "Brak treści zadania.",
          status: item.status,
          timestamp: item.created_at,
          prompt,
          pending: false,
        },
        {
          bubbleId: `${item.request_id}-response`,
          requestId: item.request_id,
          role: "assistant",
          text: assistantText,
          status: assistantStatus,
          timestamp: assistantTimestamp ?? item.created_at,
          prompt,
          pending: false,
        },
      ];
    });
  }, [history, findTaskMatch]);

  const optimisticMessages = useMemo<ChatMessage[]>(() => {
    return optimisticRequests.flatMap((entry) => {
      const baseId = entry.requestId ?? entry.clientId;
      const stream = entry.requestId ? taskStreams[entry.requestId] : null;
      const assistantText =
        stream?.result && stream.result.trim().length > 0
          ? stream.result
          : stream?.logs && stream.logs.length > 0
            ? stream.logs[stream.logs.length - 1] ?? "Generuję odpowiedź…"
            : "Generuję odpowiedź…";
      const assistantStatus =
        stream?.status ??
        (stream?.error ? "Błąd strumienia" : stream ? "W toku" : "W kolejce");
      const isPending =
        !stream?.status || (stream.status !== "COMPLETED" && stream.status !== "FAILED");
      return [
        {
          bubbleId: `${baseId}-optimistic-prompt`,
          requestId: entry.requestId,
          role: "user",
          text: entry.prompt || "Brak treści zadania.",
          status: stream?.status ?? "Wysłano",
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
        },
        {
          bubbleId: `${baseId}-optimistic-response`,
          requestId: entry.requestId,
          role: "assistant",
          text: assistantText,
          status: assistantStatus,
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
        },
      ];
    });
  }, [optimisticRequests, taskStreams]);

  const chatMessages = useMemo(
    () => [...historyMessages, ...optimisticMessages],
    [historyMessages, optimisticMessages],
  );
  const averageResponseDurationMs =
    responseDurations.length > 0
      ? responseDurations.reduce((acc, value) => acc + value, 0) /
        Math.max(responseDurations.length, 1)
      : null;
  const responseBadgeText =
    lastResponseDurationMs !== null ? `${(lastResponseDurationMs / 1000).toFixed(1)}s` : "n/d";
  const responseBadgeTone =
    lastResponseDurationMs === null
      ? "neutral"
      : lastResponseDurationMs <= 4000
        ? "success"
        : "warning";
  const responseBadgeTitle =
    averageResponseDurationMs !== null
      ? `Średnia z ostatnich ${responseDurations.length} odpowiedzi: ${(averageResponseDurationMs / 1000).toFixed(1)}s`
      : "Brak danych historycznych";
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
  const telemetryFeed = useMemo<TelemetryFeedEntry[]>(() => {
    return entries
      .filter((entry) => isTelemetryEventPayload(entry.payload) && entry.payload.type)
      .slice(0, 12)
      .map((entry) => {
        const payload = entry.payload as TelemetryEventPayload;
        return {
          id: entry.id,
          type: payload.type ?? "SYSTEM_LOG",
          message: payload.message || (typeof payload.data?.message === "string" ? payload.data?.message : "Zdarzenie telemetryczne"),
          timestamp: new Date(entry.ts).toLocaleTimeString(),
          tone: mapTelemetryTone(payload.type ?? "SYSTEM_LOG"),
        };
      });
  }, [entries]);
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
  const modelHistoryEntries = useMemo(() => {
    return (models?.models ?? []).map((model) => {
      const sizeLabel =
        typeof model.size_gb === "number" ? `${model.size_gb.toFixed(2)} GB` : "—";
      const sourceLabel =
        model.source || model.type || model.path || "Lokalny model";
      const badgeTone = model.active ? "success" : "neutral";
      return {
        name: model.name,
        sizeLabel,
        sourceLabel,
        statusLabel: model.active ? "Aktywny" : "W gotowości",
        quantizationLabel: model.quantization ?? "—",
        badgeTone,
      } as const;
    });
  }, [models]);
  const baseModelCount = models?.count ?? models?.models?.length ?? 0;
  const displayedModelCount = usageMetrics?.models_count ?? baseModelCount;
  const groupedModels = useMemo(() => {
    if (!models) return [];
    if (models.providers && Object.keys(models.providers).length > 0) {
      return Object.entries(models.providers).map(([provider, items]) => ({
        provider,
        items,
      }));
    }
    return [
      {
        provider: activeRuntime?.provider ?? "local",
        items: models.models ?? [],
      },
    ];
  }, [models, activeRuntime]);

  const allMacros = useMemo(
    () => [...macroActions, ...customMacros],
    [macroActions, customMacros],
  );

  const enqueueOptimisticRequest = useCallback((prompt: string) => {
    const entry: OptimisticRequestState = {
      clientId: createOptimisticId(),
      requestId: null,
      prompt,
      createdAt: new Date().toISOString(),
      startedAt: Date.now(),
      confirmed: false,
    };
    setOptimisticRequests((prev) => [...prev, entry]);
    return entry.clientId;
  }, []);

  const linkOptimisticRequest = useCallback((clientId: string, requestId: string | null) => {
    if (!clientId) return;
    setOptimisticRequests((prev) =>
      prev.map((entry) =>
        entry.clientId === clientId
          ? {
              ...entry,
              requestId: requestId ?? entry.requestId ?? entry.clientId,
              confirmed: true,
            }
          : entry,
      ),
    );
  }, []);

  const dropOptimisticRequest = useCallback((clientId: string) => {
    if (!clientId) return;
    setOptimisticRequests((prev) => prev.filter((entry) => entry.clientId !== clientId));
  }, []);

  const handleSend = useCallback(async () => {
    const payload = taskContent.trim();
    if (!payload) {
      setMessage("Podaj treść zadania.");
      return;
    }
    setSending(true);
    setMessage(null);
    setTaskContent("");
    const clientId = enqueueOptimisticRequest(payload);
    try {
      const res = await sendTask(payload, !labMode, generationParams);
      const resolvedId = res.task_id ?? null;
      linkOptimisticRequest(clientId, resolvedId);
      setMessage(`Wysłano zadanie: ${resolvedId ?? "w toku…"}`);
      await Promise.all([refreshTasks(), refreshQueue(), refreshHistory()]);
    } catch (err) {
      setTaskContent(payload);
      dropOptimisticRequest(clientId);
      setMessage(
        err instanceof Error ? err.message : "Nie udało się wysłać zadania",
      );
    } finally {
      setSending(false);
    }
  }, [
    taskContent,
    enqueueOptimisticRequest,
    labMode,
    generationParams,
    linkOptimisticRequest,
    dropOptimisticRequest,
    refreshTasks,
    refreshQueue,
    refreshHistory,
  ]);

  const handleOpenTuning = useCallback(async () => {
    setTuningOpen(true);
    setLoadingSchema(true);
    try {
      // Pobierz aktywny model z runtime info
      const activeModelName = models?.active?.model || "llama3";
      const config = await fetchModelConfig(activeModelName);
      const schema = config?.generation_schema as GenerationSchema | undefined;
      setModelSchema(schema ?? null);
    } catch (err) {
      console.error("Nie udało się pobrać konfiguracji modelu:", err);
      setModelSchema(null);
    } finally {
      setLoadingSchema(false);
    }
  }, [models, setTuningOpen, setLoadingSchema, setModelSchema]);

  const handleMacroRun = useCallback(
    async (macro: { id: string; content: string; label: string }) => {
      if (macroSending) return;
      setMacroSending(macro.id);
      setMessage(null);
      const clientId = enqueueOptimisticRequest(macro.content);
      try {
        const res = await sendTask(macro.content, !labMode);
        linkOptimisticRequest(clientId, res.task_id ?? null);
        setMessage(`Makro ${macro.label} wysłane: ${res.task_id ?? "w toku…"}`);
        await Promise.all([refreshTasks(), refreshQueue(), refreshHistory()]);
      } catch (err) {
        dropOptimisticRequest(clientId);
        setMessage(err instanceof Error ? err.message : "Nie udało się wykonać makra.");
      } finally {
        setMacroSending(null);
      }
    },
    [
      macroSending,
      enqueueOptimisticRequest,
      labMode,
      linkOptimisticRequest,
      dropOptimisticRequest,
      refreshTasks,
      refreshQueue,
      refreshHistory,
    ],
  );

  const handleUnloadModels = async () => {
    if (unloadingModels) return;
    setUnloadingModels(true);
    try {
      const res = await unloadAllModels();
      setMessage(res.message || "Zasoby zostały zwolnione.");
      refreshModels();
      refreshModelsUsage();
      refreshTasks();
      refreshQueue();
    } catch (err) {
      setMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się zwolnić zasobów modeli.",
      );
    } finally {
      setUnloadingModels(false);
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

  const handleToggleQueue = async () => {
    if (!queue) return;
    const action = queue.paused ? "resume" : "pause";
    if (queueAction) return;
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      await toggleQueue(action === "pause");
      setQueueActionMessage(
        action === "pause"
          ? "Kolejka wstrzymana."
          : "Kolejka wznowiona.",
      );
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się zmienić stanu kolejki.",
      );
    } finally {
      setQueueAction(null);
    }
  };

  const executeQueueMutation = async (type: "purge" | "emergency") => {
    if (queueAction) return;
    setQueueAction(type);
    setQueueActionMessage(null);
    try {
      if (type === "purge") {
        const res = await purgeQueue();
        setQueueActionMessage(`Wyczyszczono kolejkę (${res.removed} zadań).`);
      } else {
        const res = await emergencyStop();
        setQueueActionMessage(
          `Zatrzymano zadania: cancelled ${res.cancelled}, purged ${res.purged}.`,
        );
      }
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się wykonać akcji na kolejce.",
      );
    } finally {
      setQueueAction(null);
    }
  };

  const openRequestDetail = async (requestId: string, prompt?: string) => {
    setSelectedRequestId(requestId);
    setDetailOpen(true);
    setHistoryDetail(null);
    setHistoryError(null);
    setCopyStepsMessage(null);
    setSelectedTask(null);
    setLoadingHistory(true);
    const fallback = findTaskMatch(requestId, prompt);
    try {
      const [detailResult, taskResult] = await Promise.allSettled([
        fetchHistoryDetail(requestId),
        fetchTaskDetail(requestId),
      ]);

      if (detailResult.status === "fulfilled") {
        setHistoryDetail(detailResult.value);
      } else {
        setHistoryError(
          detailResult.reason instanceof Error
            ? detailResult.reason.message
            : "Nie udało się pobrać szczegółów",
        );
      }

      if (taskResult.status === "fulfilled") {
        setSelectedTask(taskResult.value);
      } else if (fallback) {
        setSelectedTask(fallback);
      }
    } catch (err) {
      setHistoryError(
        err instanceof Error ? err.message : "Nie udało się pobrać szczegółów",
      );
      if (fallback) {
        setSelectedTask(fallback);
      }
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

  const handleSuggestionClick = (prompt: string) => {
    setTaskContent(prompt);
  };

  const handleTextareaKeyDown = useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>) => {
      const isEnter = event.key === "Enter";
      const isModifier = event.ctrlKey || event.metaKey;
      if (isEnter && isModifier) {
        event.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

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

  if (!isClientReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#020617] p-6 text-sm text-zinc-400">
        Ładowanie kokpitu…
      </div>
    );
  }

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
        <div className="space-y-6">
          <Panel
            title="Serwery LLM"
            description="Steruj lokalnymi runtime (vLLM, Ollama) i monitoruj ich status."
            action={
              <Button variant="secondary" size="xs" onClick={refreshLlmServers}>
                Odśwież
              </Button>
            }
          >
            {llmServersLoading ? (
              <p className="text-sm text-zinc-500">Ładuję status serwerów…</p>
            ) : llmServers.length === 0 ? (
              <EmptyState
                icon={<Package className="h-4 w-4" />}
                title="Brak danych"
                description="Skonfiguruj komendy LLM_*_COMMAND w .env, aby włączyć sterowanie serwerami."
              />
            ) : (
              <div className="space-y-3">
                {llmServers.map((server) => {
                  const statusValue = resolveServerStatus(
                    server.display_name,
                    server.status,
                  );
                  const tone = statusToneFor(statusValue);
                  const pendingPrefix = `${server.name}:`;
                  return (
                    <div
                      key={server.name}
                      className="rounded-3xl border border-white/10 bg-white/5 p-4 text-sm text-white shadow-card"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-lg font-semibold">{server.display_name}</p>
                          <p className="text-xs text-zinc-400">
                            {server.description || "Lokalny serwer LLM"}
                          </p>
                          {server.endpoint && (
                            <p className="text-xs text-zinc-500">{server.endpoint}</p>
                          )}
                        </div>
                        <Badge tone={tone}>{statusValue}</Badge>
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {(["start", "stop", "restart"] as const).map((action) => {
                          const supported = server.supports?.[action];
                          const actionKey = `${pendingPrefix}${action}`;
                          return (
                            <Button
                              key={`${server.name}-${action}`}
                              size="xs"
                              variant="outline"
                              disabled={!supported || llmActionPending === actionKey}
                              onClick={() => handleLlmServerAction(server.name, action)}
                            >
                              {llmActionPending === actionKey ? "..." : action.toUpperCase()}
                            </Button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>
          <Panel
            title="Modele"
            description="Lista modeli lokalnych i aktywacja (/api/v1/models)."
            action={
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral" data-testid="models-count">
                  {displayedModelCount} modeli
                </Badge>
                <Button
                  variant="danger"
                  size="xs"
                  className="rounded-full px-3"
                  onClick={handleUnloadModels}
                  disabled={unloadingModels}
                >
                  {unloadingModels ? "Zwalnianie..." : "PANIC: Zwolnij zasoby"}
                </Button>
              </div>
            }
          >
            <div className="space-y-4">
            <div className="rounded-3xl border border-emerald-400/15 bg-gradient-to-br from-emerald-500/10 via-black/40 to-transparent p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.35em] text-emerald-200/70">
                    Aktywny runtime
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    {activeRuntime?.label ?? "Brak aktywnego modelu"}
                  </p>
                  <p className="text-xs text-zinc-400">
                    {activeRuntime?.provider
                      ? `Serwer: ${activeRuntime.provider}`
                      : "Ustaw LLM_MODEL_NAME i endpoint w .env"}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {activeRuntime?.endpoint ?? "Endpoint nieustawiony"}
                  </p>
                </div>
                <Badge tone={runtimeIsOnline ? "success" : runtimeAlert ? "danger" : "neutral"}>
                  {runtimeStatusLabel}
                </Badge>
              </div>
              {runtimeAlert ? (
                <div className="mt-4 space-y-2 rounded-2xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">
                  <p>{runtimeAlert.error}</p>
                  <p className="text-xs text-rose-200/80">
                    {runtimeAlert.model ?? "?"} • {runtimeAlert.provider ?? "LLM"}
                    {runtimeAlert.endpoint ? ` @ ${runtimeAlert.endpoint}` : ""}
                  </p>
                  {runtimeAlertDismissible ? (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={() => setLlmAlert(null)}
                    >
                      Ukryj alert
                    </Button>
                  ) : null}
                </div>
              ) : (
                <p className="mt-4 text-xs text-zinc-400">
                  Monitoruję błędy SSE i raportuję źródło modelu przy każdej odpowiedzi.
                </p>
              )}
            </div>
            <div className="rounded-3xl border border-white/10 bg-black/30 p-4">
              <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                Instalacja
              </p>
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
                        setMessage(
                          err instanceof Error ? err.message : "Błąd instalacji",
                        );
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
                Obsługiwany format: `phi3:mini`, `mistral:7b` itd. (Ollama). Modele do vLLM skopiuj
                do katalogu `./models` lub `./data/models` i ponownie wczytaj serwer.
              </p>
            </div>
            {groupedModels.every((entry) => entry.items.length === 0) ? (
              <EmptyState
                icon={<Package className="h-4 w-4" />}
                title="Brak modeli"
                description="Zainstaluj model, aby rozpocząć pracę."
              />
            ) : (
              <>
                {groupedModels.map(({ provider, items }) => {
                  const meta =
                    modelProviderMeta[provider] ?? {
                      title: `Modele ${provider}`,
                      description: "Modele przypisane do tego runtime.",
                    };
                  return (
                    <div
                      key={`provider-${provider}`}
                      className="rounded-3xl border border-white/10 bg-white/5 p-4"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                            {meta.title}
                          </p>
                          <p className="text-xs text-zinc-400">{meta.description}</p>
                          {meta.installHint && (
                            <p className="text-[11px] text-zinc-500">{meta.installHint}</p>
                          )}
                        </div>
                        <Badge tone="neutral">{provider.toUpperCase()}</Badge>
                      </div>
                      {items.length === 0 ? (
                        <div className="mt-4">
                          <EmptyState
                            icon={<Package className="h-4 w-4" />}
                            title="Brak modeli"
                            description="Dodaj model do tego runtime."
                          />
                        </div>
                      ) : (
                        <div className="mt-4 grid gap-3">
                          {items.map((model) => (
                            <ModelListItem
                              key={`${provider}-${model.name}`}
                              name={model.name}
                              sizeGb={model.size_gb}
                              source={model.source || model.type || model.path}
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
                  );
                })}
                {modelHistoryEntries.length > 0 && (
                  <div className="mt-6 space-y-2">
                    <p className="text-[11px] uppercase tracking-[0.35em] text-zinc-500">
                      Historia modeli
                      </p>
                      <div className="grid gap-3 sm:grid-cols-2">
                        {modelHistoryEntries.map((entry) => (
                          <ListCard
                            key={`history-${entry.name}`}
                            title={entry.name}
                            subtitle={entry.sourceLabel}
                            badge={<Badge tone={entry.badgeTone}>{entry.statusLabel}</Badge>}
                            meta={`Rozmiar: ${entry.sizeLabel} • Kwantyzacja: ${entry.quantizationLabel}`}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </Panel>
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
                      typeof payload === "string"
                        ? payload
                        : JSON.stringify(payload, null, 2);
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
              {tasksPreview.map((task, index) => (
                <ListCard
                  key={`${task.task_id ?? task.id ?? "task"}-${index}`}
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
        </div>
        <div className="space-y-6">
          <div className="glass-panel command-console-panel relative flex min-h-[520px] flex-col overflow-hidden px-6 py-6">
            <SectionHeading
              eyebrow="Command Console"
              title="Cockpit AI"
              description="Chat operacyjny z Orchestratora i logami runtime."
              as="h1"
              size="lg"
              className="items-center"
              rightSlot={
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={labMode ? "warning" : "success"}>
                    {labMode ? "Lab Mode" : "Prod"}
                  </Badge>
                  <Badge tone={responseBadgeTone} title={responseBadgeTitle}>
                    Odpowiedź {responseBadgeText}
                  </Badge>
                </div>
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
                      const requestId = msg.requestId;
                      const isSelected = selectedRequestId === requestId;
                      const canInspect = Boolean(requestId) && !msg.pending;
                      const handleSelect =
                        canInspect && requestId
                          ? () => openRequestDetail(requestId, msg.prompt)
                          : undefined;
                      return (
                        <motion.div
                          key={msg.bubbleId}
                          layout
                          initial={{ opacity: 0, y: 12 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -12 }}
                        >
                          <ConversationBubble
                            role={msg.role}
                            timestamp={msg.timestamp}
                            text={msg.text}
                            status={msg.status}
                            requestId={msg.requestId ?? undefined}
                            isSelected={isSelected}
                            pending={msg.pending}
                            onSelect={handleSelect}
                          />
                        </motion.div>
                      );
                    })}
                  </AnimatePresence>
                  {historyLoading && (
                    <p className="flex items-center gap-2 text-xs text-zinc-500">
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-400" />
                      Odświeżam historię…
                    </p>
                  )}
                </div>
                <div className="sticky bottom-0 mt-4 border-t border-white/5 pt-4">
                  <textarea
                    className="min-h-[120px] w-full rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/60 2xl:text-base"
                    placeholder="Opisz zadanie dla Venoma..."
                    value={taskContent}
                    onChange={(e) => setTaskContent(e.target.value)}
                    onKeyDown={handleTextareaKeyDown}
                    data-testid="cockpit-prompt-input"
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
                        onClick={handleOpenTuning}
                        className="text-zinc-300"
                        title="Dostosuj parametry generacji"
                      >
                        <Settings className="h-4 w-4 mr-1" />
                        Tuning
                      </Button>
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
                        data-testid="cockpit-send-button"
                      >
                        {sending ? "Wysyłanie..." : "Wyślij"}
                      </Button>
                    </div>
                  </div>
                </div>

                <QuickActions open={quickActionsOpen} onOpenChange={setQuickActionsOpen} />
                {message && (
                  <p className="mt-2 text-xs text-amber-300">{message}</p>
                )}
              </div>
            </div>
          </div>
          <div className="mt-4 space-y-3 rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-zinc-300">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11px] uppercase tracking-[0.35em] text-zinc-500">
                Sugestie szybkich promptów
              </p>
              <span className="text-[11px] uppercase tracking-[0.3em] text-zinc-600">
                Kliknij, aby wypełnić chat
              </span>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {promptPresets.map((preset) => (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => handleSuggestionClick(preset.prompt)}
                  title={preset.description}
                  className="flex items-center gap-3 rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-left transition hover:border-violet-400/50 hover:bg-black/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-violet-500/60"
                >
                  <span className="rounded-2xl bg-white/10 px-3 py-2 text-lg">
                    {preset.icon}
                  </span>
                  <div className="flex-1">
                    <p className="font-semibold text-white">{preset.category}</p>
                    <p className="text-xs text-zinc-400">{preset.description}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
          <div className="grid gap-6">
            <Panel
              eyebrow="KPI kolejki"
              title="Skuteczność operacji"
              description="Monitoruj SLA tasków i uptime backendu."
              className="kpi-panel"
            >
              {metricsLoading && !metrics ? (
                <PanelLoadingState label="Ładuję metryki zadań…" />
              ) : successRate === null ? (
                <EmptyState
                  icon={<Bot className="h-4 w-4" />}
                  title="Brak danych SLA"
                  description="Po uruchomieniu zadań i aktualizacji /metrics pojawi się trend skuteczności."
                />
              ) : (
                <CockpitMetricCard
                  primaryValue={`${successRate}%`}
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
              )}
            </Panel>
            <Panel
              eyebrow="KPI kolejki"
              title="Zużycie tokenów"
              description="Trend prompt/completion/cached."
              className="kpi-panel"
            >
              {tokenMetricsLoading && !tokenMetrics ? (
                <PanelLoadingState label="Ładuję statystyki tokenów…" />
              ) : (
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
              )}
            </Panel>
          </div>
          <Panel
            eyebrow="Live telemetry"
            title="Zdarzenia /ws/events"
            description="Najświeższe sygnały TASK_* i QUEUE_* – pozwalają śledzić napływające wyniki bez przeładowania."
          >
            {telemetryFeed.length === 0 ? (
              <p className="text-sm text-zinc-500">Brak zdarzeń – czekam na telemetrię.</p>
            ) : (
              <div className="space-y-2">
                {telemetryFeed.map((event) => (
                  <div
                    key={event.id}
                    className="flex items-start justify-between rounded-2xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
                  >
                    <div>
                      <p className="font-semibold">{event.type}</p>
                      <p className="text-xs text-zinc-400">{event.message}</p>
                    </div>
                    <div className="text-right text-xs text-zinc-500">
                      <Badge tone={event.tone}>{event.timestamp}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </section>
      <section className="grid gap-6">
        <Panel
          title="Zasoby"
          description="Śledź wykorzystanie CPU/GPU/RAM/VRAM/Dysk oraz koszt sesji."
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <ResourceMetricCard
              label="CPU"
              value={cpuUsageValue}
              hint="Średnie obciążenie modeli"
            />
            <ResourceMetricCard
              label="GPU"
              value={gpuUsageValue}
              hint="Wskaźnik wykorzystania akceleratora"
            />
            <ResourceMetricCard
              label="RAM"
              value={ramValue}
              hint={usageMetrics?.memory_usage_percent ? `${usageMetrics.memory_usage_percent.toFixed(0)}%` : ""}
            />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <ResourceMetricCard
              label="VRAM"
              value={vramValue}
              hint="Aktywny model/GPU"
            />
            <ResourceMetricCard
              label="Dysk"
              value={diskValue}
              hint={diskPercent ?? ""}
            />
          </div>
          <div className="mt-4 flex items-center justify-between rounded-2xl border border-white/10 bg-black/30 px-4 py-3 text-xs text-zinc-400">
            <span className="uppercase tracking-[0.35em]">Koszt sesji</span>
            <span className="text-base font-semibold text-white">{sessionCostValue}</span>
          </div>
        </Panel>
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

      <Panel
        eyebrow="System KPIs"
        title="Status operacyjny"
        description="Najważniejsze liczby backendu."
        className="kpi-panel"
      >
        <div className="grid gap-4 md:grid-cols-4">
          <StatCard
            label="Zadania"
            value={metrics?.tasks?.created ?? "—"}
            hint="Łącznie utworzonych"
          />
          <StatCard
            label="Skuteczność"
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
            value={queue ? `${queue.active ?? 0} / ${queue.limit ?? "∞"}` : "—"}
            hint="Aktywne / limit"
            accent="blue"
          />
        </div>
      </Panel>

      <Panel
        title="Zarządzanie kolejką"
        description="Stan kolejki `/api/v1/queue/status`, koszty sesji i akcje awaryjne."
        className="queue-panel"
      >
        {queue ? (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatCard
                label="Aktywne"
                value={queue.active ?? "—"}
                hint="Zadania w toku"
                accent="violet"
              />
              <StatCard
                label="Oczekujące"
                value={queue.pending ?? "—"}
                hint="Czekają na wykonanie"
                accent="indigo"
              />
              <StatCard
                label="Limit"
                value={queue.limit ?? "∞"}
                hint="Maksymalna pojemność"
                accent="blue"
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="xs"
                onClick={handleToggleQueue}
                disabled={queueAction === "pause" || queueAction === "resume"}
              >
                {queue.paused ? "Wznów kolejkę" : "Wstrzymaj kolejkę"}
              </Button>
              <Button
                variant="outline"
                size="xs"
                onClick={() => executeQueueMutation("purge")}
                disabled={queueAction === "purge"}
              >
                Wyczyść kolejkę
              </Button>
              <Button
                variant="danger"
                size="xs"
                onClick={() => executeQueueMutation("emergency")}
                disabled={queueAction === "emergency"}
              >
                Awaryjne zatrzymanie
              </Button>
            </div>
            {queueActionMessage && (
              <p className="mt-2 text-xs text-zinc-400">{queueActionMessage}</p>
            )}
          </>
        ) : (
          <EmptyState
            icon={<Package className="h-4 w-4" />}
            title="Kolejka offline"
            description="Brak danych `/api/v1/queue/status` – sprawdź backend lub użyj Quick Actions."
          />
        )}
      </Panel>

      <div className="grid gap-6">
        <Panel
          title="Historia requestów"
          description="Ostatnie /api/v1/history/requests – kliknij, by odczytać szczegóły."
        >
          <HistoryList
            entries={history}
            limit={5}
            selectedId={selectedRequestId}
            onSelect={(entry) => openRequestDetail(entry.request_id, entry.prompt)}
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

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <VoiceCommandCenter />
        <IntegrationMatrix services={services} events={entries} />
      </section>

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
          title="Zarządzanie kolejką"
        description="Stan kolejki i szybkie akcje – zarządzaj z jednego miejsca."
        action={
          <Badge tone={queue?.paused ? "warning" : "success"}>
            {queue?.paused ? "Wstrzymana" : "Aktywna"}
          </Badge>
        }
      >
        <div className="space-y-4">
          <QueueStatusCard queue={queue} loading={queueLoading && !queue} />
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
            setSelectedTask(null);
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
              <div className="mt-4 rounded-2xl border border-white/10 bg-black/40 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
                      Źródło LLM
                    </p>
                    <p className="mt-2 text-base font-semibold text-white">
                      {historyDetail.llm_model ?? "Nieznany model"}
                    </p>
                    <p className="text-xs text-zinc-400">
                      {historyDetail.llm_provider ?? "—"}
                      {historyDetail.llm_endpoint ? ` @ ${historyDetail.llm_endpoint}` : ""}
                    </p>
                  </div>
                  <Badge tone={selectedTaskRuntime?.status === "error" ? "danger" : "success"}>
                    {selectedTaskRuntime?.status === "error" ? "Błąd" : "OK"}
                  </Badge>
                </div>
                {selectedTaskRuntime?.error && (
                  <p className="mt-3 rounded-xl border border-rose-400/30 bg-rose-500/10 p-2 text-xs text-rose-100">
                    {selectedTaskRuntime.error}
                  </p>
                )}
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
              {selectedTask && (
                <div className="mt-4 rounded-2xl border border-emerald-400/10 bg-emerald-400/5 p-4">
                  <p className="text-xs uppercase tracking-[0.3em] text-emerald-200">
                    Odpowiedź / wynik
                  </p>
                  <div className="mt-2 text-sm text-white">
                    <MarkdownPreview
                      content={
                        selectedTask.result && selectedTask.result.trim().length > 0
                          ? selectedTask.result
                          : "Brak odpowiedzi. Zadanie mogło zakończyć się niepowodzeniem lub jeszcze trwa."
                      }
                      emptyState="Brak danych wyjściowych."
                    />
                  </div>
                </div>
              )}
              {selectedTask?.logs && selectedTask.logs.length > 0 && (
                <div className="mt-4 rounded-2xl border border-white/10 bg-black/40 p-4">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-semibold text-white">
                      Logi zadania ({selectedTask.logs.length})
                    </h4>
                  </div>
                  <div className="mt-3 max-h-[180px] space-y-2 overflow-y-auto pr-2 text-xs text-zinc-300">
                    {selectedTask.logs.map((log, idx) => (
                      <p
                        key={`task-log-${idx}`}
                        className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                      >
                        {log}
                      </p>
                    ))}
                  </div>
                </div>
              )}
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

      {/* Tuning Drawer */}
      <Sheet open={tuningOpen} onOpenChange={setTuningOpen}>
        <SheetContent className="w-full sm:max-w-md overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Parametry Generacji</SheetTitle>
            <SheetDescription>
              Dostosuj parametry modelu, takie jak temperatura, max_tokens, etc.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-6">
            {loadingSchema && (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-violet-500" />
              </div>
            )}
            {!loadingSchema && !modelSchema && (
              <p className="text-sm text-zinc-400">
                Brak schematu parametrów dla aktywnego modelu.
              </p>
            )}
            {!loadingSchema && modelSchema && (
              <DynamicParameterForm
                schema={modelSchema}
                values={generationParams || undefined}
                onChange={(values) => setGenerationParams(values)}
                onReset={() => setGenerationParams(null)}
              />
            )}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

function PanelLoadingState({ label }: { label: string }) {
  return (
    <div className="flex h-32 items-center justify-center text-sm text-zinc-400">
      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
      {label}
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

function mapTelemetryTone(type: string): "success" | "warning" | "danger" | "neutral" {
  if (type.includes("FAILED") || type.includes("ERROR")) return "danger";
  if (type.includes("PAUSED") || type.includes("PURGED")) return "warning";
  if (type.includes("COMPLETED") || type.includes("RESUMED")) return "success";
  return "neutral";
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

type ChatMessage = {
  bubbleId: string;
  requestId: string | null;
  role: "user" | "assistant";
  text: string;
  status?: string | null;
  timestamp: string;
  prompt?: string;
  pending?: boolean;
};

type OptimisticRequestState = {
  clientId: string;
  requestId: string | null;
  prompt: string;
  createdAt: string;
  startedAt: number;
  confirmed: boolean;
};

type TokenSample = { timestamp: string; value: number };
type TelemetryFeedEntry = {
  id: string;
  type: string;
  message: string;
  timestamp: string;
  tone: "success" | "warning" | "danger" | "neutral";
};
export type MacroAction = {
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

type ResourceMetricCardProps = {
  label: string;
  value: string;
  hint?: string;
};

function ResourceMetricCard({ label, value, hint }: ResourceMetricCardProps) {
  return (
    <div className="rounded-2xl border border-white/10 bg-black/30 p-3 text-sm text-white">
      <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{label}</p>
      <p className="mt-2 text-2xl font-semibold">{value}</p>
      {hint ? <p className="text-[11px] text-zinc-400">{hint}</p> : null}
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

function createOptimisticId() {
  return `opt-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`;
}

export default CockpitHome;

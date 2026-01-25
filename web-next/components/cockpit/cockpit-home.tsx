"use client";

import { Button } from "@/components/ui/button";
import {
  emergencyStop,
  activateRegistryModel,
  fetchHistoryDetail,
  fetchModelConfig,
  fetchTaskDetail,
  ingestMemoryEntry,
  purgeQueue,
  sendSimpleChatStream,
  sendTask,
  sendFeedback,
  setActiveHiddenPrompt,
  setActiveLlmServer,
  setActiveLlmRuntime,
  clearSessionMemory,
  clearGlobalMemory,
  updateModelConfig,
  switchModel,
  toggleQueue,
  useGitStatus,
  useFeedbackLogs,
  useActiveHiddenPrompts,
  useActiveLlmServer,
  useGraphSummary,
  useHistory,
  useSessionHistory,
  useHiddenPrompts,
  useLlmServers,
  useLearningLogs,
  useMetrics,
  useModels,
  useModelsUsage,
  useQueueStatus,
  useServiceStatus,
  useTasks,
  useTokenMetrics,
} from "@/hooks/use-api";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useTaskStream } from "@/hooks/use-task-stream";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import { useSession } from "@/lib/session";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  GenerationParams,
  HistoryRequestDetail,
  ServiceStatus,
  Task,
} from "@/lib/types";
import type { CockpitInitialData } from "@/lib/server-data";
import { LogEntryType } from "@/lib/logs";
import { statusTone } from "@/lib/status";
import { formatRelativeTime } from "@/lib/date";
import { useCockpitChatUi } from "@/components/cockpit/cockpit-chat-ui";
import { useCockpitSessionActions } from "@/components/cockpit/cockpit-session-actions";
import { useCockpitLlmServerActions } from "@/components/cockpit/cockpit-llm-server-actions";
import { PROMPT_PRESETS } from "@/components/cockpit/cockpit-prompts";
import {
  useDetailTaskSync,
  useTelemetryRefreshEffect,
  useTokenHistoryBuffer,
} from "@/components/cockpit/cockpit-effects";
import { useTranslation } from "@/lib/i18n";
import Link from "next/link";
import type { GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import {
  type ChatComposerHandle,
  type ChatMessage,
  type ChatMode,
} from "@/components/cockpit/cockpit-chat-thread";
import { CockpitHeader } from "@/components/cockpit/cockpit-header";
import { CockpitPrimarySection } from "@/components/cockpit/cockpit-primary-section";
import { CockpitRuntimeSection } from "@/components/cockpit/cockpit-runtime-section";
import { useCockpitSectionProps } from "@/components/cockpit/cockpit-section-props";
import { useOptimisticRequests } from "@/components/cockpit/cockpit-chat-hooks";
import type { TokenSample } from "@/components/cockpit/token-types";
import {
  extractContextPreviewMeta,
  extractPayloadContextDetails,
  isTelemetryEventPayload,
  normalizeMatchValue,
  RESPONSE_SOURCE_LABELS,
  sanitizeAssistantText,
  TELEMETRY_REFRESH_EVENTS,
  TERMINAL_STATUSES,
} from "@/components/cockpit/cockpit-utils";
import {
  useHistorySummary,
  useLlmServerSelectionData,
  useMacroActions,
  useQueueActions,
  type SessionHistoryEntry,
  useSessionHistoryState,
  useServiceStatusMap,
  useTasksIndex,
  useTelemetryFeedEntries,
  useHiddenPromptState,
  useTrackedRequestIds,
  useTokenMetricsSummary,
} from "@/components/cockpit/cockpit-hooks";
import { useCockpitRequestDetailActions } from "@/components/cockpit/cockpit-request-detail-actions";
import {
  formatDiskSnapshot,
  formatGbPair,
  formatPercentMetric,
  formatUsd,
  formatVramMetric,
} from "@/lib/formatters";

export function CockpitHome({
  initialData,
  variant = "reference",
}: {
  initialData: CockpitInitialData;
  variant?: "reference" | "home";
}) {
  const [isClientReady, setIsClientReady] = useState(false);
  useEffect(() => {
    setIsClientReady(true);
  }, []);
  const showReferenceSections = variant === "reference";
  const showSharedSections = variant === "reference" || variant === "home";
  const [showArtifacts, setShowArtifacts] = useState(true);
  useEffect(() => {
    setShowArtifacts(true);
  }, [showReferenceSections]);
  const [labMode, setLabMode] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>("normal");
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [llmActionPending, setLlmActionPending] = useState<string | null>(null);
  const [selectedLlmServer, setSelectedLlmServer] = useState("");
  const [selectedLlmModel, setSelectedLlmModel] = useState("");
  const [historyDetail, setHistoryDetail] = useState<HistoryRequestDetail | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [tokenHistory, setTokenHistory] = useState<TokenSample[]>([]);
  const [pinnedLogs, setPinnedLogs] = useState<LogEntryType[]>([]);
  const [logFilter, setLogFilter] = useState("");
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [copyStepsMessage, setCopyStepsMessage] = useState<string | null>(null);
  const [feedbackByRequest, setFeedbackByRequest] = useState<
    Record<
      string,
      { rating?: "up" | "down" | null; comment?: string; message?: string | null }
    >
  >({});
  const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<string | null>(null);
  const [quickActionsOpen, setQuickActionsOpen] = useState(false);
  const [exportingPinned, setExportingPinned] = useState(false);
  const [gitAction, setGitAction] = useState<"sync" | "undo" | null>(null);
  const [memoryAction, setMemoryAction] = useState<null | "session" | "global">(null);
  const {
    optimisticRequests,
    simpleStreams,
    simpleRequestDetails,
    setSimpleRequestDetails,
    uiTimingsByRequest,
    uiTimingsRef,
    enqueueOptimisticRequest,
    linkOptimisticRequest,
    dropOptimisticRequest,
    updateSimpleStream,
    recordUiTiming,
    clearSimpleStream,
    pruneOptimisticRequests,
  } = useOptimisticRequests<HistoryRequestDetail>(chatMode);
  const [lastResponseDurationMs, setLastResponseDurationMs] = useState<number | null>(null);
  const [responseDurations, setResponseDurations] = useState<number[]>([]);
  const lastTelemetryRefreshRef = useRef<string | null>(null);
  const [tuningOpen, setTuningOpen] = useState(false);
  const [generationParams, setGenerationParams] = useState<GenerationParams | null>(null);
  const [modelSchema, setModelSchema] = useState<GenerationSchema | null>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [tuningSaving, setTuningSaving] = useState(false);
  const { sessionId, resetSession } = useSession();
  const [chatFullscreen, setChatFullscreen] = useState(false);
  const { pushToast } = useToast();
  const {
    handleClearGlobalMemory,
    handleClearSessionMemory,
    handleServerSessionReset,
    handleSessionReset,
  } = useCockpitSessionActions({
    sessionId,
    resetSession,
    clearSessionMemory,
    clearGlobalMemory,
    setMessage,
    setMemoryAction,
    pushToast,
  });

  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const t = useTranslation();
  const streamCompletionRef = useRef<Set<string>>(new Set());
  const promptPresets = PROMPT_PRESETS;
  const { data: liveMetrics, loading: metricsLoading, refresh: refreshMetrics } = useMetrics(0);
  const metrics = liveMetrics ?? initialData.metrics ?? null;
  const { data: liveTasks, refresh: refreshTasks } = useTasks(0);
  const tasks = liveTasks ?? initialData.tasks ?? null;
  const { data: liveQueue, loading: queueLoading, refresh: refreshQueue } = useQueueStatus(0);
  const queue = liveQueue ?? initialData.queue ?? null;
  const { data: liveServices, refresh: refreshServices } = useServiceStatus();
  const { data: liveLlmServers, loading: llmServersLoading, refresh: refreshLlmServers } =
    useLlmServers();
  const { data: liveActiveServer, refresh: refreshActiveServer } = useActiveLlmServer(15000);
  const services = liveServices ?? initialData.services ?? null;
  const { data: liveGraph } = useGraphSummary();
  const graph = liveGraph ?? initialData.graphSummary ?? null;
  const { data: liveModels, refresh: refreshModels } = useModels();
  const models = liveModels ?? initialData.models ?? null;
  const { data: liveGit, refresh: refreshGit } = useGitStatus();
  const git = liveGit ?? initialData.gitStatus ?? null;
  const { data: liveTokenMetrics, loading: tokenMetricsLoading, refresh: refreshTokenMetrics } =
    useTokenMetrics(0);
  const tokenMetrics = liveTokenMetrics ?? initialData.tokenMetrics ?? null;
  const { data: liveHistory, loading: historyLoading, refresh: refreshHistory } = useHistory(6, 0);
  const history = liveHistory ?? initialData.history ?? null;
  const { data: sessionHistoryData, refresh: refreshSessionHistory } = useSessionHistory(sessionId, 0);
  const {
    sessionHistory,
    localSessionHistory,
    setLocalSessionHistory,
    sessionEntryKey,
  } = useSessionHistoryState({
    sessionId,
    sessionHistoryData,
    refreshSessionHistory,
    refreshHistory,
  });
  const { data: learningLogs, loading: learningLoading, error: learningError } = useLearningLogs(6);
  const { data: feedbackLogs, loading: feedbackLoading, error: feedbackError } = useFeedbackLogs(6);
  const [hiddenIntentFilter, setHiddenIntentFilter] = useState("all");
  const [hiddenScoreFilter, setHiddenScoreFilter] = useState(1);
  const hiddenIntentParam = hiddenIntentFilter === "all" ? undefined : hiddenIntentFilter;
  const {
    data: hiddenPrompts,
    loading: hiddenLoading,
    error: hiddenError,
  } = useHiddenPrompts(6, 20000, hiddenIntentParam, hiddenScoreFilter);
  const {
    data: activeHiddenPrompts,
    loading: activeHiddenLoading,
    error: activeHiddenError,
  } = useActiveHiddenPrompts(hiddenIntentParam, 20000);
  const feedbackUp = metrics?.feedback?.up ?? 0;
  const feedbackDown = metrics?.feedback?.down ?? 0;
  const feedbackTotal = feedbackUp + feedbackDown;
  const feedbackScore =
    feedbackTotal > 0 ? Math.round((feedbackUp / feedbackTotal) * 100) : null;
  const {
    activeHiddenKeys,
    activeHiddenMap,
    hiddenIntentOptions,
    selectableHiddenPrompts,
    activeForIntent,
    isHiddenResponse,
  } = useHiddenPromptState({
    hiddenPrompts,
    activeHiddenPrompts,
    hiddenIntentFilter,
  });
  const trackedRequestIds = useTrackedRequestIds({
    optimisticRequests,
    history,
    selectedRequestId,
  });
  const { streams: taskStreams } = useTaskStream(trackedRequestIds, {
    enabled: isClientReady && trackedRequestIds.length > 0,
    throttleMs: 250,
    onEvent: (event) => {
      if (!event.taskId || !event.result) return;
      const timing = uiTimingsRef.current.get(event.taskId);
      if (!timing || timing.ttftMs !== undefined) return;
      const ttftMs = Date.now() - timing.t0;
      recordUiTiming(event.taskId, { ttftMs });
      console.info(`[TTFT] ${event.taskId}: ${ttftMs}ms`);
    },
  });
  const { data: liveModelsUsageResponse, refresh: refreshModelsUsage } = useModelsUsage(0);
  const modelsUsageResponse =
    liveModelsUsageResponse ?? initialData.modelsUsage ?? null;
  const { connected, entries } = useTelemetryFeed();
  const usageMetrics = modelsUsageResponse?.usage ?? null;
  const llmServers = useMemo(() => liveLlmServers ?? [], [liveLlmServers]);
  const activeServerInfo = liveActiveServer ?? null;
  const activeServerName = activeServerInfo?.active_server ?? "";
  const { language } = useLanguage();
  const {
    selectedServerEntry,
    availableModelsForServer,
    llmServerOptions,
    llmModelOptions,
  } = useLlmServerSelectionData({
    llmServers,
    models,
    selectedLlmServer,
    activeServerInfo,
  });
  const { tasksByPrompt, tasksById } = useTasksIndex(tasks);
  const serviceStatusMap = useServiceStatusMap(services);
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

  const {
    handleChatModelSelect,
    handleLlmServerActivate,
    resolveServerStatus,
  } = useCockpitLlmServerActions({
    selectedLlmServer,
    selectedLlmModel,
    setSelectedLlmServer,
    setSelectedLlmModel,
    setMessage,
    pushToast,
    setLlmActionPending,
    refreshLlmServers,
    refreshActiveServer,
    refreshModels,
    activeServerInfo,
    llmServers,
    availableModelsForServer,
    serviceStatusMap,
    activateRegistryModel,
    switchModel,
    setActiveLlmServer,
  });
  const {
    macroSending,
    customMacros,
    setCustomMacros,
    newMacro,
    setNewMacro,
    allMacros,
    handleMacroRun,
  } = useMacroActions({
    enqueueOptimisticRequest,
    linkOptimisticRequest,
    dropOptimisticRequest,
    sendTask,
    refreshTasks,
    refreshQueue,
    refreshHistory,
    labMode,
    activeConfigHash: activeServerInfo?.config_hash ?? null,
    activeRuntimeId: activeServerInfo?.runtime_id ?? null,
    language,
    sessionId,
    setMessage,
  });

  useTokenHistoryBuffer(tokenMetrics?.total_tokens, setTokenHistory);
  useDetailTaskSync({
    detailOpen,
    selectedRequestId,
    historyPrompt: historyDetail?.prompt,
    findTaskMatch,
    selectedTask,
    setSelectedTask,
  });

  useEffect(() => {
    pruneOptimisticRequests(history, (duration) => {
      setLastResponseDurationMs(duration);
      setResponseDurations((prev) => {
        const next = [...prev, duration];
        return next.slice(-10);
      });
    });
  }, [history, pruneOptimisticRequests]);

  useTelemetryRefreshEffect({
    entries,
    lastTelemetryRefreshRef,
    refreshQueue,
    refreshTasks,
    refreshHistory,
    refreshSessionHistory,
    refreshMetrics,
    refreshTokenMetrics,
    refreshModelsUsage,
    refreshServices,
    shouldRefresh: (payload) =>
      isTelemetryEventPayload(payload) &&
      !!payload.type &&
      TELEMETRY_REFRESH_EVENTS.has(payload.type),
  });

  useEffect(() => {
    const activeIds = new Set(Object.keys(taskStreams));
    streamCompletionRef.current.forEach((trackedId) => {
      if (!activeIds.has(trackedId)) {
        streamCompletionRef.current.delete(trackedId);
      }
    });

    const entries = Object.entries(taskStreams);
    if (entries.length === 0) return;

    let shouldRefresh = false;
    for (const [taskId, state] of entries) {
      if (!state?.status) continue;
      if (!TERMINAL_STATUSES.has(state.status)) continue;
      if (streamCompletionRef.current.has(taskId)) continue;
      streamCompletionRef.current.add(taskId);
      const optimisticEntry = optimisticRequests.find((entry) => entry.requestId === taskId);
      if (optimisticEntry) {
        const assistantText =
          state.result?.trim() ||
          (state.logs?.length ? state.logs[state.logs.length - 1] : "") ||
          "Brak odpowiedzi.";
        const timestamp = new Date().toISOString();
        setLocalSessionHistory((prev) => {
          let hasUser = false;
          let hasAssistant = false;
          const next = prev.map((entry) => {
            if (entry.request_id !== taskId) return entry;
            if (entry.role === "user") {
              hasUser = true;
              return entry;
            }
            if (entry.role === "assistant") {
              hasAssistant = true;
              return {
                ...entry,
                content: assistantText,
                timestamp,
              };
            }
            return entry;
          });
          if (!hasUser) {
            next.push({
              role: "user",
              content: optimisticEntry.prompt,
              request_id: taskId,
              timestamp,
              session_id: sessionId ?? undefined,
            });
          }
          if (!hasAssistant) {
            next.push({
              role: "assistant",
              content: assistantText,
              request_id: taskId,
              timestamp,
              session_id: sessionId ?? undefined,
            });
          }
          return next;
        });
        window.setTimeout(() => {
          dropOptimisticRequest(optimisticEntry.clientId);
        }, 200);
        const duration = Date.now() - optimisticEntry.startedAt;
        if (Number.isFinite(duration)) {
          setLastResponseDurationMs(duration);
          setResponseDurations((prev) => {
            const next = [...prev, duration];
            return next.slice(-10);
          });
        }
      }
      shouldRefresh = true;
    }
    if (shouldRefresh) {
      refreshHistory();
      refreshTasks();
      refreshSessionHistory();
      refreshMetrics();
      refreshTokenMetrics();
      refreshModelsUsage();
      refreshServices();
    }
  }, [
    taskStreams,
    refreshHistory,
    refreshTasks,
    refreshSessionHistory,
    refreshMetrics,
    refreshTokenMetrics,
    refreshModelsUsage,
    refreshServices,
    optimisticRequests,
    dropOptimisticRequest,
    sessionEntryKey,
    sessionId,
  ]);

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
  const diskValue =
    usageMetrics?.disk_system_used_gb !== undefined &&
      usageMetrics?.disk_system_total_gb !== undefined
      ? formatDiskSnapshot(usageMetrics.disk_system_used_gb, usageMetrics.disk_system_total_gb)
      : formatDiskSnapshot(usageMetrics?.disk_usage_gb, usageMetrics?.disk_limit_gb);
  const diskPercent =
    usageMetrics?.disk_system_usage_percent !== undefined
      ? `${usageMetrics.disk_system_usage_percent.toFixed(1)}%`
      : usageMetrics?.disk_usage_percent !== undefined
        ? `${usageMetrics.disk_usage_percent.toFixed(1)}%`
        : null;
  const sessionCostValue = formatUsd(tokenMetrics?.session_cost_usd);
  const requestModeById = useMemo(() => {
    const modeMap = new Map<string, string>();
    optimisticRequests.forEach((entry) => {
      const id = entry.requestId ?? entry.clientId;
      if (!id) return;
      if (entry.simpleMode) {
        modeMap.set(id, "Direct");
        return;
      }
      const label =
        entry.chatMode === "complex"
          ? "Complex"
          : entry.chatMode === "normal"
            ? "Normal"
            : entry.chatMode === "direct"
              ? "Direct"
              : null;
      if (label) {
        modeMap.set(id, label);
      }
    });
    Object.keys(simpleRequestDetails).forEach((id) => {
      if (!modeMap.has(id)) {
        modeMap.set(id, "Direct");
      }
    });
    return modeMap;
  }, [optimisticRequests, simpleRequestDetails]);

  const historyMessages = useMemo<ChatMessage[]>(() => {
    const resolvedHistory =
      localSessionHistory.length > 0 ? localSessionHistory : sessionHistory;
    if (resolvedHistory.length > 0) {
      const seenMap = new Map<string, SessionHistoryEntry>();
      resolvedHistory.forEach((entry) => {
        const key = sessionEntryKey(entry);
        const existing = seenMap.get(key);
        if (!existing) {
          seenMap.set(key, entry);
        } else if (entry.timestamp && existing.timestamp) {
          if (new Date(entry.timestamp) > new Date(existing.timestamp)) {
            seenMap.set(key, entry);
          }
        } else if (entry.timestamp && !existing.timestamp) {
          seenMap.set(key, entry);
        }
      });
      const deduped = Array.from(seenMap.values());
      return deduped.map((entry, index) => {
        const role = entry.role === "assistant" ? "assistant" : "user";
        const requestId = entry.request_id ?? null;
        const timestamp = entry.timestamp ?? new Date().toISOString();
        const optimisticEntry = requestId
          ? optimisticRequests.find(
            (item) => item.requestId === requestId || item.clientId === requestId,
          )
          : null;
        const liveSimple = requestId ? simpleStreams[requestId] : null;
        const liveTask = requestId ? taskStreams[requestId] : null;
        const optimisticSimple =
          optimisticEntry?.simpleMode
            ? simpleStreams[optimisticEntry.clientId] ??
            (optimisticEntry.requestId
              ? simpleStreams[optimisticEntry.requestId]
              : null)
            : null;
        const optimisticTask = optimisticEntry?.requestId
          ? taskStreams[optimisticEntry.requestId]
          : null;
        const liveStatus =
          optimisticSimple?.status ??
          liveSimple?.status ??
          optimisticTask?.status ??
          liveTask?.status ??
          "COMPLETED";
        const livePending = optimisticSimple
          ? !optimisticSimple.done
          : optimisticTask?.status
            ? !TERMINAL_STATUSES.has(optimisticTask.status)
            : liveSimple
              ? !liveSimple.done
              : liveTask?.status
                ? !TERMINAL_STATUSES.has(liveTask.status)
                : false;
        const liveText =
          role === "assistant" && optimisticSimple?.text
            ? optimisticSimple.text
            : role === "assistant" && liveSimple?.text
              ? liveSimple.text
              : role === "assistant" && optimisticTask?.result
                ? optimisticTask.result
                : role === "assistant" && liveTask?.result
                  ? liveTask.result
                  : entry.content || "Brak treści.";
        return {
          bubbleId: `session-${index}-${role}`,
          requestId,
          role,
          text: liveText,
          status: liveStatus,
          timestamp,
          prompt: entry.content || "",
          pending: role === "assistant" ? livePending : false,
          forcedTool: null,
          forcedProvider: null,
        };
      });
    }
    if (!history) return [];
    const sortedHistory = [...history].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return aTime - bTime;
    });
    return sortedHistory.flatMap((item) => {
      const prompt = item.prompt?.trim() ?? "";
      const matchedTask = findTaskMatch(item.request_id, prompt);
      const assistantText =
        matchedTask?.result?.trim() ??
        (item.status === "COMPLETED"
          ? "Brak zapisanej odpowiedzi – sprawdź szczegóły zadania."
          : "Odpowiedź w trakcie generowania");
      const sanitizedAssistantText = sanitizeAssistantText(assistantText);
      const displayAssistantText = sanitizedAssistantText.trim().length > 0
        ? sanitizedAssistantText
        : "Odpowiedź gotowa – sprawdź szczegóły zadania.";
      const assistantSourceLabel = isHiddenResponse(displayAssistantText)
        ? RESPONSE_SOURCE_LABELS.hidden
        : RESPONSE_SOURCE_LABELS.history;
      const assistantStatus = matchedTask?.status ?? item.status;
      const assistantTimestamp =
        matchedTask?.updated_at ||
        matchedTask?.created_at ||
        item.finished_at ||
        item.created_at;
      const modeLabel = requestModeById.get(item.request_id) ?? null;
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
          forcedTool: item.forced_tool ?? null,
          forcedProvider: item.forced_provider ?? null,
          modeLabel,
        },
        {
          bubbleId: `${item.request_id}-response`,
          requestId: item.request_id,
          role: "assistant",
          text: displayAssistantText,
          status: assistantStatus,
          timestamp: assistantTimestamp ?? item.created_at,
          prompt,
          pending: !TERMINAL_STATUSES.has(item.status),
          forcedTool: item.forced_tool ?? null,
          forcedProvider: item.forced_provider ?? null,
          modeLabel,
          sourceLabel: assistantSourceLabel,
          contextUsed: null, // History summary doesn't have context info yet
        },
      ];
    });
  }, [
    history,
    localSessionHistory,
    sessionHistory,
    findTaskMatch,
    sessionEntryKey,
    requestModeById,
    isHiddenResponse,
  ]);

  const optimisticMessages = useMemo<ChatMessage[]>(() => {
    const historySnapshot =
      localSessionHistory.length > 0 ? localSessionHistory : sessionHistory;
    return optimisticRequests.flatMap((entry) => {
      const baseId = entry.requestId ?? entry.clientId;
      const simpleStream = entry.simpleMode ? simpleStreams[entry.clientId] : null;
      const stream = entry.requestId ? taskStreams[entry.requestId] : null;
      const historyAssistant = entry.requestId
        ? historySnapshot.find(
          (item) =>
            item.request_id === entry.requestId &&
            item.role === "assistant" &&
            (item.content || "").trim().length > 0,
        )
        : null;
      const historyAssistantText = (historyAssistant?.content || "").trim();
      const hasHistoryAssistant = historyAssistantText.length > 0;
      const lastVisibleLog =
        stream?.logs
          ?.slice()
          .reverse()
          .find((log) => {
            const trimmed = (log || "").trim();
            if (!trimmed) return false;
            const normalized = trimmed.toLowerCase();
            if (normalized.startsWith("sesja:")) return false;
            return true;
          }) ?? null;
      const assistantText = entry.simpleMode
        ? simpleStream?.text ?? ""
        : stream?.result && stream.result.trim().length > 0
          ? stream.result
          : lastVisibleLog
            ? lastVisibleLog
            : hasHistoryAssistant
              ? historyAssistantText
              : "Generuję odpowiedź";
      const sanitizedAssistantText = sanitizeAssistantText(assistantText);
      const displayAssistantText =
        sanitizedAssistantText.trim().length > 0
          ? sanitizedAssistantText
          : "Odpowiedź gotowa.";
      const assistantStatus = entry.simpleMode
        ? simpleStream?.status ?? "W toku"
        : stream?.status ??
        (stream?.error ? "Błąd strumienia" : stream ? "W toku" : "W kolejce");
      const terminal = entry.simpleMode
        ? Boolean(simpleStream?.done)
        : stream?.status === "COMPLETED" ||
        stream?.status === "FAILED" ||
        hasHistoryAssistant;
      const pendingGraceMs = Math.min(
        1200,
        Math.max(300, Math.floor(assistantText.length * 4)),
      );
      const inGraceWindow =
        terminal && Date.now() - entry.startedAt < pendingGraceMs;
      const isPending = !terminal || inGraceWindow;
      const assistantSourceLabel = isPending
        ? RESPONSE_SOURCE_LABELS.live
        : isHiddenResponse(displayAssistantText)
          ? RESPONSE_SOURCE_LABELS.hidden
          : hasHistoryAssistant
            ? RESPONSE_SOURCE_LABELS.history
            : RESPONSE_SOURCE_LABELS.live;
      const hasUserInHistory = Boolean(
        entry.requestId &&
        historySnapshot.some(
          (item) => item.request_id === entry.requestId && item.role === "user",
        ),
      );
      const hasAssistantInHistory = Boolean(
        entry.requestId &&
        historySnapshot.some(
          (item) =>
            item.request_id === entry.requestId && item.role === "assistant",
        ),
      );
      // Jeśli mamy już requestId (zadanie w historii), nie pokazujemy optymistycznej odpowiedzi,
      // żeby uniknąć podwójnego mignięcia (optimistic + final).
      const showOptimisticAssistant = entry.simpleMode
        ? isPending || (!hasAssistantInHistory && !entry.requestId)
        : isPending || !hasAssistantInHistory;
      const modeLabel = entry.simpleMode
        ? "Direct"
        : entry.chatMode === "complex"
          ? "Complex"
          : entry.chatMode === "normal"
            ? "Normal"
            : entry.chatMode === "direct"
              ? "Direct"
              : null;
      const contextUsed = stream?.contextUsed ?? null;
      const messages: ChatMessage[] = [];
      if (!hasUserInHistory) {
        messages.push({
          bubbleId: `${baseId}-optimistic-prompt`,
          requestId: entry.requestId,
          role: "user",
          text: entry.prompt || "Brak treści zadania.",
          status: stream?.status ?? "Wysłano",
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
          forcedTool: entry.forcedTool ?? null,
          forcedProvider: entry.forcedProvider ?? null,
          modeLabel,
          contextUsed: null,
        });
      }
      if (showOptimisticAssistant) {
        messages.push({
          bubbleId: `${baseId}-optimistic-response`,
          requestId: entry.requestId,
          role: "assistant",
          text: displayAssistantText,
          status: assistantStatus,
          timestamp: entry.createdAt,
          prompt: entry.prompt,
          pending: isPending,
          forcedTool: entry.forcedTool ?? null,
          forcedProvider: entry.forcedProvider ?? null,
          modeLabel,
          sourceLabel: assistantSourceLabel,
          contextUsed,
        });
      }
      return messages;
    });
  }, [
    optimisticRequests,
    taskStreams,
    simpleStreams,
    localSessionHistory,
    sessionHistory,
    isHiddenResponse,
  ]);

  const chatMessages = useMemo(() => {
    const pendingOptimisticIds = new Set(
      optimisticMessages
        .filter((msg) => msg.role === "assistant" && msg.pending && msg.requestId)
        .map((msg) => msg.requestId as string),
    );
    const filteredHistory = pendingOptimisticIds.size
      ? historyMessages.filter(
        (msg) =>
          !(
            msg.role === "assistant" &&
            msg.requestId &&
            pendingOptimisticIds.has(msg.requestId)
          ),
      )
      : historyMessages;
    return [...filteredHistory, ...optimisticMessages];
  }, [historyMessages, optimisticMessages]);
  const {
    autoScrollEnabled,
    composerRef,
    handleApplyTuning,
    handleChatScroll,
    handleExportPinnedLogs,
    handleFeedbackClick,
    handleFeedbackSubmit,
    handleOpenTuning,
    handleSend,
    handleSuggestionClick,
    responseBadgeText,
    responseBadgeTone,
    responseBadgeTitle,
    scrollChatToBottom,
    updateFeedbackState,
  } = useCockpitChatUi({
    chatMessages,
    chatScrollRef,
    feedbackByRequest,
    setFeedbackByRequest,
    setFeedbackSubmittingId,
    sendFeedback,
    refreshHistory,
    refreshTasks,
    responseDurations,
    lastResponseDurationMs,
    labMode,
    chatMode,
    generationParams,
    selectedLlmModel,
    activeServerInfo,
    sessionId,
    language,
    resetSession,
    refreshActiveServer,
    setActiveLlmRuntime,
    sendSimpleChatStream,
    sendTask,
    ingestMemoryEntry,
    refreshQueue,
    refreshSessionHistory,
    enqueueOptimisticRequest,
    linkOptimisticRequest,
    dropOptimisticRequest,
    updateSimpleStream,
    recordUiTiming,
    uiTimingsRef,
    clearSimpleStream,
    setLocalSessionHistory,
    setSimpleRequestDetails,
    setMessage,
    setSending,
    setLastResponseDurationMs,
    setResponseDurations,
    models,
    fetchModelConfig,
    updateModelConfig,
    setTuningOpen,
    setLoadingSchema,
    setModelSchema,
    setGenerationParams,
    setTuningSaving,
    pushToast,
    pinnedLogs,
    setExportingPinned,
  });
  const logEntries = entries.slice(0, 8);
  const {
    tokenSplits,
    totalTokens,
    tokenTrendDelta,
    tokenTrendLabel,
  } = useTokenMetricsSummary({ tokenMetrics, tokenHistory });
  const tasksCreated = metrics?.tasks?.created ?? 0;
  const successRateValue = metrics?.tasks?.success_rate;
  const successRate = typeof successRateValue === "number" ? successRateValue : null;
  const telemetryFeed = useTelemetryFeedEntries(entries);
  const graphNodes = graph?.summary?.nodes ?? graph?.nodes ?? "—";
  const graphEdges = graph?.summary?.edges ?? graph?.edges ?? "—";
  const historySummary = useHistorySummary(history);
  const historyStatusEntries = historySummary.map((entry) => ({ label: entry.name, value: entry.value }));

  const {
    queueAction,
    queueActionMessage,
    handleToggleQueue,
    executeQueueMutation,
  } = useQueueActions({
    queue,
    refreshQueue,
    refreshTasks,
    toggleQueue,
    purgeQueue,
    emergencyStop,
  });

  const { handleCopyDetailSteps, openRequestDetail } = useCockpitRequestDetailActions({
    findTaskMatch,
    simpleRequestDetails,
    fetchHistoryDetail,
    fetchTaskDetail,
    setSelectedRequestId,
    setDetailOpen,
    setHistoryDetail,
    setHistoryError,
    setCopyStepsMessage,
    setSelectedTask,
    setLoadingHistory,
    historyDetail,
  });
  const uiTimingEntry = selectedRequestId ? uiTimingsByRequest[selectedRequestId] : undefined;
  const llmStartStep = useMemo(
    () =>
      historyDetail?.steps?.find(
        (step) => step.component === "LLM" && step.action === "start",
      ),
    [historyDetail?.steps],
  );
  const llmStartAt = llmStartStep?.timestamp ?? null;
  const contextPreviewMeta = useMemo(
    () => extractContextPreviewMeta(historyDetail?.steps),
    [historyDetail?.steps],
  );
  const payloadContext = selectedTask?.context_history ?? null;
  const {
    payloadGenerationParams,
    payloadSessionMeta,
    payloadForcedRoute,
    payloadContextUsed,
  } = extractPayloadContextDetails(payloadContext);

  const { primarySectionProps, runtimeSectionProps } = useCockpitSectionProps({
    chatFullscreen,
    setChatFullscreen: (value) => setChatFullscreen(value),
    showArtifacts,
    showReferenceSections,
    showSharedSections,
    labMode,
    responseBadgeTone,
    responseBadgeTitle,
    responseBadgeText,
    chatMessages,
    selectedRequestId,
    historyLoading,
    feedbackByRequest,
    feedbackSubmittingId,
    onOpenRequestDetail: openRequestDetail,
    onFeedbackClick: handleFeedbackClick,
    onFeedbackSubmit: handleFeedbackSubmit,
    onUpdateFeedbackState: updateFeedbackState,
    chatScrollRef,
    onChatScroll: handleChatScroll,
    composerRef,
    onSend: handleSend,
    sending,
    chatMode,
    setChatMode,
    setLabMode,
    selectedLlmServer,
    llmServerOptions,
    setSelectedLlmServer,
    selectedLlmModel,
    llmModelOptions,
    setSelectedLlmModel,
    onActivateModel: handleChatModelSelect,
    hasModels: availableModelsForServer.length > 0,
    onOpenTuning: handleOpenTuning,
    tuningLabel: t("common.tuning"),
    quickActionsOpen,
    setQuickActionsOpen,
    message,
    promptPresets,
    onSuggestionClick: handleSuggestionClick,
    llmServersLoading,
    llmServers,
    llmServerOptionsPanel: llmServerOptions,
    llmModelOptionsPanel: llmModelOptions,
    availableModelsForServer,
    selectedServerEntry,
    resolveServerStatus,
    sessionId,
    memoryAction,
    onSessionReset: handleSessionReset,
    onServerSessionReset: handleServerSessionReset,
    onClearSessionMemory: handleClearSessionMemory,
    onClearGlobalMemory: handleClearGlobalMemory,
    activeServerInfo,
    activeServerName,
    llmActionPending,
    onActivateServer: handleLlmServerActivate,
    connected,
    logFilter,
    onLogFilterChange: setLogFilter,
    logEntries,
    pinnedLogs,
    onTogglePin: (entry) =>
      setPinnedLogs((prev) =>
        prev.some((log) => log.id === entry.id)
          ? prev.filter((log) => log.id !== entry.id)
          : [...prev, entry],
      ),
    exportingPinned,
    onExportPinnedLogs: handleExportPinnedLogs,
    onClearPinnedLogs: () => setPinnedLogs([]),
    tasksPreview,
    hiddenScoreFilter,
    hiddenIntentFilter,
    onHiddenIntentFilterChange: setHiddenIntentFilter,
    onHiddenScoreFilterChange: setHiddenScoreFilter,
    hiddenIntentOptions,
    selectableHiddenPrompts,
    activeHiddenKeys,
    activeHiddenMap,
    activeForIntent,
    hiddenPrompts,
    hiddenLoading,
    hiddenError,
    activeHiddenLoading,
    activeHiddenError,
    onSetActiveHiddenPrompt: setActiveHiddenPrompt,
    history,
    loadingHistory,
    historyError,
    metrics,
    metricsLoading,
    successRate,
    tasksCreated,
    queue,
    feedbackScore,
    feedbackUp,
    feedbackDown,
    tokenMetricsLoading,
    tokenSplits,
    tokenHistory,
    tokenTrendDelta,
    tokenTrendLabel,
    totalTokens,
    telemetryFeed,
    usageMetrics,
    cpuUsageValue,
    gpuUsageValue,
    ramValue,
    vramValue,
    diskValue,
    diskPercent,
    sessionCostValue,
    graphNodes,
    graphEdges,
    agentDeck,
    queueLoading,
    queueAction,
    queueActionMessage,
    onToggleQueue: handleToggleQueue,
    onExecuteQueueMutation: executeQueueMutation,
    historyStatusEntries,
    learningLogs,
    learningLoading,
    learningError,
    feedbackLogs,
    feedbackLoading,
    feedbackError,
    services,
    entries,
    newMacro,
    setNewMacro,
    customMacros,
    setCustomMacros,
    allMacros,
    macroSending,
    onRunMacro: handleMacroRun,
    detailOpen,
    setDetailOpen,
    onCloseDetail: () => {
      setHistoryError(null);
      setSelectedRequestId(null);
      setSelectedTask(null);
    },
    historyDetail,
    selectedTask,
    uiTimingEntry,
    llmStartAt,
    payloadSessionMeta,
    payloadForcedRoute,
    payloadGenerationParams,
    payloadContextUsed,
    contextPreviewMeta,
    copyStepsMessage,
    onCopyDetailSteps: handleCopyDetailSteps,
    t,
    tuningOpen,
    setTuningOpen,
    loadingSchema,
    modelSchema,
    generationParams,
    onChangeGenerationParams: (values) =>
      setGenerationParams(values as Record<string, unknown>),
    onResetGenerationParams: () => setGenerationParams(null),
    tuningSaving,
    onApplyTuning: handleApplyTuning,
  });

  if (!isClientReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#020617] p-6 text-sm text-zinc-400">
        Ładowanie kokpitu…
      </div>
    );
  }

  return (
    <div className="space-y-10 pb-14">
      <CockpitHeader
        showReferenceSections={showReferenceSections}
        showArtifacts={showArtifacts}
        onToggleArtifacts={() => setShowArtifacts((prev) => !prev)}
      />
      <CockpitPrimarySection {...primarySectionProps} />
      <CockpitRuntimeSection {...runtimeSectionProps} />
    </div>
  );
}

export default CockpitHome;

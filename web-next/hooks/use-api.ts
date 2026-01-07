import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
import { getApiBaseUrl } from "@/lib/env";
import {
  AutonomyLevel,
  CampaignResponse,
  CostMode,
  FlowTrace,
  GenerationParams,
  GitStatus,
  GraphFileInfoResponse,
  GraphImpactResponse,
  GraphScanResponse,
  GraphSummary,
  HistoryRequest,
  HistoryRequestDetail,
  LlmActionResponse,
  LlmServerInfo,
  KnowledgeGraph,
  LearningLogsResponse,
  LessonsResponse,
  LessonsStats,
  Metrics,
  ModelCatalogResponse,
  ModelOperationsResponse,
  ModelsResponse,
  ModelsUsage,
  ModelsUsageResponse,
  QueueStatus,
  RoadmapResponse,
  RoadmapStatusResponse,
  ServiceStatus,
  Task,
  TokenMetrics,
  FeedbackResponse,
  FeedbackLogsResponse,
  ActiveHiddenPromptsResponse,
  HiddenPromptsResponse,
  ActiveLlmServerResponse,
} from "@/lib/types";

export const KNOWLEDGE_GRAPH_LIMIT = Number(process.env.NEXT_PUBLIC_KNOWLEDGE_GRAPH_LIMIT ?? "500");
export const MEMORY_GRAPH_LIMIT = Number(process.env.NEXT_PUBLIC_MEMORY_GRAPH_LIMIT ?? "100");

type PollingState<T> = {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const defaultHandleError = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  return "Nie udało się pobrać danych";
};

type PollingSnapshot<T> = {
  data: T | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
};

type PollingEntry<T> = {
  state: PollingSnapshot<T>;
  fetcher: () => Promise<T>;
  interval: number;
  listeners: Set<() => void>;
  timer?: ReturnType<typeof setInterval>;
  fetching: boolean;
  suspendedUntil?: number;
};

const pollingRegistry = new Map<string, PollingEntry<unknown>>();
const SERVICE_UNAVAILABLE_CODES = new Set([502, 503, 504]);
const OFFLINE_BACKOFF_MS = 15000;
type GenerationSchemaEntry = {
  type: string;
  default: unknown;
  min?: number;
  max?: number;
  desc?: string;
  options?: unknown[];
};
type GenerationSchema = Record<string, GenerationSchemaEntry>;

function ensureEntry<T>(key: string, fetcher: () => Promise<T>, interval: number) {
  const existing = pollingRegistry.get(key) as PollingEntry<T> | undefined;
  if (existing) {
    existing.fetcher = fetcher;
    if (interval > 0 && interval < existing.interval) {
      existing.interval = interval;
      if (existing.timer) {
        clearInterval(existing.timer);
        existing.timer = undefined;
      }
    }
    return existing;
  }
  const entry: PollingEntry<T> = {
    state: { data: null, loading: true, refreshing: false, error: null },
    fetcher,
    interval,
    listeners: new Set(),
    fetching: false,
  };
  pollingRegistry.set(key, entry as PollingEntry<unknown>);
  triggerFetch(entry);
  return entry;
}

async function triggerFetch<T>(entry: PollingEntry<T>) {
  if (entry.fetching) return;
  const now = Date.now();
  if (entry.suspendedUntil && entry.suspendedUntil > now) {
    entry.state = {
      ...entry.state,
      loading: false,
      refreshing: false,
    };
    notifyEntry(entry);
    return;
  }
  entry.fetching = true;
  if (entry.state.data === null) {
    entry.state = { ...entry.state, loading: true, refreshing: false };
  } else {
    entry.state = { ...entry.state, refreshing: true };
  }
  notifyEntry(entry);
  try {
    const result = await entry.fetcher();
    entry.state = {
      data: result,
      loading: false,
      refreshing: false,
      error: null,
    };
    entry.suspendedUntil = undefined;
  } catch (err) {
    let message = defaultHandleError(err);
    if (err instanceof ApiError && SERVICE_UNAVAILABLE_CODES.has(err.status)) {
      entry.suspendedUntil = Date.now() + OFFLINE_BACKOFF_MS;
      message = "API tymczasowo niedostępne (503) – ponowię próbę za 15s.";
    } else {
      entry.suspendedUntil = undefined;
    }
    entry.state = {
      ...entry.state,
      loading: false,
      refreshing: false,
      error: message,
    };
  } finally {
    entry.fetching = false;
    notifyEntry(entry);
  }
}

function notifyEntry(entry: PollingEntry<unknown>) {
  entry.listeners.forEach((listener) => listener());
}

function usePolling<T>(
  key: string,
  fetcher: () => Promise<T>,
  intervalMs = 5000,
): PollingState<T> {
  const isBrowser = typeof window !== "undefined";
  const pollingDisabled = process.env.NEXT_PUBLIC_DISABLE_API_POLLING === "true";
  const disabledState = useMemo(
    () => ({
      data: null,
      loading: false,
      refreshing: false,
      error: null,
      refresh: async () => { },
    }),
    [],
  );
  const fallbackEntry = useMemo<PollingEntry<T>>(
    () => ({
      state: { data: null, loading: true, refreshing: false, error: null },
      fetcher: async () => {
        throw new Error("Polling entry not initialized.");
      },
      interval: 0,
      listeners: new Set(),
      fetching: false,
    }),
    [],
  );
  const entryRef = useRef<PollingEntry<T>>(fallbackEntry);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isBrowser || pollingDisabled) return;
    const actualEntry = ensureEntry(key, fetcher, intervalMs);
    entryRef.current = actualEntry;
    setReady(true);
  }, [isBrowser, pollingDisabled, key, intervalMs]);

  useEffect(() => {
    if (pollingDisabled) return;
    const entry = entryRef.current;
    if (entry) {
      entry.fetcher = fetcher;
    }
  }, [fetcher, pollingDisabled]);

  const entry = pollingDisabled
    ? fallbackEntry
    : ready
      ? entryRef.current
      : fallbackEntry;

  const subscribe = useCallback(
    (listener: () => void) => {
      if (pollingDisabled) return () => { };
      entry.listeners.add(listener);
      if (entry.listeners.size === 1) {
        if (entry.interval > 0 && !entry.timer) {
          entry.timer = setInterval(() => triggerFetch(entry), entry.interval);
        }
        triggerFetch(entry);
      }
      return () => {
        entry.listeners.delete(listener);
        if (entry.listeners.size === 0 && entry.timer) {
          clearInterval(entry.timer);
          entry.timer = undefined;
        }
      };
    },
    [entry, pollingDisabled],
  );

  const snapshot = useSyncExternalStore(
    subscribe,
    () => (pollingDisabled ? disabledState : entry.state),
    () => (pollingDisabled ? disabledState : entry.state),
  );

  const refresh = useCallback(async () => {
    if (pollingDisabled || entry === fallbackEntry) return;
    entry.suspendedUntil = undefined;
    await triggerFetch(entry);
  }, [entry, fallbackEntry, pollingDisabled]);

  return useMemo(
    () =>
      pollingDisabled
        ? disabledState
        : {
          data: snapshot.data,
          loading: snapshot.loading,
          refreshing: snapshot.refreshing,
          error: snapshot.error,
          refresh,
        },
    [
      pollingDisabled,
      disabledState,
      snapshot.data,
      snapshot.loading,
      snapshot.refreshing,
      snapshot.error,
      refresh,
    ],
  );
}

export function useMetrics(intervalMs = 5000) {
  return usePolling<Metrics>("metrics", () => apiFetch("/api/v1/metrics"), intervalMs);
}

export function useTasks(intervalMs = 5000) {
  return usePolling<Task[]>(
    "tasks",
    () => apiFetch("/api/v1/tasks"),
    intervalMs,
  );
}

export function useHistory(limit = 50, intervalMs = 10000) {
  return usePolling<HistoryRequest[]>(
    `history-${limit}`,
    () => apiFetch(`/api/v1/history/requests?limit=${limit}`),
    intervalMs,
  );
}

export async function fetchHistoryDetail(requestId: string) {
  return apiFetch<HistoryRequestDetail>(`/api/v1/history/requests/${requestId}`);
}

export async function fetchFlowTrace(requestId: string) {
  return apiFetch<FlowTrace>(`/api/v1/flow/${requestId}`);
}

export async function fetchTaskDetail(taskId: string) {
  return apiFetch<Task>(`/api/v1/tasks/${taskId}`);
}

export function useQueueStatus(intervalMs = 5000) {
  return usePolling<QueueStatus>(
    "queue",
    () =>
      apiFetch("/api/v1/queue/status"),
    intervalMs,
  );
}

export function useServiceStatus(intervalMs = 15000) {
  return usePolling<ServiceStatus[]>(
    "services",
    async () => {
      const data = await apiFetch<{ services?: ServiceStatus[]; status?: string }>(
        "/api/v1/system/services",
      );
      if (Array.isArray(data?.services)) {
        return data.services;
      }
      if (Array.isArray((data as unknown) as ServiceStatus[])) {
        return (data as unknown) as ServiceStatus[];
      }
      return [];
    },
    intervalMs,
  );
}

export function useGraphSummary(intervalMs = 15000) {
  return usePolling<GraphSummary>(
    "graph-summary",
    () => apiFetch("/api/v1/graph/summary"),
    intervalMs,
  );
}

export function useModels(intervalMs = 15000) {
  return usePolling<ModelsResponse>(
    "models",
    () => apiFetch("/api/v1/models"),
    intervalMs,
  );
}

export function useModelTrending(provider: string, intervalMs = 60000) {
  return usePolling<ModelCatalogResponse>(
    `models-trending-${provider}`,
    () => apiFetch(`/api/v1/models/trending?provider=${encodeURIComponent(provider)}`),
    intervalMs,
  );
}

export function useModelCatalog(provider: string, intervalMs = 60000) {
  return usePolling<ModelCatalogResponse>(
    `models-catalog-${provider}`,
    () => apiFetch(`/api/v1/models/providers?provider=${encodeURIComponent(provider)}`),
    intervalMs,
  );
}

export function useModelOperations(limit = 10, intervalMs = 5000) {
  return usePolling<ModelOperationsResponse>(
    `models-operations-${limit}`,
    () => apiFetch(`/api/v1/models/operations?limit=${limit}`),
    intervalMs,
  );
}

export function useGitStatus(intervalMs = 0) {
  return usePolling<GitStatus>(
    "git-status",
    () => apiFetch("/api/v1/git/status"),
    intervalMs,
  );
}

export function useTokenMetrics(intervalMs = 5000) {
  return usePolling<TokenMetrics>(
    "token-metrics",
    () => apiFetch("/api/v1/metrics/tokens"),
    intervalMs,
  );
}

type ModelsUsagePayload = ModelsUsageResponse | ModelsUsage;

export function useModelsUsage(intervalMs = 10000) {
  return usePolling<ModelsUsageResponse>(
    "models-usage",
    async () => {
      const result = await apiFetch<ModelsUsagePayload>("/api/v1/models/usage");
      if ("usage" in result) {
        return result;
      }
      return { usage: result as ModelsUsage };
    },
    intervalMs,
  );
}

export function useLlmServers(intervalMs = 0) {
  return usePolling<LlmServerInfo[]>(
    "llm-servers",
    async () => {
      const data = await apiFetch<{ servers?: LlmServerInfo[] } | LlmServerInfo[]>(
        "/api/v1/system/llm-servers",
      );
      if (Array.isArray(data)) {
        return data;
      }
      if (Array.isArray(data?.servers)) {
        return data.servers;
      }
      return [];
    },
    intervalMs,
  );
}

export function useActiveLlmServer(intervalMs = 0) {
  return usePolling<ActiveLlmServerResponse>(
    "llm-servers-active",
    () => apiFetch("/api/v1/system/llm-servers/active"),
    intervalMs,
  );
}

export async function setActiveLlmServer(serverName: string) {
  return apiFetch<ActiveLlmServerResponse>("/api/v1/system/llm-servers/active", {
    method: "POST",
    body: JSON.stringify({ server_name: serverName }),
  });
}

export async function setActiveLlmRuntime(provider: "openai" | "google", model?: string) {
  return apiFetch<ActiveLlmServerResponse>("/api/v1/system/llm-runtime/active", {
    method: "POST",
    body: JSON.stringify({ provider, model }),
  });
}

export async function controlLlmServer(
  serverName: string,
  action: "start" | "stop" | "restart",
) {
  return apiFetch<LlmActionResponse>(
    `/api/v1/system/llm-servers/${serverName}/${action}`,
    { method: "POST" },
  );
}

export async function unloadAllModels() {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/v1/models/unload-all",
    { method: "POST" },
  );
}

export function useCostMode(intervalMs = 15000) {
  return usePolling<CostMode>(
    "cost-mode",
    () => apiFetch("/api/v1/system/cost-mode"),
    intervalMs,
  );
}

export function useAutonomyLevel(intervalMs = 15000) {
  return usePolling<AutonomyLevel>(
    "autonomy-level",
    () => apiFetch("/api/v1/system/autonomy"),
    intervalMs,
  );
}

export function useKnowledgeGraph(limit = KNOWLEDGE_GRAPH_LIMIT, intervalMs = 20000) {
  return usePolling<KnowledgeGraph>(
    `knowledge-graph-${limit}`,
    () => apiFetch(`/api/v1/knowledge/graph?limit=${limit}`),
    intervalMs,
  );
}

export function useLessons(limit = 5, intervalMs = 20000) {
  return usePolling<LessonsResponse>(
    "lessons",
    () => apiFetch(`/api/v1/lessons?limit=${limit}`),
    intervalMs,
  );
}

export function useLearningLogs(limit = 20, intervalMs = 20000) {
  return usePolling<LearningLogsResponse>(
    `learning-logs-${limit}`,
    () => apiFetch(`/api/v1/learning/logs?limit=${limit}`),
    intervalMs,
  );
}

export function useRoadmap(intervalMs = 30000) {
  return usePolling<RoadmapResponse>("roadmap", () => apiFetch("/api/roadmap"), intervalMs);
}

export function useLessonsStats(intervalMs = 30000) {
  return usePolling<LessonsStats>(
    "lessons-stats",
    () => apiFetch("/api/v1/lessons/stats"),
    intervalMs,
  );
}

export function useMemoryGraph(
  limit = MEMORY_GRAPH_LIMIT,
  sessionId?: string,
  onlyPinned = false,
  includeLessons = false,
  intervalMs = 20000,
  mode: "default" | "flow" = "default",
) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (sessionId) params.set("session_id", sessionId);
  if (onlyPinned) params.set("only_pinned", "true");
  if (includeLessons) params.set("include_lessons", "true");
  if (mode && mode !== "default") params.set("mode", mode);
  return usePolling<KnowledgeGraph>(
    `memory-graph-${limit}-${sessionId || "all"}-${onlyPinned}-${includeLessons}-${mode}`,
    () => apiFetch(`/api/v1/memory/graph?${params.toString()}`),
    intervalMs,
  );
}

type SessionHistoryEntry = {
  role?: string;
  content?: string;
  session_id?: string;
  request_id?: string;
  timestamp?: string;
};

type SessionHistoryResponse = {
  status?: string;
  session_id?: string;
  history?: SessionHistoryEntry[];
  summary?: string | null;
  count?: number;
};

export function useSessionHistory(sessionId?: string | null, intervalMs = 10000) {
  return usePolling<SessionHistoryResponse>(
    `session-history-${sessionId || "none"}`,
    () => {
      if (!sessionId) {
        return Promise.resolve({ status: "success", history: [] });
      }
      return apiFetch(`/api/v1/memory/session/${encodeURIComponent(sessionId)}`);
    },
    intervalMs,
  );
}

export async function pinMemoryEntry(entryId: string, pinned = true) {
  return apiFetch<{ status: string; entry_id: string; pinned: boolean }>(
    `/api/v1/memory/entry/${encodeURIComponent(entryId)}/pin?pinned=${pinned ? "true" : "false"}`,
    { method: "POST" },
  );
}

export async function deleteMemoryEntry(entryId: string) {
  return apiFetch<{ status: string; entry_id: string; deleted: number }>(
    `/api/v1/memory/entry/${encodeURIComponent(entryId)}`,
    { method: "DELETE" },
  );
}

export async function clearSessionMemory(sessionId: string) {
  return apiFetch<{ status: string; session_id: string; deleted_vectors: number; cleared_tasks: number }>(
    `/api/v1/memory/session/${encodeURIComponent(sessionId)}`,
    { method: "DELETE" },
  );
}

export async function clearGlobalMemory() {
  return apiFetch<{ status: string; deleted_vectors: number; message: string }>(
    "/api/v1/memory/global",
    { method: "DELETE" },
  );
}

export async function ingestMemoryEntry(payload: {
  text: string;
  category?: string;
  collection?: string;
  sessionId?: string | null;
  userId?: string | null;
  pinned?: boolean;
  memoryType?: string | null;
  scope?: string | null;
  topic?: string | null;
  timestamp?: string | null;
}) {
  const body = {
    text: payload.text,
    category: payload.category ?? "general",
    collection: payload.collection ?? "default",
    session_id: payload.sessionId ?? undefined,
    user_id: payload.userId ?? undefined,
    pinned: payload.pinned ?? undefined,
    memory_type: payload.memoryType ?? undefined,
    scope: payload.scope ?? undefined,
    topic: payload.topic ?? undefined,
    timestamp: payload.timestamp ?? undefined,
  };
  return apiFetch<{ status: string; message: string; chunks_count: number }>(
    "/api/v1/memory/ingest",
    { method: "POST", body: JSON.stringify(body) },
  );
}

export type TaskExtraContext = {
  files?: string[];
  links?: string[];
  paths?: string[];
  notes?: string[];
};

export type ForcedRoute = {
  tool?: string;
  provider?: string;
};

export type SimpleChatStreamRequest = {
  content: string;
  model?: string | null;
  maxTokens?: number | null;
  temperature?: number | null;
  sessionId?: string | null;
};

export async function sendSimpleChatStream(payload: SimpleChatStreamRequest) {
  const baseUrl = getApiBaseUrl();
  const target = baseUrl ? `${baseUrl}/api/v1/llm/simple/stream` : "/api/v1/llm/simple/stream";
  const body: {
    content: string;
    model?: string;
    max_tokens?: number;
    temperature?: number;
    session_id?: string;
  } = {
    content: payload.content,
  };
  if (payload.model) body.model = payload.model;
  if (typeof payload.maxTokens === "number") body.max_tokens = payload.maxTokens;
  if (typeof payload.temperature === "number") body.temperature = payload.temperature;
  if (payload.sessionId) body.session_id = payload.sessionId;
  let response: Response;
  try {
    response = await fetch(target, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (error) {
    if (baseUrl) {
      response = await fetch("/api/v1/llm/simple/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } else {
      throw error;
    }
  }
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(
      `Request failed: ${response.status}`,
      response.status,
      text,
    );
  }
  return response;
}

export async function sendTask(
  content: string,
  storeKnowledge = true,
  generationParams?: GenerationParams | null,
  runtimeMeta?: { configHash?: string | null; runtimeId?: string | null } | null,
  extraContext?: TaskExtraContext | null,
  forcedRoute?: ForcedRoute | null,
  forcedIntent?: string | null,
  preferredLanguage?: "pl" | "en" | "de" | null,
  sessionId?: string | null,
  preferenceScope?: "session" | "global" | null,
) {
  const body: {
    content: string;
    store_knowledge: boolean;
    generation_params?: GenerationParams;
    expected_config_hash?: string;
    expected_runtime_id?: string;
    extra_context?: TaskExtraContext;
    forced_tool?: string;
    forced_provider?: string;
    forced_intent?: string;
    preferred_language?: string;
    session_id?: string;
    preference_scope?: string;
  } = {
    content,
    store_knowledge: storeKnowledge,
  };

  if (generationParams) {
    body.generation_params = generationParams;
  }
  if (runtimeMeta?.configHash) {
    body.expected_config_hash = runtimeMeta.configHash;
  }
  if (runtimeMeta?.runtimeId) {
    body.expected_runtime_id = runtimeMeta.runtimeId;
  }
  if (extraContext) {
    body.extra_context = extraContext;
  }
  if (forcedRoute?.tool) {
    body.forced_tool = forcedRoute.tool;
  }
  if (forcedRoute?.provider) {
    body.forced_provider = forcedRoute.provider;
  }
  if (forcedIntent) {
    body.forced_intent = forcedIntent;
  }
  if (preferredLanguage) {
    body.preferred_language = preferredLanguage;
  }
  if (sessionId) {
    body.session_id = sessionId;
  }
  if (preferenceScope) {
    body.preference_scope = preferenceScope;
  }

  return apiFetch<{ task_id: string }>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function sendFeedback(
  taskId: string,
  rating: "up" | "down",
  comment?: string,
) {
  return apiFetch<FeedbackResponse>("/api/v1/feedback", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      rating,
      comment,
    }),
  });
}

export function useFeedbackLogs(limit = 10, intervalMs = 20000, rating?: "up" | "down") {
  const suffix = rating ? `&rating=${rating}` : "";
  return usePolling<FeedbackLogsResponse>(
    `feedback-logs-${limit}-${rating ?? "all"}`,
    () => apiFetch(`/api/v1/feedback/logs?limit=${limit}${suffix}`),
    intervalMs,
  );
}

export function useHiddenPrompts(
  limit = 10,
  intervalMs = 20000,
  intent?: string,
  minScore = 1,
) {
  const intentParam = intent ? `&intent=${encodeURIComponent(intent)}` : "";
  return usePolling<HiddenPromptsResponse>(
    `hidden-prompts-${limit}-${intent ?? "all"}-${minScore}`,
    () =>
      apiFetch(
        `/api/v1/learning/hidden-prompts?limit=${limit}${intentParam}&min_score=${minScore}`,
      ),
    intervalMs,
  );
}

export function useActiveHiddenPrompts(intent?: string, intervalMs = 20000) {
  const intentParam = intent ? `?intent=${encodeURIComponent(intent)}` : "";
  return usePolling<ActiveHiddenPromptsResponse>(
    `hidden-prompts-active-${intent ?? "all"}`,
    () => apiFetch(`/api/v1/learning/hidden-prompts/active${intentParam}`),
    intervalMs,
  );
}

export async function setActiveHiddenPrompt(payload: {
  intent?: string;
  prompt?: string;
  approved_response?: string;
  prompt_hash?: string;
  active?: boolean;
  actor?: string;
}) {
  return apiFetch<ActiveHiddenPromptsResponse>(
    "/api/v1/learning/hidden-prompts/active",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function toggleQueue(paused: boolean) {
  const endpoint = paused ? "/api/v1/queue/resume" : "/api/v1/queue/pause";
  return apiFetch<{ message: string }>(endpoint, { method: "POST" });
}

export async function purgeQueue() {
  return apiFetch<{ removed: number }>("/api/v1/queue/purge", {
    method: "POST",
  });
}

export async function emergencyStop() {
  return apiFetch<{ cancelled: number; purged: number }>(
    "/api/v1/queue/emergency-stop",
    { method: "POST" },
  );
}

export async function installModel(name: string) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/v1/models/install",
    {
      method: "POST",
      body: JSON.stringify({ name }),
    },
  );
}

export async function installRegistryModel(payload: {
  name: string;
  provider: string;
  runtime: string;
}) {
  return apiFetch<{ success: boolean; message: string; operation_id: string }>(
    "/api/v1/models/registry/install",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function removeRegistryModel(modelName: string) {
  return apiFetch<{ success: boolean; message: string; operation_id: string }>(
    `/api/v1/models/registry/${encodeURIComponent(modelName)}`,
    { method: "DELETE" },
  );
}

export async function activateRegistryModel(payload: { name: string; runtime: string }) {
  return apiFetch<{ success: boolean; message: string }>(
    "/api/v1/models/activate",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function switchModel(name: string) {
  return apiFetch<{ success: boolean; message: string; active_model: string }>(
    "/api/v1/models/switch",
    {
      method: "POST",
      body: JSON.stringify({ name }),
    },
  );
}

export async function gitSync() {
  return apiFetch("/api/v1/git/sync", { method: "POST" });
}

export async function gitUndo() {
  return apiFetch("/api/v1/git/undo", { method: "POST" });
}

export async function setCostMode(enable: boolean) {
  return apiFetch("/api/v1/system/cost-mode", {
    method: "POST",
    body: JSON.stringify({ enable }),
  });
}

export async function setAutonomy(level: number) {
  return apiFetch("/api/v1/system/autonomy", {
    method: "POST",
    body: JSON.stringify({ level }),
  });
}

export async function triggerGraphScan() {
  return apiFetch<GraphScanResponse>("/api/v1/graph/scan", { method: "POST" });
}

export async function createRoadmap(vision: string) {
  return apiFetch("/api/roadmap/create", {
    method: "POST",
    body: JSON.stringify({ vision }),
  });
}

export async function requestRoadmapStatus() {
  return apiFetch<RoadmapStatusResponse>("/api/roadmap/status");
}

export async function startCampaign() {
  return apiFetch<CampaignResponse>("/api/campaign/start", { method: "POST" });
}

export async function fetchGraphFileInfo(filePath: string) {
  return apiFetch<GraphFileInfoResponse>(
    `/api/v1/graph/file/${encodeURIComponent(filePath)}`,
  );
}

export async function fetchGraphImpact(filePath: string) {
  return apiFetch<GraphImpactResponse>(
    `/api/v1/graph/impact/${encodeURIComponent(filePath)}`,
  );
}

/**
 * Pobiera schemat parametrów generacji dla modelu
 */
export async function fetchModelConfig(modelName: string) {
  return apiFetch<{
    success: boolean;
    model_name: string;
    generation_schema: GenerationSchema;
    current_values?: Record<string, number | string | boolean | null | undefined>;
    runtime?: string;
  }>(`/api/v1/models/${encodeURIComponent(modelName)}/config`);
}

export async function updateModelConfig(
  modelName: string,
  payload: {
    runtime?: string;
    params: Record<string, number | string | boolean | null | undefined>;
  },
) {
  return apiFetch<{
    success: boolean;
    model_name: string;
    runtime?: string;
    params?: Record<string, number | string | boolean | null | undefined>;
  }>(`/api/v1/models/${encodeURIComponent(modelName)}/config`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
export function useLessonPruning() {
  const pruneByTTL = useCallback(async (days: number) => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        `/api/v1/lessons/prune/ttl?days=${days}`,
        { method: "DELETE" }
      );
    } catch (error) {
      throw new Error(`Failed to prune lessons by TTL: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const pruneByTag = useCallback(async (tag: string) => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        `/api/v1/lessons/prune/tag?tag=${encodeURIComponent(tag)}`,
        { method: "DELETE" }
      );
    } catch (error) {
      throw new Error(`Failed to prune lessons by tag: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const pruneByDate = useCallback(async (fromDate: string, toDate: string) => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        `/api/v1/lessons/prune/range?from_date=${fromDate}&to_date=${toDate}`,
        { method: "DELETE" }
      );
    } catch (error) {
      throw new Error(`Failed to prune lessons by date range: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const pruneLatest = useCallback(async (count: number) => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        `/api/v1/lessons/prune/latest?count=${count}`,
        { method: "DELETE" }
      );
    } catch (error) {
      throw new Error(`Failed to prune latest lessons: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const dedupeLessons = useCallback(async () => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        "/api/v1/lessons/dedupe",
        { method: "POST" }
      );
    } catch (error) {
      throw new Error(`Failed to deduplicate lessons: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const purgeLessons = useCallback(async () => {
    try {
      return await apiFetch<{ deleted: number; remaining: number }>(
        "/api/v1/lessons/purge",
        { method: "DELETE" }
      );
    } catch (error) {
      throw new Error(`Failed to purge all lessons: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  return {
    pruneByTTL,
    pruneByTag,
    pruneByDate,
    pruneLatest,
    dedupeLessons,
    purgeLessons,
  };
}

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, apiFetch } from "@/lib/api-client";
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
  LessonsResponse,
  LessonsStats,
  Metrics,
  ModelsResponse,
  ModelsUsage,
  ModelsUsageResponse,
  QueueStatus,
  RoadmapResponse,
  RoadmapStatusResponse,
  ServiceStatus,
  Task,
  TokenMetrics,
} from "@/lib/types";

type PollingState<T> = {
  data: T | null;
  loading: boolean;
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
    state: { data: null, loading: true, error: null },
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
    };
    notifyEntry(entry);
    return;
  }
  entry.fetching = true;
  entry.state = { ...entry.state, loading: true };
  notifyEntry(entry);
  try {
    const result = await entry.fetcher();
    entry.state = {
      data: result,
      loading: false,
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
  const fallbackEntry = useMemo<PollingEntry<T>>(
    () => ({
      state: { data: null, loading: true, error: null },
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
    if (!isBrowser) return;
    const actualEntry = ensureEntry(key, fetcher, intervalMs);
    entryRef.current = actualEntry;
    setReady(true);
  }, [isBrowser, key, fetcher, intervalMs]);

  const entry = ready ? entryRef.current : fallbackEntry;

  const subscribe = useCallback(
    (listener: () => void) => {
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
    [entry],
  );

  const snapshot = useSyncExternalStore(
    subscribe,
    () => entry.state,
    () => entry.state,
  );

  const refresh = useCallback(async () => {
    if (entry === fallbackEntry) return;
    entry.suspendedUntil = undefined;
    await triggerFetch(entry);
  }, [entry, fallbackEntry]);

  return useMemo(
    () => ({
      data: snapshot.data,
      loading: snapshot.loading,
      error: snapshot.error,
      refresh,
    }),
    [snapshot.data, snapshot.loading, snapshot.error, refresh],
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

export function useGitStatus(intervalMs = 10000) {
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

export function useKnowledgeGraph(intervalMs = 20000) {
  return usePolling<KnowledgeGraph>(
    "knowledge-graph",
    () => apiFetch("/api/v1/knowledge/graph"),
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

export async function sendTask(
  content: string,
  storeKnowledge = true,
  generationParams?: GenerationParams | null
) {
  const body: {
    content: string;
    store_knowledge: boolean;
    generation_params?: GenerationParams;
  } = {
    content,
    store_knowledge: storeKnowledge,
  };

  if (generationParams) {
    body.generation_params = generationParams;
  }

  return apiFetch<{ task_id: string }>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
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
  }>(`/api/v1/models/${encodeURIComponent(modelName)}/config`);
}

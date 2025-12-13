import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import {
  AutonomyLevel,
  CampaignResponse,
  CostMode,
  GraphFileInfoResponse,
  GraphImpactResponse,
  GraphScanResponse,
  GraphSummary,
  HistoryRequest,
  HistoryRequestDetail,
  GitStatus,
  KnowledgeGraph,
  Lesson,
  LessonsStats,
  LessonsResponse,
  Metrics,
  ModelsResponse,
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
  refresh: () => void;
};

const defaultHandleError = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  return "Nie udało się pobrać danych";
};

function usePolling<T>(
  key: string,
  fetcher: () => Promise<T>,
  intervalMs = 5000,
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runner = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (err) {
      setError(defaultHandleError(err));
    } finally {
      setLoading(false);
    }
  }, [fetcher]);

  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    runner();
    if (intervalMs > 0) {
      timer = setInterval(runner, intervalMs);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [key, intervalMs, runner]);

  return useMemo(
    () => ({
      data,
      loading,
      error,
      refresh: runner,
    }),
    [data, loading, error, runner],
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
    "history",
    () => apiFetch(`/api/v1/history/requests?limit=${limit}`),
    intervalMs,
  );
}

export async function fetchHistoryDetail(requestId: string) {
  return apiFetch<HistoryRequestDetail>(`/api/v1/history/requests/${requestId}`);
}

export function useQueueStatus(intervalMs = 5000) {
  return usePolling<QueueStatus>(
    "queue",
    () => apiFetch("/api/v1/queue/status"),
    intervalMs,
  );
}

export function useServiceStatus(intervalMs = 15000) {
  return usePolling<ServiceStatus[]>(
    "services",
    () => apiFetch("/api/v1/system/services"),
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

export async function sendTask(content: string, storeKnowledge = true) {
  return apiFetch<{ task_id: string }>("/api/v1/tasks", {
    method: "POST",
    body: JSON.stringify({
      content,
      store_knowledge: storeKnowledge,
    }),
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

export async function fetchMarkdownContent(path: string) {
  return apiFetch<string>(path, { skipBaseUrl: true });
}

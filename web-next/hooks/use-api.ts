import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "@/lib/api-client";
import {
  GraphSummary,
  HistoryRequest,
  Metrics,
  QueueStatus,
  ServiceStatus,
  Task,
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

export function useQueueStatus(intervalMs = 5000) {
  return usePolling<QueueStatus>(
    "queue",
    () => apiFetch("/api/v1/queue/status"),
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

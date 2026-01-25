"use client";

import { useEffect } from "react";
import type { HistoryRequestDetail, Task } from "@/lib/types";

export function useTokenHistoryBuffer(
  tokenTotal: number | undefined,
  setTokenHistory: React.Dispatch<React.SetStateAction<Array<{ timestamp: string; value: number }>>>,
) {
  useEffect(() => {
    if (tokenTotal === undefined) return;
    setTokenHistory((prev) => {
      const next = [
        ...prev,
        {
          timestamp: new Date().toLocaleTimeString(),
          value: tokenTotal ?? 0,
        },
      ];
      return next.slice(-20);
    });
  }, [setTokenHistory, tokenTotal]);
}

export function useDetailTaskSync({
  detailOpen,
  selectedRequestId,
  historyPrompt,
  findTaskMatch,
  selectedTask,
  setSelectedTask,
}: {
  detailOpen: boolean;
  selectedRequestId: string | null;
  historyPrompt?: string | null;
  findTaskMatch: (requestId?: string, prompt?: string | null) => Task | null;
  selectedTask: Task | null;
  setSelectedTask: React.Dispatch<React.SetStateAction<Task | null>>;
}) {
  useEffect(() => {
    if (!detailOpen || !selectedRequestId) return;
    const fallback = findTaskMatch(selectedRequestId, historyPrompt);
    if (!fallback) return;
    if (
      !selectedTask ||
      (fallback.logs?.length ?? 0) !== (selectedTask.logs?.length ?? 0) ||
      (fallback.result ?? "") !== (selectedTask.result ?? "")
    ) {
      setSelectedTask(fallback);
    }
  }, [detailOpen, selectedRequestId, historyPrompt, findTaskMatch, selectedTask, setSelectedTask]);
}

export function useTelemetryRefreshEffect({
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
  shouldRefresh,
}: {
  entries: Array<{ id: string; payload: unknown }>;
  lastTelemetryRefreshRef: React.MutableRefObject<string | null>;
  refreshQueue: () => void;
  refreshTasks: () => void;
  refreshHistory: () => void;
  refreshSessionHistory: () => void;
  refreshMetrics: () => void;
  refreshTokenMetrics: () => void;
  refreshModelsUsage: () => void;
  refreshServices: () => void;
  shouldRefresh: (payload: unknown) => boolean;
}) {
  useEffect(() => {
    if (!entries.length) return;
    const latest = entries[0];
    if (!latest || lastTelemetryRefreshRef.current === latest.id) return;
    lastTelemetryRefreshRef.current = latest.id;
    if (!shouldRefresh(latest.payload)) return;
    const debounce = setTimeout(() => {
      refreshQueue();
      refreshTasks();
      refreshHistory();
      refreshSessionHistory();
      refreshMetrics();
      refreshTokenMetrics();
      refreshModelsUsage();
      refreshServices();
    }, 250);
    return () => clearTimeout(debounce);
  }, [
    entries,
    lastTelemetryRefreshRef,
    refreshHistory,
    refreshMetrics,
    refreshModelsUsage,
    refreshQueue,
    refreshServices,
    refreshSessionHistory,
    refreshTasks,
    refreshTokenMetrics,
    shouldRefresh,
  ]);
}

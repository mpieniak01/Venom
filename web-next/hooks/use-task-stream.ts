"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { TaskStatus } from "@/lib/types";

export type TaskStreamEventName = "task_update" | "task_finished" | "task_missing" | "heartbeat";

export type TaskStreamEvent = {
  taskId: string;
  event: TaskStreamEventName;
  status?: TaskStatus | null;
  logs?: string[];
  result?: string | null;
  timestamp?: string | null;
};

export type TaskStreamState = {
  status: TaskStatus | null;
  logs: string[];
  result: string | null;
  lastEventAt: string | null;
  heartbeatAt: string | null;
  connected: boolean;
  error: string | null;
};

export type UseTaskStreamResult = {
  streams: Record<string, TaskStreamState>;
  connectedIds: string[];
  lastEvent?: TaskStreamEvent;
};

type UseTaskStreamOptions = {
  enabled?: boolean;
  autoCloseOnFinish?: boolean;
  onEvent?: (event: TaskStreamEvent) => void;
};

const defaultState: TaskStreamState = {
  status: null,
  logs: [],
  result: null,
  lastEventAt: null,
  heartbeatAt: null,
  connected: false,
  error: null,
};

const TERMINAL_STATUSES: TaskStatus[] = ["COMPLETED", "FAILED", "LOST"];

export function useTaskStream(taskIds: string[], options?: UseTaskStreamOptions): UseTaskStreamResult {
  const { enabled = true, autoCloseOnFinish = true, onEvent } = options ?? {};
  const [streams, setStreams] = useState<Record<string, TaskStreamState>>({});
  const [lastEvent, setLastEvent] = useState<TaskStreamEvent | undefined>(undefined);
  const sourcesRef = useRef<Map<string, EventSource>>(new Map());
  const dedupedTaskIds = useMemo(() => {
    const seen = new Set<string>();
    const filtered: string[] = [];
    for (const id of taskIds) {
      if (!id) continue;
      if (seen.has(id)) continue;
      seen.add(id);
      filtered.push(id);
    }
    return filtered;
  }, [taskIds]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    if (!enabled) {
      // Zamknij wszystkie istniejące źródła jeśli streaming wyłączony
      sourcesRef.current.forEach((source) => source.close());
      sourcesRef.current.clear();
      setStreams({});
      return undefined;
    }

    const targetIds = new Set(dedupedTaskIds);

    // Dodaj nowe strumienie
    for (const taskId of targetIds) {
      if (sourcesRef.current.has(taskId)) continue;
      const source = new EventSource(`/api/v1/tasks/${taskId}/stream`);

      const updateState = (patch: Partial<TaskStreamState>) => {
        setStreams((prev) => {
          const existing = prev[taskId] ?? defaultState;
          const mergedLogs =
            patch.logs === undefined
              ? existing.logs
              : mergeLogs(existing.logs, patch.logs);
          return {
            ...prev,
            [taskId]: {
              ...existing,
              ...patch,
              logs: mergedLogs,
            },
          };
        });
      };

      const emitEvent = (event: TaskStreamEvent) => {
        setLastEvent(event);
        onEvent?.(event);
      };

      const handlePayload = (eventName: TaskStreamEventName, payload: Record<string, unknown>) => {
        const status = normalizeStatus(payload.status);
        const logs = Array.isArray(payload.logs)
          ? payload.logs.map((entry) => String(entry))
          : undefined;
        const result =
          typeof payload.result === "string" || payload.result === null
            ? (payload.result as string | null)
            : undefined;
        const timestamp =
          typeof payload.timestamp === "string" ? payload.timestamp : null;
        const derivedTaskId = typeof payload.task_id === "string" ? payload.task_id : taskId;
        const entry: TaskStreamEvent = {
          taskId: derivedTaskId,
          event: eventName,
          status,
          logs,
          result,
          timestamp,
        };

        if (eventName === "heartbeat") {
          updateState({
            heartbeatAt: timestamp ?? new Date().toISOString(),
            connected: true,
            error: null,
          });
          emitEvent(entry);
          return;
        }

        updateState({
          status: status ?? null,
          logs,
          result: result ?? null,
          lastEventAt: timestamp ?? new Date().toISOString(),
          connected: true,
          error: null,
        });
        emitEvent(entry);

        if (
          autoCloseOnFinish &&
          (eventName === "task_finished" ||
            eventName === "task_missing" ||
            (status && TERMINAL_STATUSES.includes(status)))
        ) {
          const currentSource = sourcesRef.current.get(taskId);
          currentSource?.close();
          sourcesRef.current.delete(taskId);
          updateState({
            connected: false,
          });
        }
      };

      source.addEventListener("task_update", (event) => {
        const payload = safeParse(event.data);
        handlePayload("task_update", payload);
      });

      source.addEventListener("task_finished", (event) => {
        const payload = safeParse(event.data);
        handlePayload("task_finished", payload);
      });

      source.addEventListener("task_missing", (event) => {
        const payload = safeParse(event.data);
        handlePayload("task_missing", payload);
      });

      source.addEventListener("heartbeat", (event) => {
        const payload = safeParse(event.data);
        handlePayload("heartbeat", payload);
      });

      source.onopen = () => {
        updateState({
          connected: true,
          error: null,
        });
      };

      source.onerror = () => {
        updateState({
          connected: false,
          error: "Połączenie SSE przerwane – używam pollingu.",
        });
      };

      sourcesRef.current.set(taskId, source);
      // zapewnij stan startowy
      setStreams((prev) => ({
        ...prev,
        [taskId]: {
          ...(prev[taskId] ?? defaultState),
          connected: true,
          error: null,
        },
      }));
    }

    // Usuń strumienie dla ID, które nie są już śledzone
    sourcesRef.current.forEach((source, sourceTaskId) => {
      if (!targetIds.has(sourceTaskId)) {
        source.close();
        sourcesRef.current.delete(sourceTaskId);
        setStreams((prev) => {
          const next = { ...prev };
          delete next[sourceTaskId];
          return next;
        });
      }
    });

    return () => {
      sourcesRef.current.forEach((source) => source.close());
      sourcesRef.current.clear();
      setStreams({});
    };
  }, [dedupedTaskIds, enabled, autoCloseOnFinish, onEvent]);

  const connectedIds = useMemo(
    () => Object.entries(streams).filter(([, entry]) => entry.connected).map(([id]) => id),
    [streams],
  );

  return { streams, connectedIds, lastEvent };
}

function safeParse(data: unknown): Record<string, unknown> {
  if (typeof data !== "string") return {};
  try {
    return JSON.parse(data) as Record<string, unknown>;
  } catch (err) {
    console.warn("Nie udało się sparsować zdarzenia SSE:", err);
    return {};
  }
}

function mergeLogs(existing: string[], incoming?: string[]): string[] {
  if (!incoming || incoming.length === 0) return existing;
  const next = [...existing];
  for (const entry of incoming) {
    if (entry && !next.includes(entry)) {
      next.push(entry);
    }
  }
  return next;
}

function normalizeStatus(status: unknown): TaskStatus | null {
  if (typeof status !== "string") return null;
  switch (status) {
    case "PENDING":
    case "PROCESSING":
    case "COMPLETED":
    case "FAILED":
    case "LOST":
      return status;
    default:
      return null;
  }
}

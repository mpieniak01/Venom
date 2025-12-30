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
  llmProvider?: string | null;
  llmModel?: string | null;
  llmEndpoint?: string | null;
  llmStatus?: string | null;
  llmRuntimeError?: string | null;
  context?: Record<string, unknown> | null;
};

export type TaskStreamState = {
  status: TaskStatus | null;
  logs: string[];
  result: string | null;
  lastEventAt: string | null;
  heartbeatAt: string | null;
  connected: boolean;
  error: string | null;
  llmProvider: string | null;
  llmModel: string | null;
  llmEndpoint: string | null;
  llmStatus: string | null;
  context: Record<string, unknown> | null;
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
  throttleMs?: number;
};

const defaultState: TaskStreamState = {
  status: null,
  logs: [],
  result: null,
  lastEventAt: null,
  heartbeatAt: null,
  connected: false,
  error: null,
  llmProvider: null,
  llmModel: null,
  llmEndpoint: null,
  llmStatus: null,
  context: null,
};

const TERMINAL_STATUSES: TaskStatus[] = ["COMPLETED", "FAILED", "LOST"];

export function useTaskStream(taskIds: string[], options?: UseTaskStreamOptions): UseTaskStreamResult {
  const {
    enabled = true,
    autoCloseOnFinish = true,
    onEvent,
    throttleMs = 0,
  } = options ?? {};
  const [streams, setStreams] = useState<Record<string, TaskStreamState>>({});
  const [lastEvent, setLastEvent] = useState<TaskStreamEvent | undefined>(undefined);
  const sourcesRef = useRef<Map<string, EventSource>>(new Map());
  const pendingUpdatesRef = useRef<Map<string, Partial<TaskStreamState>>>(new Map());
  const throttleTimersRef = useRef<Map<string, number>>(new Map());
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
    const sources = sourcesRef.current;
    if (!enabled) {
      // Zamknij wszystkie istniejące źródła jeśli streaming wyłączony
      sources.forEach((source) => source.close());
      sources.clear();
      setStreams({});
      return undefined;
    }

    const targetIds = new Set(dedupedTaskIds);

    // Dodaj nowe strumienie
    for (const taskId of targetIds) {
      if (sources.has(taskId)) continue;
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

      const scheduleUpdate = (patch: Partial<TaskStreamState>) => {
        if (throttleMs <= 0) {
          updateState(patch);
          return;
        }
        const pending = pendingUpdatesRef.current.get(taskId) ?? {};
        // Merge logs zamiast nadpisywania, z deduplikacją jak w updateState
        const mergedLogs = mergeLogs(pending.logs ?? [], patch.logs ?? []);
        pendingUpdatesRef.current.set(taskId, {
          ...pending,
          ...patch,
          logs: mergedLogs,
        });
        if (throttleTimersRef.current.has(taskId)) return;
        const timer = window.setTimeout(() => {
          throttleTimersRef.current.delete(taskId);
          const queued = pendingUpdatesRef.current.get(taskId);
          pendingUpdatesRef.current.delete(taskId);
          if (queued) {
            updateState(queued);
          }
        }, throttleMs);
        throttleTimersRef.current.set(taskId, timer);
      };

      const flushPending = () => {
        const timer = throttleTimersRef.current.get(taskId);
        if (timer) {
          window.clearTimeout(timer);
          throttleTimersRef.current.delete(taskId);
        }
        const queued = pendingUpdatesRef.current.get(taskId);
        pendingUpdatesRef.current.delete(taskId);
        if (queued) {
          updateState(queued);
        }
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
        const runtime = extractRuntime(payload);
        const entry: TaskStreamEvent = {
          taskId: derivedTaskId,
          event: eventName,
          status,
          logs,
          result,
          timestamp,
          llmProvider: runtime.provider,
          llmModel: runtime.model,
          llmEndpoint: runtime.endpoint,
          llmStatus: runtime.status,
          llmRuntimeError: runtime.error,
          context: runtime.context,
        };

        if (eventName === "heartbeat") {
          scheduleUpdate({
            heartbeatAt: timestamp ?? new Date().toISOString(),
            connected: true,
            error: null,
            llmProvider: runtime.provider,
            llmModel: runtime.model,
            llmEndpoint: runtime.endpoint,
            llmStatus: runtime.status ?? null,
            context: runtime.context,
          });
          emitEvent(entry);
          return;
        }

        const patch = {
          status: status ?? null,
          logs,
          result: result ?? null,
          lastEventAt: timestamp ?? new Date().toISOString(),
          connected: true,
          error: null,
          llmProvider: runtime.provider,
          llmModel: runtime.model,
          llmEndpoint: runtime.endpoint,
          llmStatus: runtime.status ?? null,
          context: runtime.context,
        };
        const isTerminal =
          eventName === "task_finished" ||
          eventName === "task_missing" ||
          (status && TERMINAL_STATUSES.includes(status));
        if (isTerminal) {
          flushPending();
          updateState(patch);
        } else {
          scheduleUpdate(patch);
        }
        emitEvent(entry);

        if (
          autoCloseOnFinish &&
          (eventName === "task_finished" ||
            eventName === "task_missing" ||
            (status && TERMINAL_STATUSES.includes(status)))
        ) {
          const currentSource = sources.get(taskId);
          currentSource?.close();
          sources.delete(taskId);
          flushPending();
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

      sources.set(taskId, source);
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
    sources.forEach((source, sourceTaskId) => {
      if (!targetIds.has(sourceTaskId)) {
        source.close();
        sources.delete(sourceTaskId);
        const timer = throttleTimersRef.current.get(sourceTaskId);
        if (timer) {
          window.clearTimeout(timer);
          throttleTimersRef.current.delete(sourceTaskId);
        }
        pendingUpdatesRef.current.delete(sourceTaskId);
        setStreams((prev) => {
          const next = { ...prev };
          delete next[sourceTaskId];
          return next;
        });
      }
    });

    const timersSnapshot = throttleTimersRef.current;
    const pendingSnapshot = pendingUpdatesRef.current;
    return () => {
      sources.forEach((source) => source.close());
      sources.clear();
      setStreams({});
      timersSnapshot.forEach((timer) => window.clearTimeout(timer));
      timersSnapshot.clear();
      pendingSnapshot.clear();
    };
  }, [dedupedTaskIds, enabled, autoCloseOnFinish, onEvent, throttleMs]);

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

function extractRuntime(payload: Record<string, unknown>) {
  const provider =
    typeof payload.llm_provider === "string" ? payload.llm_provider : null;
  const model = typeof payload.llm_model === "string" ? payload.llm_model : null;
  const endpoint =
    typeof payload.llm_endpoint === "string" ? payload.llm_endpoint : null;
  const status =
    typeof payload.llm_status === "string" ? payload.llm_status : null;
  const context = isRecord(payload.context_history)
    ? (payload.context_history as Record<string, unknown>)
    : null;
  const runtimeContext =
    context && isRecord(context.llm_runtime)
      ? (context.llm_runtime as Record<string, unknown>)
      : null;
  let error: string | null = null;
  if (runtimeContext) {
    const rawError = runtimeContext.error;
    if (typeof rawError === "string") {
      error = rawError;
    } else if (isRecord(rawError)) {
      const message = rawError.error_message;
      const code = rawError.error_code;
      if (typeof message === "string") {
        error = message;
      } else if (typeof code === "string") {
        error = code;
      }
    }
  }

  return {
    provider,
    model,
    endpoint,
    status,
    error,
    context,
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

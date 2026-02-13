"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { fetchTaskDetail } from "@/hooks/use-api";
import { POLLING } from "@/lib/ui-config";
import type { TaskStatus, ContextUsed } from "@/lib/types";

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
  contextUsed?: ContextUsed | null;
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
  contextUsed: ContextUsed | null;
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
  contextUsed: null,
};

const TERMINAL_STATUSES = new Set<TaskStatus>(["COMPLETED", "FAILED", "LOST"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toStringOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : value != null ? String(value) : null;
}

function extractRuntime(payload: Record<string, unknown>) {
  const runtimeRaw = payload.active_runtime || payload.runtime;
  const runtime = isRecord(runtimeRaw) ? runtimeRaw : {};
  return {
    provider: toStringOrNull(payload.llm_provider ?? runtime.provider),
    model: toStringOrNull(payload.llm_model ?? runtime.model),
    endpoint: toStringOrNull(payload.llm_endpoint ?? runtime.endpoint),
    status: toStringOrNull(payload.llm_status ?? runtime.status),
    error: toStringOrNull(payload.llm_error ?? runtime.error),
    context: isRecord(payload.context) ? payload.context : isRecord(runtime.context) ? runtime.context : null,
  };
}

function normalizeStatus(status: unknown): TaskStatus | null {
  if (!status) return null;
  const s = String(status).toUpperCase();
  if (TERMINAL_STATUSES.has(s as TaskStatus)) return s as TaskStatus;
  if (s === "PENDING" || s === "PROCESSING") return s as TaskStatus;
  return null;
}

function mergeLogs(existing: string[], incoming: string[]): string[] {
  const seen = new Set(existing);
  const result = [...existing];
  incoming.forEach((log) => {
    if (!seen.has(log)) {
      seen.add(log);
      result.push(log);
    }
  });
  return result;
}

function safeParse(data: unknown): Record<string, unknown> {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  if (typeof data !== "string") return {};
  try {
    const parsed = JSON.parse(data);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return {};
  } catch {
    return {};
  }
}

export function useTaskStream(taskIds: string[], options?: UseTaskStreamOptions): UseTaskStreamResult {
  const {
    enabled = true,
    autoCloseOnFinish = true,
    onEvent,
    throttleMs = 250,
  } = options ?? {};

  const [streams, setStreams] = useState<Record<string, TaskStreamState>>({});
  const [lastEvent, setLastEvent] = useState<TaskStreamEvent | undefined>(undefined);

  const onEventRef = useRef<UseTaskStreamOptions["onEvent"]>(onEvent);
  const sourcesRef = useRef<Map<string, EventSource>>(new Map());
  const pendingUpdatesRef = useRef<Map<string, Partial<TaskStreamState>>>(new Map());
  const throttleTimersRef = useRef<Map<string, number>>(new Map());
  const pollTimersRef = useRef<Map<string, number>>(new Map());
  const firstResultSeenRef = useRef<Map<string, boolean>>(new Map());

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
    onEventRef.current = onEvent;
  }, [onEvent]);

  const updateStateById = useCallback((taskId: string, patch: Partial<TaskStreamState>) => {
    setStreams((prev) => {
      const existing = prev[taskId] ?? defaultState;
      const mergedLogs = patch.logs === undefined ? existing.logs : mergeLogs(existing.logs, patch.logs);
      return {
        ...prev,
        [taskId]: {
          ...existing,
          ...patch,
          logs: mergedLogs,
        },
      };
    });
  }, []);

  useEffect(() => {
    if (globalThis.window === undefined) return undefined;
    if (!enabled) {
      sourcesRef.current.forEach((s) => s.close());
      sourcesRef.current.clear();
      pollTimersRef.current.forEach((t) => globalThis.window.clearTimeout(t));
      pollTimersRef.current.clear();
      setStreams({});
      return undefined;
    }

    const targetIds = new Set(dedupedTaskIds);
    const sources = sourcesRef.current;
    const pollIntervalMs = POLLING.TASK_INTERVAL_MS || 2000;

    const emitEvent = (event: TaskStreamEvent) => {
      setLastEvent(event);
      onEventRef.current?.(event);
      if (typeof window !== "undefined") {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const win = window as any;
        win.__lastTaskStreamEvent = event;
        win.__taskStreamEvents = [...(win.__taskStreamEvents ?? []), event].slice(-25);
      }
    };

    const stopPolling = (taskId: string) => {
      const timer = pollTimersRef.current.get(taskId);
      if (timer) {
        globalThis.window.clearTimeout(timer);
        pollTimersRef.current.delete(taskId);
      }
    };

    const pollTask = async (taskId: string) => {
      try {
        const task = await fetchTaskDetail(taskId);
        const status = normalizeStatus(task.status);
        const logs = task.logs as string[] | undefined;
        const result = task.result as string | undefined;

        updateStateById(taskId, {
          status: status ?? null,
          logs,
          result,
          lastEventAt: task.updated_at ?? new Date().toISOString(),
          connected: false,
          error: "SSE connection lost, using polling.",
        });

        const runtime = extractRuntime(task as unknown as Record<string, unknown>);
        emitEvent({
          taskId,
          event: status === "COMPLETED" ? "task_finished" : "task_update",
          status,
          logs,
          result,
          timestamp: task.updated_at,
          llmProvider: runtime.provider,
          llmModel: runtime.model,
          llmEndpoint: runtime.endpoint,
          llmStatus: runtime.status,
          llmRuntimeError: runtime.error,
          context: runtime.context,
        });

        if (status && TERMINAL_STATUSES.has(status)) {
          stopPolling(taskId);
        } else {
          const timer = globalThis.window.setTimeout(() => pollTask(taskId), pollIntervalMs);
          pollTimersRef.current.set(taskId, timer);
        }
      } catch {
        const timer = globalThis.window.setTimeout(() => pollTask(taskId), pollIntervalMs * 2);
        pollTimersRef.current.set(taskId, timer);
      }
    };

    const scheduleUpdate = (taskId: string, patch: Partial<TaskStreamState>) => {
      if (throttleMs <= 0) {
        updateStateById(taskId, patch);
        return;
      }
      const pending = pendingUpdatesRef.current.get(taskId) ?? {};
      const mergedLogs = mergeLogs(pending.logs ?? [], patch.logs ?? []);
      pendingUpdatesRef.current.set(taskId, { ...pending, ...patch, logs: mergedLogs });

      if (throttleTimersRef.current.has(taskId)) return;

      const timer = globalThis.window.setTimeout(() => {
        throttleTimersRef.current.delete(taskId);
        const queued = pendingUpdatesRef.current.get(taskId);
        pendingUpdatesRef.current.delete(taskId);
        if (queued) updateStateById(taskId, queued);
      }, throttleMs);
      throttleTimersRef.current.set(taskId, timer);
    };

    const flushPending = (taskId: string) => {
      const timer = throttleTimersRef.current.get(taskId);
      if (timer) {
        globalThis.window.clearTimeout(timer);
        throttleTimersRef.current.delete(taskId);
      }
      const queued = pendingUpdatesRef.current.get(taskId);
      pendingUpdatesRef.current.delete(taskId);
      if (queued) updateStateById(taskId, queued);
    };

    const handlePayload = (taskId: string, eventName: TaskStreamEventName, payload: Record<string, unknown>) => {
      const status = normalizeStatus(payload.status);
      const logs = Array.isArray(payload.logs) ? payload.logs.map(String) : undefined;
      const result = typeof payload.result === "string" || payload.result === null ? payload.result : undefined;
      const timestamp = typeof payload.timestamp === "string" ? payload.timestamp : null;
      const derivedTaskId = (payload.task_id as string) || taskId;
      const runtime = extractRuntime(payload);
      const contextUsed = (payload.context_used as Record<string, unknown>) || null;

      const entry: TaskStreamEvent = {
        taskId: derivedTaskId,
        event: eventName,
        status,
        logs,
        result,
        timestamp: timestamp as string | null,
        llmProvider: runtime.provider,
        llmModel: runtime.model,
        llmEndpoint: runtime.endpoint,
        llmStatus: runtime.status,
        llmRuntimeError: runtime.error,
        context: runtime.context,
        contextUsed,
      };

      if (eventName === "heartbeat") {
        scheduleUpdate(taskId, {
          heartbeatAt: (timestamp as string | null) ?? new Date().toISOString(),
          connected: true,
          error: null,
          llmProvider: runtime.provider,
          llmModel: runtime.model,
          llmEndpoint: runtime.endpoint,
          llmStatus: runtime.status,
          context: runtime.context,
        });
        emitEvent(entry);
        return;
      }

      const patch = {
        status: status ?? null,
        logs,
        result: result ?? null,
        lastEventAt: (timestamp as string | null) ?? new Date().toISOString(),
        connected: true,
        error: null,
        llmProvider: runtime.provider,
        llmModel: runtime.model,
        llmEndpoint: runtime.endpoint,
        llmStatus: runtime.status,
        context: runtime.context,
        ...(contextUsed ? { contextUsed } : {}),
      };

      const isTerminal = eventName === "task_finished" || eventName === "task_missing" || (status && TERMINAL_STATUSES.has(status));
      const hasResult = typeof result === "string" && result.trim().length > 0;
      const firstResultSeen = firstResultSeenRef.current.get(taskId) ?? false;
      const firstResultNow = hasResult && !firstResultSeen;

      if (firstResultNow) firstResultSeenRef.current.set(taskId, true);

      if (isTerminal) {
        flushPending(taskId);
        updateStateById(taskId, patch);
        stopPolling(taskId);
      } else if (firstResultNow) {
        flushPending(taskId);
        updateStateById(taskId, patch);
      } else {
        scheduleUpdate(taskId, patch);
      }
      emitEvent(entry);

      if (autoCloseOnFinish && isTerminal) {
        const currentSource = sources.get(taskId);
        currentSource?.close();
        sources.delete(taskId);
        updateStateById(taskId, { connected: false });
      }
    };

    // Incremental update
    sources.forEach((source, id) => {
      if (!targetIds.has(id)) {
        source.close();
        sources.delete(id);
        stopPolling(id);
        const timer = throttleTimersRef.current.get(id);
        if (timer) globalThis.window.clearTimeout(timer);
        throttleTimersRef.current.delete(id);
        pendingUpdatesRef.current.delete(id);
        setStreams((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      }
    });

    for (const taskId of targetIds) {
      if (sources.has(taskId)) continue;

      const source = new EventSource(`/api/v1/tasks/${taskId}/stream`);

      source.addEventListener("task_update", (e) => handlePayload(taskId, "task_update", safeParse(e.data)));
      source.addEventListener("task_finished", (e) => handlePayload(taskId, "task_finished", safeParse(e.data)));
      source.addEventListener("task_missing", (e) => handlePayload(taskId, "task_missing", safeParse(e.data)));
      source.addEventListener("heartbeat", (e) => handlePayload(taskId, "heartbeat", safeParse(e.data)));

      source.onopen = () => {
        stopPolling(taskId);
        updateStateById(taskId, { connected: true, error: null });
      };
      source.onerror = () => {
        updateStateById(taskId, { connected: false, error: "SSE failure, polling..." });
        if (!pollTimersRef.current.has(taskId)) {
          pollTask(taskId);
        }
      };

      sources.set(taskId, source);
      pollTask(taskId);
    }
  }, [dedupedTaskIds, enabled, autoCloseOnFinish, throttleMs, updateStateById]);

  return {
    streams,
    connectedIds: Array.from(sourcesRef.current.keys()),
    lastEvent,
  };
}

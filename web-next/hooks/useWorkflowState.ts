"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "@/lib/i18n";
import { getApiBaseUrl } from "@/lib/env";
import type {
  SystemState,
  PlanRequest,
  PlanResponse,
  ApplyResults,
  WorkflowControlOptions,
  WorkflowControlStatePayload,
} from "@/types/workflow-control";

const WORKFLOW_STATE_CACHE_KEY = "workflow_control_state_cache_v1";
const WORKFLOW_OPTIONS_CACHE_KEY = "workflow_control_options_cache_v1";
const WORKFLOW_CACHE_TTL_MS = 60_000;

const buildApiUrl = (path: string): string => {
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${path}` : path;
};

export async function readApiErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const text = await response.text();
    if (!text) return fallback;
    try {
      const parsed = JSON.parse(text) as { detail?: string; message?: string };
      if (typeof parsed?.detail === "string" && parsed.detail.trim()) return parsed.detail;
      if (typeof parsed?.message === "string" && parsed.message.trim()) return parsed.message;
    } catch {
      // Non-JSON payload; return raw text below.
    }
    return text.trim() || fallback;
  } catch {
    return fallback;
  }
}

export function extractSystemStateFromPayload(payload: unknown): SystemState | null {
  if (!payload || typeof payload !== "object" || !("system_state" in payload)) {
    return null;
  }

  const typedPayload = payload as WorkflowControlStatePayload;
  const baseState = typedPayload.system_state;
  if (!baseState) return null;

  return {
    ...baseState,
    config_fields: typedPayload.config_fields ?? baseState.config_fields,
    runtime_services: typedPayload.runtime_services ?? baseState.runtime_services,
    execution_steps: typedPayload.execution_steps ?? baseState.execution_steps,
    graph: typedPayload.graph ?? baseState.graph,
    active_request_id:
      typedPayload.workflow_target?.request_id ?? baseState.active_request_id,
    active_task_status:
      typedPayload.workflow_target?.task_status ?? baseState.active_task_status,
    workflow_status:
      typedPayload.workflow_target?.workflow_status ?? baseState.workflow_status,
    llm_runtime_id:
      typedPayload.workflow_target?.runtime_id ?? baseState.llm_runtime_id,
    llm_provider_name:
      typedPayload.workflow_target?.provider ?? baseState.llm_provider_name,
    llm_model: typedPayload.workflow_target?.model ?? baseState.llm_model,
    allowed_operations:
      typedPayload.workflow_target?.allowed_operations ?? baseState.allowed_operations,
  };
}

function cloneState(state: SystemState): SystemState {
  if (typeof globalThis.structuredClone === "function") {
    return globalThis.structuredClone(state);
  }
  return cloneStateFallback(state);
}

function cloneStateFallback<T>(value: T): T {
  if (value === null || typeof value !== "object") {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((entry) => cloneStateFallback(entry)) as T;
  }
  const cloned: Record<string, unknown> = {};
  for (const [key, entry] of Object.entries(value)) {
    cloned[key] = cloneStateFallback(entry);
  }
  return cloned as T;
}

function stableSerialize(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return "";
  }
}

function readCache<T>(key: string): T | null {
  if (globalThis.window === undefined) return null;
  try {
    const raw = globalThis.window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { ts?: number; data?: T };
    if (!parsed || typeof parsed !== "object" || typeof parsed.ts !== "number") return null;
    if (Date.now() - parsed.ts > WORKFLOW_CACHE_TTL_MS) return null;
    return (parsed.data ?? null) as T | null;
  } catch {
    return null;
  }
}

function writeCache<T>(key: string, data: T): void {
  if (globalThis.window === undefined) return;
  try {
    globalThis.window.sessionStorage.setItem(
      key,
      JSON.stringify({ ts: Date.now(), data }),
    );
  } catch {
    // Ignore storage errors (private mode / quota exceeded).
  }
}

export function useWorkflowState() {
  const t = useTranslation();
  const [systemState, setSystemState] = useState<SystemState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [controlOptions, setControlOptions] =
    useState<WorkflowControlOptions | null>(null);

  const fetchControlOptions = useCallback(async () => {
    try {
      const response = await fetch(buildApiUrl("/api/v1/workflow/control/options"));
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.error")));
      }
      const data = (await response.json()) as WorkflowControlOptions;
      setControlOptions((prev) => {
        if (prev && stableSerialize(prev) === stableSerialize(data)) return prev;
        return data;
      });
      writeCache(WORKFLOW_OPTIONS_CACHE_KEY, data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.error"));
    }
  }, [t]);

  // Fetch system state
  const fetchSystemState = useCallback(async () => {
    try {
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/control/state")
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.error")));
      }
      const data = await response.json();
      const nextState = extractSystemStateFromPayload(data);
      if (nextState) {
        setSystemState((prev) => {
          if (prev && stableSerialize(prev) === stableSerialize(nextState)) return prev;
          return nextState;
        });
        writeCache(WORKFLOW_STATE_CACHE_KEY, nextState);
      } else {
        setSystemState(null);
        throw new Error(t("workflowControl.messages.invalidStatePayload"));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.error"));
    }
  }, [t]);

  // Refresh state
  const refresh = useCallback(() => {
    fetchSystemState();
    fetchControlOptions();
  }, [fetchSystemState, fetchControlOptions]);

  // Plan changes
  const planChanges = useCallback(async (changes: PlanRequest): Promise<PlanResponse | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/control/plan"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(changes),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.planError")));
      }
      return await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.planError"));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  // Apply changes
  const applyChanges = useCallback(async (executionTicket: string): Promise<ApplyResults | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/control/apply"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            execution_ticket: executionTicket,
            confirm_restart: true,
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.applyError")));
      }
      return await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.applyError"));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  // Shared helper for all runtime workflow operations — avoids copy-pasting
  // the workflowId guard, loading flag, and error handling across 5 callbacks.
  const executeWorkflowOperation = useCallback(
    async (operation: string, errorKey: string): Promise<void> => {
      const workflowId = systemState?.active_request_id;
      if (!workflowId) {
        setError(t("workflowControl.messages.noActiveRequest"));
        return;
      }
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(
          buildApiUrl(`/api/v1/workflow/control/workflow/${workflowId}/${operation}`),
          {
            method: "POST",
          }
        );
        if (!response.ok) {
          throw new Error(await readApiErrorMessage(response, t(errorKey)));
        }
        await fetchSystemState();
      } catch (err) {
        setError(err instanceof Error ? err.message : t(errorKey));
      } finally {
        setIsLoading(false);
      }
    },
    [systemState, fetchSystemState, t]
  );

  // Pause workflow
  const pauseWorkflow = useCallback(
    () => executeWorkflowOperation("pause", "workflowControl.messages.pauseError"),
    [executeWorkflowOperation]
  );

  // Resume workflow
  const resumeWorkflow = useCallback(
    () => executeWorkflowOperation("resume", "workflowControl.messages.resumeError"),
    [executeWorkflowOperation]
  );

  // Cancel workflow
  const cancelWorkflow = useCallback(
    () => executeWorkflowOperation("cancel", "workflowControl.messages.cancelError"),
    [executeWorkflowOperation]
  );

  // Retry workflow
  const retryWorkflow = useCallback(
    () => executeWorkflowOperation("retry", "workflowControl.messages.retryError"),
    [executeWorkflowOperation]
  );

  // Dry run
  const dryRun = useCallback(
    () => executeWorkflowOperation("dry_run", "workflowControl.messages.dryRunError"),
    [executeWorkflowOperation]
  );

  // Initial load and polling
  useEffect(() => {
    const cachedState = readCache<SystemState>(WORKFLOW_STATE_CACHE_KEY);
    if (cachedState) {
      setSystemState(cachedState);
    }
    const cachedOptions = readCache<WorkflowControlOptions>(WORKFLOW_OPTIONS_CACHE_KEY);
    if (cachedOptions) {
      setControlOptions(cachedOptions);
    }

    fetchSystemState();
    fetchControlOptions();
    // Poll every 5 seconds
    const interval = setInterval(fetchSystemState, 5000);
    return () => clearInterval(interval);
  }, [fetchSystemState, fetchControlOptions]);

  // Draft State Management
  const [draftState, setDraftState] = useState<SystemState | null>(null);
  // Snapshot helper: include only user-configurable fields (exclude telemetry).
  // Used consistently for both rebase detection and hasChanges to keep them in sync.
  const snapshotConfig = useCallback((s: SystemState) => ({
    decision_strategy: s.decision_strategy,
    intent_mode: s.intent_mode,
    kernel: s.kernel,
    embedding_model: s.embedding_model,
    provider_active: s.provider?.active,
    provider_source: s.provider_source,
    embedding_source: s.embedding_source,
  }), []);
  // Tracks the last server configuration snapshot that draft was initialized/rebased to.
  // Stores only user-configurable fields so telemetry changes don't falsely block rebase.
  const lastServerStateRef = useRef<string | null>(null);

  // Sync draft with system state: rebase only when user has no local edits.
  useEffect(() => {
    if (!systemState) return;
    const serializedNew = stableSerialize(snapshotConfig(systemState));
    if (!draftState) {
      // First load: initialize draft from server state
      setDraftState(cloneState(systemState));
      lastServerStateRef.current = serializedNew;
      return;
    }
    // If draft's configuration still matches the previous server snapshot, user hasn't edited — rebase.
    if (stableSerialize(snapshotConfig(draftState)) === lastServerStateRef.current) {
      setDraftState(cloneState(systemState));
    }
    // Always advance the reference regardless of rebase decision.
    lastServerStateRef.current = serializedNew;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [systemState]);

  // hasChanges: compare only user-configurable fields, not telemetry.
  const hasChanges = (() => {
    if (!systemState || !draftState) return false;
    return (
      stableSerialize(snapshotConfig(systemState)) !==
      stableSerialize(snapshotConfig(draftState))
    );
  })();

  const updateNode = useCallback((nodeId: string, data: unknown) => {
    setDraftState((prev) => {
      if (!prev) return null;
      // Deep merge logic simplified for MVP - usually we'd use immer or similar
      // Mapping node ID to state keys (simplified mapping)
      const next = { ...prev };
      const typedData = data as Record<string, unknown>;

      if (nodeId === 'decision') next.decision_strategy = typedData.strategy as string;
      if (nodeId === "intent" && typedData.intentMode) {
        next.intent_mode = typedData.intentMode as string;
      }
      if (nodeId === 'kernel') next.kernel = typedData.kernel as string;
      if (nodeId === "provider" && typedData.provider) {
        const provider = typedData.provider as { active?: string; sourceType?: string };
        next.provider = provider;
        if (provider.sourceType) {
          next.provider_source = provider.sourceType;
        }
      }
      if (nodeId === "embedding") {
        next.embedding_model = typedData.model as string;
        if (typeof typedData.sourceType === "string") {
          next.embedding_source = typedData.sourceType;
        }
      }
      if (nodeId === "config" && Array.isArray(typedData.configFields)) {
        next.config_fields = typedData.configFields as typeof next.config_fields;
      }

      return next;
    });
  }, []);

  const reset = useCallback(() => {
    if (systemState) {
      setDraftState(cloneState(systemState));
    }
  }, [systemState]);

  return {
    systemState,
    draftState: draftState || systemState, // Fallback to system if draft not ready
    hasChanges,
    isLoading,
    error,
    controlOptions,
    refresh,
    updateNode,
    reset,
    planChanges,
    applyChanges,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    retryWorkflow,
    dryRun,
  };
}

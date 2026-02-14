"use client";

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "@/lib/i18n";
import { getApiBaseUrl } from "@/lib/env";
import type {
  SystemState,
  PlanRequest,
  PlanResponse,
  ApplyResults,
} from "@/types/workflow-control";

const WORKFLOW_STORAGE_KEY = "workflow_control_id";
const DEFAULT_WORKFLOW_ID = "00000000-0000-0000-0000-000000000001";

const buildApiUrl = (path: string): string => {
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${path}` : path;
};

function createUuidV4(): string {
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi) return DEFAULT_WORKFLOW_ID;

  if (typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID();
  }

  if (typeof cryptoApi.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    cryptoApi.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20, 32)}`;
  }

  return DEFAULT_WORKFLOW_ID;
}

// Generate a valid UUID v4 for the workflow
// In production, this should come from the backend or be persisted
const getOrCreateWorkflowId = (): string => {
  if (typeof window === "undefined") return DEFAULT_WORKFLOW_ID;

  const stored = localStorage.getItem(WORKFLOW_STORAGE_KEY);
  if (stored) return stored;

  if (typeof window !== "undefined") {
    const uuid = createUuidV4();
    localStorage.setItem(WORKFLOW_STORAGE_KEY, uuid);
    return uuid;
  }

  return DEFAULT_WORKFLOW_ID;
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
  if (payload && typeof payload === "object" && "system_state" in payload) {
    return (payload as { system_state: SystemState }).system_state;
  }
  return null;
}

export function useWorkflowState() {
  const t = useTranslation();
  const [systemState, setSystemState] = useState<SystemState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
        setSystemState(nextState);
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
  }, [fetchSystemState]);

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

  // Pause workflow
  const pauseWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = getOrCreateWorkflowId();
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/operations/pause"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_id: workflowId,
            operation: "pause",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.pauseError")));
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.pauseError"));
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState, t]);

  // Resume workflow
  const resumeWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = getOrCreateWorkflowId();
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/operations/resume"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_id: workflowId,
            operation: "resume",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.resumeError")));
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.resumeError"));
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState, t]);

  // Cancel workflow
  const cancelWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = getOrCreateWorkflowId();
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/operations/cancel"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_id: workflowId,
            operation: "cancel",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.cancelError")));
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.cancelError"));
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState, t]);

  // Retry workflow
  const retryWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = getOrCreateWorkflowId();
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/operations/retry"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_id: workflowId,
            operation: "retry",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.retryError")));
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.retryError"));
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState, t]);

  // Dry run
  const dryRun = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = getOrCreateWorkflowId();
      const response = await fetch(
        buildApiUrl("/api/v1/workflow/operations/dry-run"),
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            workflow_id: workflowId,
            operation: "dry_run",
          }),
        }
      );
      if (!response.ok) {
        throw new Error(await readApiErrorMessage(response, t("workflowControl.messages.dryRunError")));
      }
      await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : t("workflowControl.messages.dryRunError"));
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  // Initial load and polling
  useEffect(() => {
    fetchSystemState();
    // Poll every 5 seconds
    const interval = setInterval(fetchSystemState, 5000);
    return () => clearInterval(interval);
  }, [fetchSystemState]);

  return {
    systemState,
    isLoading,
    error,
    refresh,
    planChanges,
    applyChanges,
    pauseWorkflow,
    resumeWorkflow,
    cancelWorkflow,
    retryWorkflow,
    dryRun,
  };
}

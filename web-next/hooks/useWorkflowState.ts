"use client";

import { useState, useEffect, useCallback } from "react";
import type {
  SystemState,
  PlanRequest,
  PlanResponse,
  ApplyResults,
} from "@/types/workflow-control";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useWorkflowState() {
  const [systemState, setSystemState] = useState<SystemState | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch system state
  const fetchSystemState = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/control/state`
      );
      if (!response.ok) {
        throw new Error("Failed to fetch system state");
      }
      const data = await response.json();
      setSystemState(data.system_state);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    }
  }, []);

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
        `${API_BASE_URL}/api/v1/workflow/control/plan`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(changes),
        }
      );
      if (!response.ok) {
        throw new Error("Failed to plan changes");
      }
      return await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Apply changes
  const applyChanges = useCallback(async (executionTicket: string): Promise<ApplyResults | null> => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/control/apply`,
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
        throw new Error("Failed to apply changes");
      }
      return await response.json();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Pause workflow
  const pauseWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // Generate a workflow ID (in real app, get from state)
      const workflowId = "main-workflow";
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/operations/pause`,
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
        throw new Error("Failed to pause workflow");
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState]);

  // Resume workflow
  const resumeWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = "main-workflow";
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/operations/resume`,
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
        throw new Error("Failed to resume workflow");
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState]);

  // Cancel workflow
  const cancelWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = "main-workflow";
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/operations/cancel`,
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
        throw new Error("Failed to cancel workflow");
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState]);

  // Retry workflow
  const retryWorkflow = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = "main-workflow";
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/operations/retry`,
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
        throw new Error("Failed to retry workflow");
      }
      await fetchSystemState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, [fetchSystemState]);

  // Dry run
  const dryRun = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const workflowId = "main-workflow";
      const response = await fetch(
        `${API_BASE_URL}/api/v1/workflow/operations/dry-run`,
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
        throw new Error("Failed to perform dry run");
      }
      const result = await response.json();
      // Show result in a toast or notification
      console.log("Dry run result:", result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

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

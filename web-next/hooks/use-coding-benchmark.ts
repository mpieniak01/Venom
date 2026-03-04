import { useState, useRef, useCallback, useEffect } from "react";
import type {
  CodingBenchmarkStatus,
  CodingBenchmarkStartRequest,
  CodingBenchmarkRun,
  BenchmarkLog,
} from "@/lib/types";
import { getApiBaseUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";
import {
  emitActiveLlmStateLog,
  emitPreflightLogs,
  resolveStartFailureMessage,
} from "@/hooks/benchmark-preflight";

const POLLING_INTERVAL_MS = 1500;
const resolveApiRoot = (): string => getApiBaseUrl() || "";
const buildApiUrl = (path: string): string => `${resolveApiRoot()}${path}`;

// ─── Pure helpers (exported for tests) ───────────────────────────────────────

/** Map raw API status string to hook CodingBenchmarkStatus, or null if unchanged. */
export function resolvePollStatus(apiStatus: string): CodingBenchmarkStatus | null {
  if (apiStatus === "completed") return "completed";
  if (apiStatus === "completed_with_failures") return "completed_with_failures";
  if (apiStatus === "failed") return "failed";
  if (apiStatus === "running") return "running";
  return null;
}

export interface CodingBenchmarkProgress {
  completed: number;
  total: number;
}

/** Build structured progress data, or null if not applicable. */
export function buildProgressLog(
  summary: { completed: number; total_jobs: number } | null | undefined,
): CodingBenchmarkProgress | null {
  if (!summary || summary.total_jobs === 0) return null;
  return {
    completed: summary.completed,
    total: summary.total_jobs,
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

interface UseCodingBenchmarkReturn {
  status: CodingBenchmarkStatus;
  runId: string | null;
  run: CodingBenchmarkRun | null;
  logs: BenchmarkLog[];
  error: string | null;
  startBenchmark: (req: CodingBenchmarkStartRequest) => Promise<void>;
  reset: () => void;
  deleteRun: (runId: string) => Promise<boolean>;
  clearAllRuns: () => Promise<boolean>;
}

export function useCodingBenchmark(): UseCodingBenchmarkReturn {
  const t = useTranslation();
  const [status, setStatus] = useState<CodingBenchmarkStatus>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<CodingBenchmarkRun | null>(null);
  const [logs, setLogs] = useState<BenchmarkLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastProgressRef = useRef<string | null>(null);

  const addLog = useCallback((message: string, level: BenchmarkLog["level"] = "info") => {
    setLogs((prev) => [
      ...prev,
      { timestamp: new Date().toISOString(), message, level },
    ]);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    setStatus("idle");
    setRunId(null);
    setRun(null);
    setLogs([]);
    setError(null);
    lastProgressRef.current = null;
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const pollStatus = useCallback(async (id: string) => {
    try {
      const response = await fetch(buildApiUrl(`/api/v1/benchmark/coding/${id}/status`));
      if (!response.ok) {
        throw new Error(`Status fetch failed: ${response.statusText}`);
      }
      const data: CodingBenchmarkRun = await response.json();
      setRun(data);

      if (data.status === "completed") {
        stopPolling();
        setStatus("completed");
        const rate = data.summary?.success_rate ?? 0;
        addLog(
          t("benchmark.coding.logs.completed", {
            rate: rate.toFixed(1),
          }),
          "info",
        );
      } else if (data.status === "completed_with_failures") {
        stopPolling();
        setStatus("completed_with_failures");
        const completed = data.summary?.completed ?? 0;
        const failed = data.summary?.failed ?? 0;
        const total = data.summary?.total_jobs ?? 0;
        addLog(
          t("benchmark.coding.logs.completedWithFailures", {
            completed,
            failed,
            total,
          }),
          "warning",
        );
      } else if (data.status === "failed") {
        stopPolling();
        setStatus("failed");
        const msg = data.error_message || t("benchmark.coding.logs.unknownError");
        setError(msg);
        addLog(
          t("benchmark.coding.logs.failed", {
            message: msg,
          }),
          "error",
        );
      } else if (data.status === "running") {
        setStatus("running");
        const progress = buildProgressLog(data.summary);
        if (progress) {
          const progressKey = `${progress.completed}/${progress.total}`;
          if (lastProgressRef.current !== progressKey) {
            lastProgressRef.current = progressKey;
            addLog(
              t("benchmark.coding.logs.progress", {
                completed: progress.completed,
                total: progress.total,
              }),
              "info",
            );
          }
        }
      }
    } catch (err) {
      console.error("Coding benchmark polling error:", err);
    }
  }, [addLog, stopPolling, t]);

  const startBenchmark = useCallback(async (req: CodingBenchmarkStartRequest) => {
    reset();
    setStatus("pending");
    emitPreflightLogs(addLog, {
      preparing: t("benchmark.preflight.preparing"),
      unloading: t("benchmark.preflight.unloading"),
      starting: t("benchmark.preflight.starting"),
      success: t("benchmark.preflight.success"),
      conflict: t("benchmark.preflight.conflict"),
      runtimeUnhealthy: t("benchmark.preflight.runtimeUnhealthy"),
    });
    await emitActiveLlmStateLog(buildApiUrl, addLog, t);
    addLog(
      t("benchmark.coding.logs.startingModels", {
        models: req.models.join(", "),
      }),
      "info",
    );
    addLog(
      t("benchmark.coding.logs.startingTasks", {
        tasks: (req.tasks ?? ["python_complex"]).join(", "),
      }),
      "info",
    );

    try {
      const response = await fetch(buildApiUrl("/api/v1/benchmark/coding/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const detail = (errorData as { detail?: string }).detail;
        const message = resolveStartFailureMessage(response, detail, t);
        throw new Error(message);
      }

      const data = await response.json() as { run_id: string; message?: string };
      const id = data.run_id;
      setRunId(id);
      setStatus("running");
      addLog(t("benchmark.preflight.success"), "info");
      addLog(
        t("benchmark.coding.logs.started", {
          runId: id.slice(0, 8),
        }),
        "info",
      );

      pollingIntervalRef.current = setInterval(() => {
        pollStatus(id);
      }, POLLING_INTERVAL_MS);
    } catch (err) {
      const msg = err instanceof Error ? err.message : t("benchmark.coding.logs.unknownError");
      setError(msg);
      setStatus("failed");
      addLog(
        t("benchmark.coding.logs.startError", {
          message: msg,
        }),
        "error",
      );
      stopPolling();
    }
  }, [addLog, pollStatus, reset, stopPolling, t]);

  const deleteRun = useCallback(async (id: string) => {
    try {
      const response = await fetch(buildApiUrl(`/api/v1/benchmark/coding/${id}`), {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Nie udało się usunąć coding benchmark run");
      addLog(
        t("benchmark.coding.logs.deleted", {
          runId: id.slice(0, 8),
        }),
        "info",
      );
      return true;
    } catch (err) {
      console.error(err);
      addLog(t("benchmark.coding.logs.deleteError"), "error");
      return false;
    }
  }, [addLog, t]);

  const clearAllRuns = useCallback(async () => {
    try {
      const response = await fetch(buildApiUrl("/api/v1/benchmark/coding/all"), {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Nie udało się wyczyścić coding benchmarków");
      addLog(t("benchmark.coding.logs.cleared"), "info");
      return true;
    } catch (err) {
      console.error(err);
      addLog(t("benchmark.coding.logs.clearError"), "error");
      return false;
    }
  }, [addLog, t]);

  return {
    status,
    runId,
    run,
    logs,
    error,
    startBenchmark,
    reset,
    deleteRun,
    clearAllRuns,
  };
}

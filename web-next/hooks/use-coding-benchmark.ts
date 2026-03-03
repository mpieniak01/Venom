import { useState, useRef, useCallback } from "react";
import type {
  CodingBenchmarkStatus,
  CodingBenchmarkStartRequest,
  CodingBenchmarkRun,
  BenchmarkLog,
} from "@/lib/types";
import { getApiBaseUrl } from "@/lib/env";

const POLLING_INTERVAL_MS = 1500;
const resolveApiRoot = (): string => getApiBaseUrl() || "";
const buildApiUrl = (path: string): string => `${resolveApiRoot()}${path}`;

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
  const [status, setStatus] = useState<CodingBenchmarkStatus>("idle");
  const [runId, setRunId] = useState<string | null>(null);
  const [run, setRun] = useState<CodingBenchmarkRun | null>(null);
  const [logs, setLogs] = useState<BenchmarkLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  const pollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
  }, [stopPolling]);

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
        addLog(`Coding benchmark zakończony. Wynik: ${rate.toFixed(1)}% zadań zdanych.`, "info");
      } else if (data.status === "failed") {
        stopPolling();
        setStatus("failed");
        const msg = data.error_message || "Nieznany błąd";
        setError(msg);
        addLog(`Coding benchmark nie powiódł się: ${msg}`, "error");
      } else if (data.status === "running") {
        setStatus("running");
        const completed = data.summary?.completed ?? 0;
        const total = data.summary?.total_jobs ?? 0;
        if (total > 0) {
          addLog(`Postęp: ${completed}/${total} zadań ukończonych`, "info");
        }
      }
    } catch (err) {
      console.error("Coding benchmark polling error:", err);
    }
  }, [addLog, stopPolling]);

  const startBenchmark = useCallback(async (req: CodingBenchmarkStartRequest) => {
    reset();
    setStatus("pending");
    addLog(`Uruchamiam coding benchmark dla modeli: ${req.models.join(", ")}`, "info");
    addLog(`Zadania: ${(req.tasks ?? ["python_complex"]).join(", ")}`, "info");

    try {
      const response = await fetch(buildApiUrl("/api/v1/benchmark/coding/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(
          (errorData as { detail?: string }).detail ||
          `Nie udało się uruchomić coding benchmarku: ${response.statusText}`
        );
      }

      const data = await response.json() as { run_id: string; message?: string };
      const id = data.run_id;
      setRunId(id);
      setStatus("running");
      addLog(`Coding benchmark uruchomiony (ID: ${id.slice(0, 8)}...)`, "info");

      pollingIntervalRef.current = setInterval(() => {
        pollStatus(id);
      }, POLLING_INTERVAL_MS);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Nieznany błąd";
      setError(msg);
      setStatus("failed");
      addLog(`Błąd uruchomienia: ${msg}`, "error");
      stopPolling();
    }
  }, [addLog, pollStatus, reset, stopPolling]);

  const deleteRun = useCallback(async (id: string) => {
    try {
      const response = await fetch(buildApiUrl(`/api/v1/benchmark/coding/${id}`), {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Nie udało się usunąć coding benchmark run");
      addLog(`Usunięto coding benchmark run: ${id.slice(0, 8)}...`, "info");
      return true;
    } catch (err) {
      console.error(err);
      addLog("Błąd podczas usuwania coding benchmark run", "error");
      return false;
    }
  }, [addLog]);

  const clearAllRuns = useCallback(async () => {
    try {
      const response = await fetch(buildApiUrl("/api/v1/benchmark/coding/all"), {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("Nie udało się wyczyścić coding benchmarków");
      addLog("Wyczyszczono historię coding benchmarków", "info");
      return true;
    } catch (err) {
      console.error(err);
      addLog("Błąd czyszczenia historii coding benchmarków", "error");
      return false;
    }
  }, [addLog]);

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

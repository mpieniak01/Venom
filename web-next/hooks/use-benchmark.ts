import { useState, useRef, useCallback } from "react";
import type {
    BenchmarkConfig,
    BenchmarkLog,
    BenchmarkModelResult,
    BenchmarkStatus,
    BenchmarkStartResponse,
    BenchmarkStatusResponse,
} from "@/lib/types";
import { getApiBaseUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";
import { classifyStartError, emitPreflightLogs } from "@/hooks/benchmark-preflight";

const POLLING_INTERVAL_MS = 1000;
const resolveApiRoot = (): string => getApiBaseUrl() || "";
const buildApiUrl = (path: string): string => `${resolveApiRoot()}${path}`;

interface UseBenchmarkReturn {
    status: BenchmarkStatus;
    logs: BenchmarkLog[];
    results: BenchmarkModelResult[];
    error: string | null;
    startBenchmark: (config: BenchmarkConfig) => Promise<void>;
    reset: () => void;
    deleteBenchmark: (id: string) => Promise<boolean>;
    clearAllBenchmarks: () => Promise<boolean>;
}

export function useBenchmark(): UseBenchmarkReturn {
    const t = useTranslation();
    const [status, setStatus] = useState<BenchmarkStatus>("idle");
    const [logs, setLogs] = useState<BenchmarkLog[]>([]);
    const [results, setResults] = useState<BenchmarkModelResult[]>([]);
    const [error, setError] = useState<string | null>(null);

    // Ref for polling interval to clear it on unmount/stop
    const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    const lastModelRef = useRef<string | null>(null);

    const addLog = useCallback((message: string, level: BenchmarkLog["level"] = "info") => {
        setLogs((prev) => [
            ...prev,
            {
                timestamp: new Date().toISOString(),
                message,
                level,
            },
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
        setLogs([]);
        setResults([]);
        setError(null);
    }, [stopPolling]);

    const pollStatus = useCallback(async (benchmarkId: string) => {
        try {
            const response = await fetch(buildApiUrl(`/api/v1/benchmark/${benchmarkId}/status`));

            if (!response.ok) {
                throw new Error(`Failed to fetch status: ${response.statusText}`);
            }

            const data: BenchmarkStatusResponse = await response.json();

            setResults(data.results ?? []);

            // Add progress log based on current_model
            if (data.status === "running" && data.current_model) {
                if (lastModelRef.current !== data.current_model) {
                    lastModelRef.current = data.current_model;
                    addLog(
                        t("benchmark.preflight.testingModel", { model: data.current_model }),
                        "info",
                    );
                }
            }

            if (data.status === "completed") {
                stopPolling();
                setStatus("completed");
                addLog("Benchmark zakończony sukcesem!", "info");
            } else if (data.status === "failed") {
                stopPolling();
                setStatus("failed");
                setError(data.error_message || "Benchmark failed");
                addLog(`Benchmark nie powiódł się: ${data.error_message}`, "error");
            }

        } catch (err) {
            console.error("Polling error:", err);
            // Don't stop polling immediately on temporary network errors, but maybe count them?
            // For simplicity, we just log.
        }
    }, [addLog, stopPolling, t]);

    const startBenchmark = useCallback(async (config: BenchmarkConfig) => {
        reset();
        setStatus("running");
        lastModelRef.current = null;
        const unknownLabel = t("benchmark.preflight.unknown");
        emitPreflightLogs(addLog, {
            preparing: t("benchmark.preflight.preparing"),
            unloading: t("benchmark.preflight.unloading"),
            starting: t("benchmark.preflight.starting"),
            success: t("benchmark.preflight.success"),
            conflict: t("benchmark.preflight.conflict"),
            runtimeUnhealthy: t("benchmark.preflight.runtimeUnhealthy"),
        });
        try {
            const stateResp = await fetch(buildApiUrl("/api/v1/system/llm-servers/active"));
            if (stateResp.ok) {
                const state = await stateResp.json() as { active_server?: string; active_model?: string };
                addLog(
                    t("benchmark.preflight.llmState", {
                        server: state.active_server ?? unknownLabel,
                        model: state.active_model ?? unknownLabel,
                    }),
                    "info",
                );
            }
        } catch {
            addLog(t("benchmark.preflight.llmStateUnavailable"), "warning");
        }
        addLog(
            t("benchmark.preflight.startingModels", { models: config.models.join(", ") }),
            "info",
        );

        try {
            const response = await fetch(buildApiUrl("/api/v1/benchmark/start"), {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    models: config.models,
                    num_questions: config.num_questions,
                }),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                const detail = (errorData as { detail?: string }).detail;
                const fallbackMessage = t("benchmark.preflight.genericError", {
                    status: response.status,
                    statusText: response.statusText || t("benchmark.preflight.unknownStatusText"),
                });
                const classifiedMessage = classifyStartError(detail, {
                    conflict: t("benchmark.preflight.conflict"),
                    runtimeUnhealthy: t("benchmark.preflight.runtimeUnhealthy"),
                });
                const message =
                    response.status === 409
                        ? t("benchmark.preflight.conflict")
                        : detail
                            ? classifiedMessage
                            : fallbackMessage;
                throw new Error(message);
            }

            const data: BenchmarkStartResponse = await response.json();
            const benchmarkId = data.benchmark_id;

            addLog(t("benchmark.preflight.success"), "info");
            addLog(t("benchmark.preflight.started", { benchmarkId }), "info");

            // Start polling
            pollingIntervalRef.current = setInterval(() => {
                pollStatus(benchmarkId);
            }, POLLING_INTERVAL_MS);

        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : "Unknown error";
            setError(errorMessage);
            setStatus("failed");
            addLog(`Błąd uruchomienia: ${errorMessage}`, "error");
            stopPolling();
        }
    }, [addLog, pollStatus, reset, stopPolling, t]);

    // Clean up on unmount
    // useEffect(() => () => stopPolling(), [stopPolling]); // Commented out to avoid double mounting issues in strict mode canceling too early, manual reset handles most.

    const deleteBenchmark = useCallback(async (benchmarkId: string) => {
        try {
            const response = await fetch(buildApiUrl(`/api/v1/benchmark/${benchmarkId}`), {
                method: "DELETE",
            });
            if (!response.ok) throw new Error("Failed to delete benchmark");
            addLog(`Usunięto benchmark: ${benchmarkId}`, "info");
            return true;
        } catch (err) {
            console.error(err);
            addLog("Błąd usuwania benchmarku", "error");
            return false;
        }
    }, [addLog]);

    const clearAllBenchmarks = useCallback(async () => {
        try {
            const response = await fetch(buildApiUrl("/api/v1/benchmark/all"), {
                method: "DELETE",
            });
            if (!response.ok) throw new Error("Failed to clear benchmarks");
            addLog("Wyczyszczono historię benchmarków", "info");
            return true;
        } catch (err) {
            console.error(err);
            addLog("Błąd czyszczenia historii", "error");
            return false;
        }
    }, [addLog]);

    return {
        status,
        logs,
        results,
        error,
        startBenchmark,
        reset,
        deleteBenchmark,
        clearAllBenchmarks,
    };
}

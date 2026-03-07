"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearAllSelfLearningRuns,
  deleteSelfLearningRun,
  getSelfLearningCapabilities,
  getUnifiedModelCatalog,
  getSelfLearningRunStatus,
  listSelfLearningRuns,
  resolveAcademyApiErrorMessage,
  startSelfLearning,
  type SelfLearningEmbeddingProfile,
  type SelfLearningRunStatus,
  type SelfLearningStartRequest,
  type SelfLearningStatus,
  type SelfLearningTrainableModelInfo,
} from "@/lib/academy-api";
import { ApiError } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { useTranslation } from "@/lib/i18n";
import {
  SelfLearningConfigurator,
  type SelfLearningConfig,
} from "./self-learning-configurator";
import { SelfLearningConsole } from "./self-learning-console";
import { SelfLearningHistory } from "./self-learning-history";

const POLL_INTERVAL_MS = 2000;

const TERMINAL_STATUSES: ReadonlySet<SelfLearningStatus> = new Set([
  "completed",
  "completed_with_warnings",
  "failed",
]);

export function isTerminalSelfLearningStatus(status: SelfLearningStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function resolveSelfLearningStartErrorMessage(
  error: unknown,
  fallbackMessage: string,
): string {
  const resolved = resolveAcademyApiErrorMessage(error);
  if (resolved && resolved !== "Unknown Academy API error") {
    return resolved;
  }
  if (error instanceof Error && error.message.trim().length > 0) return error.message;
  return fallbackMessage;
}

export function SelfLearningPanel() {
  const t = useTranslation();
  const { pushToast } = useToast();
  const [starting, setStarting] = useState(false);
  const [runs, setRuns] = useState<SelfLearningRunStatus[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [currentRun, setCurrentRun] = useState<SelfLearningRunStatus | null>(null);
  const [trainableModels, setTrainableModels] = useState<SelfLearningTrainableModelInfo[]>([]);
  const [runtimeOptions, setRuntimeOptions] = useState<Array<{ id: string; label: string }>>([]);
  const [selectedRuntime, setSelectedRuntime] = useState("");
  const [runtimeModelAuditIssuesCount, setRuntimeModelAuditIssuesCount] = useState(0);
  const [embeddingProfiles, setEmbeddingProfiles] = useState<SelfLearningEmbeddingProfile[]>([]);
  const [defaultEmbeddingProfileId, setDefaultEmbeddingProfileId] = useState<string | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollFailuresRef = useRef(0);

  const loadHistory = useCallback(async () => {
    try {
      const response = await listSelfLearningRuns(50);
      setRuns(response.runs);
      setSelectedRunId((prev) => {
        if (prev && response.runs.some((item) => item.run_id === prev)) {
          return prev;
        }
        return response.runs[0]?.run_id ?? null;
      });
    } catch (error) {
      console.error("Failed to load self-learning history", error);
    }
  }, []);

  const loadCapabilities = useCallback(async () => {
    try {
      const response = await getSelfLearningCapabilities();
      let trainable = response.trainable_models ?? [];
      try {
        const catalog = await getUnifiedModelCatalog();
        // Unified catalog is the source of truth, including an empty list.
        trainable =
          catalog.trainable_base_models.length > 0
            ? catalog.trainable_base_models
            : (catalog.trainable_models ?? []);
        setRuntimeModelAuditIssuesCount(
          Number(catalog.model_audit?.issues_count ?? 0),
        );
        const availableRuntimes = (catalog.runtimes ?? [])
          .filter(
            (runtime) =>
              runtime.source_type === "local-runtime" &&
              runtime.configured &&
              runtime.available,
          )
          .map((runtime) => ({ id: runtime.runtime_id, label: runtime.runtime_id }));
        setRuntimeOptions(availableRuntimes);
        const activeRuntimeId = String(
          catalog.active?.runtime_id || catalog.active?.active_server || "",
        ).trim();
        setSelectedRuntime((prev) => {
          if (prev && availableRuntimes.some((runtime) => runtime.id === prev)) {
            return prev;
          }
          if (
            activeRuntimeId &&
            availableRuntimes.some((runtime) => runtime.id === activeRuntimeId)
          ) {
            return activeRuntimeId;
          }
          return "";
        });
      } catch (catalogError) {
        console.warn(
          "Failed to load unified model catalog for self-learning; falling back to capabilities payload:",
          catalogError,
        );
      }
      setTrainableModels(trainable);
      setEmbeddingProfiles(response.embedding_profiles ?? []);
      setDefaultEmbeddingProfileId(response.default_embedding_profile_id ?? null);
    } catch (error) {
      console.error("Failed to load self-learning capabilities", error);
    }
  }, []);

  const resolveSelfLearningStartError = useCallback(
    (error: unknown): string =>
      resolveSelfLearningStartErrorMessage(error, t("academy.common.unknownError")),
    [t]
  );

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    pollFailuresRef.current = 0;
  }, []);

  const pollRun = useCallback(
    async (runId: string) => {
      try {
        const run = await getSelfLearningRunStatus(runId);
        pollFailuresRef.current = 0;
        setCurrentRun(run);
        setRuns((prev) => {
          const next = prev.filter((item) => item.run_id !== run.run_id);
          next.unshift(run);
          return next;
        });
        if (isTerminalSelfLearningStatus(run.status)) {
          stopPolling();
          await loadHistory();
        }
      } catch (error) {
        console.error("Failed to poll self-learning status", error);
        if (error instanceof ApiError && error.status >= 500) {
          pollFailuresRef.current += 1;
          if (pollFailuresRef.current < 3) {
            return;
          }
        }
        stopPolling();
      }
    },
    [loadHistory, stopPolling]
  );

  const beginPolling = useCallback(
    (runId: string) => {
      stopPolling();
      pollingRef.current = setInterval(() => {
        pollRun(runId).catch((error) => {
          console.error("Failed to poll self-learning status", error);
          stopPolling();
        });
      }, POLL_INTERVAL_MS);
    },
    [pollRun, stopPolling]
  );

  useEffect(() => {
    const initialize = async () => {
      await loadHistory();
      await loadCapabilities();
    };
    initialize().catch((error) => {
      console.error("Failed to initialize self-learning panel", error);
    });
    return () => stopPolling();
  }, [loadCapabilities, loadHistory, stopPolling]);

  useEffect(() => {
    if (!selectedRunId) {
      stopPolling();
      setCurrentRun(null);
      return;
    }
    const existing = runs.find((item) => item.run_id === selectedRunId) ?? null;
    setCurrentRun(existing);
    if (existing && !isTerminalSelfLearningStatus(existing.status)) {
      beginPolling(existing.run_id);
    }
  }, [beginPolling, runs, selectedRunId, stopPolling]);

  const handleStart = useCallback(
    async (config: SelfLearningConfig) => {
      try {
        setStarting(true);
        const payload: SelfLearningStartRequest = {
          mode: config.mode,
          sources: config.sources,
          limits: config.limits,
          dry_run: config.dry_run,
          llm_config: config.llm_config,
          rag_config: config.rag_config,
        };
        const response = await startSelfLearning(payload);
        pushToast(response.message, "success");
        setSelectedRunId(response.run_id);
        await pollRun(response.run_id);
        beginPolling(response.run_id);
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 400)) {
          console.error("Failed to start self-learning", error);
        }
        pushToast(resolveSelfLearningStartError(error), "error");
      } finally {
        setStarting(false);
      }
    },
    [beginPolling, pollRun, pushToast, resolveSelfLearningStartError]
  );

  const handleDeleteRun = useCallback(
    async (runId: string) => {
      try {
        await deleteSelfLearningRun(runId);
        if (selectedRunId === runId) {
          setSelectedRunId(null);
        }
        await loadHistory();
      } catch (error) {
        console.error("Failed to delete self-learning run", error);
        pushToast(error instanceof Error ? error.message : t("academy.common.unknownError"), "error");
      }
    },
    [loadHistory, pushToast, selectedRunId, t]
  );

  const handleClearAll = useCallback(async () => {
    try {
      await clearAllSelfLearningRuns();
      stopPolling();
      setCurrentRun(null);
      setSelectedRunId(null);
      setRuns([]);
    } catch (error) {
      console.error("Failed to clear self-learning runs", error);
      pushToast(error instanceof Error ? error.message : t("academy.common.unknownError"), "error");
    }
  }, [pushToast, stopPolling, t]);

  const consoleStatus = useMemo<SelfLearningStatus>(() => {
    return currentRun?.status ?? "pending";
  }, [currentRun?.status]);

  const consoleLogs = useMemo(() => currentRun?.logs ?? [], [currentRun?.logs]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-[color:var(--text-heading)]">
          {t("academy.selfLearning.title")}
        </h2>
        <p className="text-sm text-hint">{t("academy.selfLearning.subtitle")}</p>
        {runtimeModelAuditIssuesCount > 0 ? (
          <p className="mt-1 text-xs text-amber-300">
            {t("academy.selfLearning.runtimeModelAuditWarning", {
              count: String(runtimeModelAuditIssuesCount),
            })}
          </p>
        ) : null}
      </div>

      <SelfLearningConfigurator
        loading={starting}
        trainableModels={trainableModels.filter(
          (model) =>
            !selectedRuntime ||
            Boolean(model.runtime_compatibility?.[selectedRuntime]),
        )}
        runtimeOptions={runtimeOptions}
        selectedRuntime={selectedRuntime}
        onRuntimeChange={setSelectedRuntime}
        embeddingProfiles={embeddingProfiles}
        defaultEmbeddingProfileId={defaultEmbeddingProfileId}
        onStart={handleStart}
      />

      <SelfLearningConsole logs={consoleLogs} status={consoleStatus} />

      <SelfLearningHistory
        runs={runs}
        selectedRunId={selectedRunId}
        onSelectRun={setSelectedRunId}
        onRefresh={loadHistory}
        onDeleteRun={handleDeleteRun}
        onClearAll={handleClearAll}
      />
    </div>
  );
}

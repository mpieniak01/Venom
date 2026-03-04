"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearAllSelfLearningRuns,
  deleteSelfLearningRun,
  getSelfLearningCapabilities,
  getSelfLearningRunStatus,
  listSelfLearningRuns,
  startSelfLearning,
  type SelfLearningEmbeddingProfile,
  type SelfLearningLlmConfig,
  type SelfLearningRagConfig,
  type SelfLearningRunStatus,
  type SelfLearningStartRequest,
  type SelfLearningStatus,
  type SelfLearningTrainableModelInfo,
} from "@/lib/academy-api";
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

export function SelfLearningPanel() {
  const t = useTranslation();
  const { pushToast } = useToast();
  const [starting, setStarting] = useState(false);
  const [runs, setRuns] = useState<SelfLearningRunStatus[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [currentRun, setCurrentRun] = useState<SelfLearningRunStatus | null>(null);
  const [trainableModels, setTrainableModels] = useState<SelfLearningTrainableModelInfo[]>([]);
  const [embeddingProfiles, setEmbeddingProfiles] = useState<SelfLearningEmbeddingProfile[]>([]);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      setTrainableModels(response.trainable_models ?? []);
      setEmbeddingProfiles(response.embedding_profiles ?? []);
    } catch (error) {
      console.error("Failed to load self-learning capabilities", error);
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const pollRun = useCallback(
    async (runId: string) => {
      try {
        const run = await getSelfLearningRunStatus(runId);
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
        stopPolling();
      }
    },
    [loadHistory, stopPolling]
  );

  const beginPolling = useCallback(
    (runId: string) => {
      stopPolling();
      pollingRef.current = setInterval(() => {
        void pollRun(runId);
      }, POLL_INTERVAL_MS);
    },
    [pollRun, stopPolling]
  );

  useEffect(() => {
    void loadHistory();
    void loadCapabilities();
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
          llm_config: config.llm_config as SelfLearningLlmConfig | null,
          rag_config: config.rag_config as SelfLearningRagConfig | null,
        };
        const response = await startSelfLearning(payload);
        pushToast(response.message, "success");
        setSelectedRunId(response.run_id);
        await pollRun(response.run_id);
        beginPolling(response.run_id);
      } catch (error) {
        console.error("Failed to start self-learning", error);
        pushToast(error instanceof Error ? error.message : t("academy.common.unknownError"), "error");
      } finally {
        setStarting(false);
      }
    },
    [beginPolling, pollRun, pushToast, t]
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
      </div>

      <SelfLearningConfigurator
        loading={starting}
        trainableModels={trainableModels}
        embeddingProfiles={embeddingProfiles}
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

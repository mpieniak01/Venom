"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearAllSelfLearningRuns,
  deleteSelfLearningRun,
  getSelfLearningCapabilities,
  getSelfLearningEvaluationBaseline,
  getUnifiedModelCatalog,
  getSelfLearningRunStatus,
  listSelfLearningRuns,
  resolveAcademyApiErrorMessage,
  startSelfLearning,
  updateSelfLearningEvaluationBaseline,
  type SelfLearningEvaluationBaselineResponse,
  type SelfLearningEmbeddingProfile,
  type SelfLearningRunStatus,
  type SelfLearningStartRequest,
  type SelfLearningStatus,
  type SelfLearningTrainableModelInfo,
} from "@/lib/academy-api";
import { ApiError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useTranslation } from "@/lib/i18n";
import { normalizeRuntimeId } from "@/lib/cockpit-runtime-selection";
import {
  SelfLearningConfigurator,
  type SelfLearningConfig,
} from "./self-learning-configurator";
import { SelfLearningConsole } from "./self-learning-console";
import { SelfLearningHistory } from "./self-learning-history";

const POLL_INTERVAL_MS = 2000;
const BASELINE_FIELDS = [
  "repo_qa_accuracy",
  "code_localization_accuracy",
  "fix_success_rate",
  "hallucination_rate_max",
] as const;

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
  if (resolved) {
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
  const [evaluationBaseline, setEvaluationBaseline] = useState<SelfLearningEvaluationBaselineResponse | null>(null);
  const [baselineDraft, setBaselineDraft] = useState<Record<string, string>>({});
  const [baselineSaving, setBaselineSaving] = useState(false);

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
          .map((runtime) => ({
            id: normalizeRuntimeId(runtime.runtime_id),
            label: runtime.runtime_id,
          }));
        setRuntimeOptions(availableRuntimes);
        const activeRuntimeId = normalizeRuntimeId(
          String(catalog.active?.runtime_id || catalog.active?.active_server || ""),
        );
        setSelectedRuntime((prev) => {
          const normalizedPrev = normalizeRuntimeId(prev);
          if (
            normalizedPrev &&
            availableRuntimes.some((runtime) => runtime.id === normalizedPrev)
          ) {
            return normalizedPrev;
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

  const loadEvaluationBaseline = useCallback(async () => {
    try {
      const payload = await getSelfLearningEvaluationBaseline();
      setEvaluationBaseline(payload);
      setBaselineDraft({
        "llm_finetune.repo_qa_accuracy": String(payload.llm_finetune.repo_qa_accuracy),
        "llm_finetune.code_localization_accuracy": String(
          payload.llm_finetune.code_localization_accuracy
        ),
        "llm_finetune.fix_success_rate": String(payload.llm_finetune.fix_success_rate),
        "llm_finetune.hallucination_rate_max": String(
          payload.llm_finetune.hallucination_rate_max
        ),
        "rag_index.repo_qa_accuracy": String(payload.rag_index.repo_qa_accuracy),
        "rag_index.code_localization_accuracy": String(
          payload.rag_index.code_localization_accuracy
        ),
        "rag_index.fix_success_rate": String(payload.rag_index.fix_success_rate),
        "rag_index.hallucination_rate_max": String(payload.rag_index.hallucination_rate_max),
      });
    } catch (error) {
      console.error("Failed to load self-learning evaluation baseline", error);
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
      await loadEvaluationBaseline();
    };
    initialize().catch((error) => {
      console.error("Failed to initialize self-learning panel", error);
    });
    return () => stopPolling();
  }, [loadCapabilities, loadEvaluationBaseline, loadHistory, stopPolling]);

  const handleBaselineChange = useCallback((key: string, value: string) => {
    setBaselineDraft((prev) => ({ ...prev, [key]: value }));
  }, []);

  const handleSaveBaseline = useCallback(async () => {
    try {
      setBaselineSaving(true);
      const parseValue = (key: string): number => {
        const parsed = Number(baselineDraft[key]);
        if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) {
          throw new Error(`${key} must be between 0 and 1`);
        }
        return parsed;
      };
      const payload = {
        llm_finetune: {
          repo_qa_accuracy: parseValue("llm_finetune.repo_qa_accuracy"),
          code_localization_accuracy: parseValue(
            "llm_finetune.code_localization_accuracy"
          ),
          fix_success_rate: parseValue("llm_finetune.fix_success_rate"),
          hallucination_rate_max: parseValue("llm_finetune.hallucination_rate_max"),
        },
        rag_index: {
          repo_qa_accuracy: parseValue("rag_index.repo_qa_accuracy"),
          code_localization_accuracy: parseValue(
            "rag_index.code_localization_accuracy"
          ),
          fix_success_rate: parseValue("rag_index.fix_success_rate"),
          hallucination_rate_max: parseValue("rag_index.hallucination_rate_max"),
        },
      };
      const updated = await updateSelfLearningEvaluationBaseline(payload);
      setEvaluationBaseline(updated);
      pushToast("Evaluation baseline updated", "success");
    } catch (error) {
      const message =
        error instanceof Error && error.message.trim().length > 0
          ? error.message
          : t("academy.common.unknownError");
      pushToast(message, "error");
    } finally {
      setBaselineSaving(false);
    }
  }, [baselineDraft, pushToast, t]);

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

      <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-[color:var(--text-heading)]">
            Eval Baseline
          </h3>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSaveBaseline}
            disabled={baselineSaving || evaluationBaseline === null}
          >
            {baselineSaving ? "Saving..." : "Save baseline"}
          </Button>
        </div>
        {evaluationBaseline === null ? (
          <p className="text-xs text-hint">No baseline loaded.</p>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {(["llm_finetune", "rag_index"] as const).map((mode) => (
              <div key={mode} className="rounded-lg border border-[color:var(--ui-border)] p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.15em] text-[color:var(--text-secondary)]">
                  {mode}
                </p>
                <div className="grid gap-2">
                  {BASELINE_FIELDS.map((field) => {
                    const key = `${mode}.${field}`;
                    return (
                      <label key={key} className="grid gap-1 text-xs text-[color:var(--text-secondary)]">
                        <span>{field}</span>
                        <input
                          className="rounded-md border border-[color:var(--ui-border)] bg-transparent px-2 py-1 text-[color:var(--text-heading)]"
                          type="number"
                          min={0}
                          max={1}
                          step={0.01}
                          value={baselineDraft[key] ?? ""}
                          onChange={(event) => handleBaselineChange(key, event.target.value)}
                        />
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

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

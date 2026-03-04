"use client";

import { Trash2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { SelfLearningRunStatus, SelfLearningStatus } from "@/lib/academy-api";
import { useLanguage, useTranslation } from "@/lib/i18n";

interface Props {
  readonly runs: readonly SelfLearningRunStatus[];
  readonly selectedRunId: string | null;
  readonly onSelectRun: (runId: string) => void;
  readonly onRefresh: () => Promise<void> | void;
  readonly onDeleteRun: (runId: string) => Promise<void> | void;
  readonly onClearAll: () => Promise<void> | void;
}

const STATUS_CLASS: Record<SelfLearningStatus, string> = {
  pending: "text-amber-300",
  running: "text-blue-300",
  completed: "text-emerald-300",
  completed_with_warnings: "text-yellow-300",
  failed: "text-red-300",
};

function readArtifactString(
  artifacts: Record<string, unknown>,
  key: string
): string | null {
  const value = artifacts[key];
  if (typeof value === "string") {
    const normalized = value.trim();
    return normalized.length > 0 ? normalized : null;
  }
  return null;
}

function readKnowledgeFreshness(
  artifacts: Record<string, unknown>
): { indexedAt: string | null; mode: string | null } {
  const payload = artifacts["knowledge_freshness"];
  if (payload && typeof payload === "object") {
    const typed = payload as Record<string, unknown>;
    const indexedAt = typeof typed.indexed_at === "string" ? typed.indexed_at : null;
    const mode = typeof typed.mode === "string" ? typed.mode : null;
    return { indexedAt, mode };
  }
  return { indexedAt: null, mode: null };
}

function readEvaluationSummary(
  artifacts: Record<string, unknown>
): { score: number | null; decision: string | null } {
  const payload = artifacts["evaluation"];
  if (payload && typeof payload === "object") {
    const typed = payload as Record<string, unknown>;
    const score = typeof typed.score === "number" ? typed.score : null;
    const decision = typeof typed.decision === "string" ? typed.decision : null;
    return { score, decision };
  }
  return { score: null, decision: null };
}

function SelfLearningRunList({
  runs,
  selectedRunId,
  onSelectRun,
  onRefresh,
  onClearAll,
  language,
}: Pick<Props, "runs" | "selectedRunId" | "onSelectRun" | "onRefresh" | "onClearAll"> & {
  language: string;
}) {
  const t = useTranslation();
  return (
    <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[color:var(--text-heading)]">
          {t("academy.selfLearning.history.title")}
        </h3>
        <div className="flex items-center gap-1">
          <Button onClick={onRefresh} variant="ghost" size="sm" className="h-8 w-8 p-0" aria-label={t("academy.common.refresh")}>
            <RefreshCw className="h-4 w-4" />
          </Button>
          <Button
            onClick={onClearAll}
            variant="ghost"
            size="sm"
            className="h-8 w-8 p-0 text-red-300 hover:text-red-200"
            aria-label={t("academy.selfLearning.history.clearAll")}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
        {runs.length === 0 ? (
          <p className="text-sm text-hint">{t("academy.selfLearning.history.empty")}</p>
        ) : (
          runs.map((run) => {
            const isSelected = run.run_id === selectedRunId;
            return (
              <button
                type="button"
                key={run.run_id}
                onClick={() => onSelectRun(run.run_id)}
                className={`w-full rounded-lg border p-3 text-left transition ${
                  isSelected
                    ? "border-violet-500/50 bg-violet-500/10"
                    : "border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] hover:border-[color:var(--ui-border-strong)]"
                }`}
              >
                <p className="font-mono text-xs text-[color:var(--text-heading)]">{run.run_id.slice(0, 8)}</p>
                <p className={`mt-1 text-xs font-semibold ${STATUS_CLASS[run.status]}`}>
                  {t(`academy.selfLearning.status.${run.status === "completed_with_warnings" ? "completedWithWarnings" : run.status}`)}
                </p>
                <p className="mt-1 text-xs text-hint">
                  {new Date(run.created_at).toLocaleString(language)}
                </p>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

function SelfLearningRunDetails({
  selectedRun,
  onDeleteRun,
  language,
}: {
  selectedRun: SelfLearningRunStatus | null;
  onDeleteRun: Props["onDeleteRun"];
  language: string;
}) {
  const t = useTranslation();
  const selectedCommitSha = selectedRun
    ? readArtifactString(selectedRun.artifacts, "repo_commit_sha")
    : null;
  const selectedSnapshotAt = selectedRun
    ? readArtifactString(selectedRun.artifacts, "knowledge_snapshot_at")
    : null;
  const selectedKnowledgeFreshness = selectedRun
    ? readKnowledgeFreshness(selectedRun.artifacts)
    : { indexedAt: null, mode: null };
  const selectedEvaluation = selectedRun
    ? readEvaluationSummary(selectedRun.artifacts)
    : { score: null, decision: null };

  return (
      <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-4">
        <h3 className="text-sm font-semibold text-[color:var(--text-heading)]">
          {t("academy.selfLearning.history.details")}
        </h3>

        {selectedRun ? (
          <>
            <div className="grid gap-2 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-3 text-xs text-[color:var(--text-secondary)] md:grid-cols-2">
              <div>
                <p className="font-semibold text-[color:var(--text-heading)]">{selectedRun.run_id}</p>
                <p>{t(`academy.selfLearning.modes.${selectedRun.mode}`)}</p>
              </div>
              <div>
                <p>{t("academy.selfLearning.history.sources")}: {selectedRun.sources.join(", ")}</p>
                <p>{t("academy.selfLearning.history.progress")}: {selectedRun.progress.files_processed}/{selectedRun.progress.files_discovered}</p>
              </div>
            </div>

            <div className="overflow-x-auto rounded-lg border border-[color:var(--ui-border)]">
              <table className="w-full text-left text-xs">
                <tbody>
                  <tr className="border-b border-[color:var(--ui-border)]">
                    <th className="px-3 py-2 text-[color:var(--text-secondary)]">{t("academy.selfLearning.history.metrics.files")}</th>
                    <td className="px-3 py-2">{selectedRun.progress.files_processed}</td>
                  </tr>
                  <tr className="border-b border-[color:var(--ui-border)]">
                    <th className="px-3 py-2 text-[color:var(--text-secondary)]">{t("academy.selfLearning.history.metrics.chunks")}</th>
                    <td className="px-3 py-2">{selectedRun.progress.chunks_created}</td>
                  </tr>
                  <tr className="border-b border-[color:var(--ui-border)]">
                    <th className="px-3 py-2 text-[color:var(--text-secondary)]">{t("academy.selfLearning.history.metrics.records")}</th>
                    <td className="px-3 py-2">{selectedRun.progress.records_created}</td>
                  </tr>
                  <tr>
                    <th className="px-3 py-2 text-[color:var(--text-secondary)]">{t("academy.selfLearning.history.metrics.vectors")}</th>
                    <td className="px-3 py-2">{selectedRun.progress.indexed_vectors}</td>
                  </tr>
                  {selectedCommitSha ? (
                    <tr className="border-t border-[color:var(--ui-border)]">
                      <th className="px-3 py-2 text-[color:var(--text-secondary)]">
                        {t("academy.selfLearning.history.metrics.commit")}
                      </th>
                      <td className="px-3 py-2 font-mono">{selectedCommitSha.slice(0, 12)}</td>
                    </tr>
                  ) : null}
                  {selectedSnapshotAt ? (
                    <tr>
                      <th className="px-3 py-2 text-[color:var(--text-secondary)]">
                        {t("academy.selfLearning.history.metrics.snapshot")}
                      </th>
                      <td className="px-3 py-2">
                        {new Date(selectedSnapshotAt).toLocaleString(language)}
                      </td>
                    </tr>
                  ) : null}
                  {selectedKnowledgeFreshness.indexedAt ? (
                    <tr>
                      <th className="px-3 py-2 text-[color:var(--text-secondary)]">
                        {t("academy.selfLearning.history.metrics.freshness")}
                      </th>
                      <td className="px-3 py-2">
                        {new Date(selectedKnowledgeFreshness.indexedAt).toLocaleString(language)}
                        {selectedKnowledgeFreshness.mode
                          ? ` (${selectedKnowledgeFreshness.mode})`
                          : ""}
                      </td>
                    </tr>
                  ) : null}
                  {selectedEvaluation.score !== null ? (
                    <tr>
                      <th className="px-3 py-2 text-[color:var(--text-secondary)]">
                        {t("academy.selfLearning.history.metrics.evalScore")}
                      </th>
                      <td className="px-3 py-2">{selectedEvaluation.score.toFixed(4)}</td>
                    </tr>
                  ) : null}
                  {selectedEvaluation.decision ? (
                    <tr>
                      <th className="px-3 py-2 text-[color:var(--text-secondary)]">
                        {t("academy.selfLearning.history.metrics.evalDecision")}
                      </th>
                      <td className="px-3 py-2">
                        {t(
                          `academy.selfLearning.history.metrics.evalDecisionValues.${selectedEvaluation.decision}`
                        )}
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            {selectedRun.error_message ? (
              <p className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
                {selectedRun.error_message}
              </p>
            ) : null}

            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="outline"
                className="gap-2 border-red-500/40 text-red-200 hover:bg-red-500/10"
                onClick={() => onDeleteRun(selectedRun.run_id)}
              >
                <Trash2 className="h-4 w-4" />
                {t("academy.selfLearning.history.delete")}
              </Button>
            </div>
          </>
        ) : (
          <p className="text-sm text-hint">{t("academy.selfLearning.history.noSelection")}</p>
        )}
      </div>
  );
}

export function SelfLearningHistory({
  runs,
  selectedRunId,
  onSelectRun,
  onRefresh,
  onDeleteRun,
  onClearAll,
}: Props) {
  const { language } = useLanguage();
  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? null;

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(260px,340px)_1fr]">
      <SelfLearningRunList
        runs={runs}
        selectedRunId={selectedRunId}
        onSelectRun={onSelectRun}
        onRefresh={onRefresh}
        onClearAll={onClearAll}
        language={language}
      />
      <SelfLearningRunDetails
        selectedRun={selectedRun}
        onDeleteRun={onDeleteRun}
        language={language}
      />
    </div>
  );
}

"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import type { CodingBenchmarkRun, CodingJob, CodingBenchmarkRunStatus } from "@/lib/types";
import { Clock, RefreshCw, Trash2, X, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { getApiBaseUrl } from "@/lib/env";
import { useLanguage, useTranslation } from "@/lib/i18n";
import { BenchmarkCodingCharts } from "@/components/benchmark/benchmark-coding-charts";

interface BenchmarkCodingResultsProps {
  readonly currentRun: CodingBenchmarkRun | null;
  readonly onDelete: (runId: string) => Promise<boolean>;
  readonly onClearAll: () => Promise<boolean>;
}

interface HistoryItem {
  run_id: string;
  status: CodingBenchmarkRunStatus;
  config: CodingBenchmarkRun["config"];
  summary?: CodingBenchmarkRun["summary"];
  created_at: string;
  finished_at?: string | null;
  error_message?: string | null;
}

export function BenchmarkCodingResults({
  currentRun,
  onDelete,
  onClearAll,
}: BenchmarkCodingResultsProps) {
  const t = useTranslation();
  const { language } = useLanguage();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<CodingBenchmarkRun | null>(currentRun);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [loadingSelected, setLoadingSelected] = useState(false);
  const apiBase = useMemo(() => getApiBaseUrl() || "", []);

  const fetchHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/benchmark/coding/list?limit=50`);
      if (!res.ok) return;
      const data = await res.json();
      const runs = (data.runs || []) as HistoryItem[];
      setHistory(runs);

      if (currentRun?.run_id) {
        setSelectedRunId(currentRun.run_id);
        return;
      }
      if (selectedRunId && runs.some((item) => item.run_id === selectedRunId)) {
        return;
      }
      setSelectedRunId(runs[0]?.run_id ?? null);
    } catch (e) {
      console.error("Failed to fetch coding benchmark history", e);
    } finally {
      setLoadingHistory(false);
    }
  }, [apiBase, currentRun?.run_id, selectedRunId]);

  const fetchRunDetails = useCallback(async (runId: string) => {
    setLoadingSelected(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/benchmark/coding/${runId}/status`);
      if (!res.ok) return;
      const data = (await res.json()) as CodingBenchmarkRun;
      setSelectedRun(data);
    } catch (e) {
      console.error("Failed to fetch coding benchmark run details", e);
    } finally {
      setLoadingSelected(false);
    }
  }, [apiBase]);

  useEffect(() => {
    void fetchHistory();
  }, [fetchHistory]);

  useEffect(() => {
    if (!currentRun) return;
    setSelectedRun(currentRun);
    setSelectedRunId(currentRun.run_id);
  }, [currentRun]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      return;
    }
    if (currentRun?.run_id === selectedRunId && currentRun.jobs.length > 0) {
      setSelectedRun(currentRun);
      return;
    }
    if (selectedRun?.run_id === selectedRunId && selectedRun.jobs.length > 0) {
      return;
    }
    void fetchRunDetails(selectedRunId);
  }, [selectedRunId, currentRun, selectedRun, fetchRunDetails]);

  const handleDelete = async (id: string) => {
    if (!confirm(t("benchmark.coding.results.confirmDelete"))) return;
    const success = await onDelete(id);
    if (!success) return;

    if (selectedRunId === id) {
      setSelectedRunId(null);
      setSelectedRun(null);
    }
    await fetchHistory();
  };

  const handleClearAll = async () => {
    if (!confirm(t("benchmark.coding.results.confirmClearAll"))) return;
    const success = await onClearAll();
    if (!success) return;
    setHistory([]);
    setSelectedRunId(null);
    setSelectedRun(null);
  };

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return "-";
    return new Date(iso).toLocaleString(language, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const resolveStatusDot = (status: CodingBenchmarkRunStatus) => {
    if (status === "completed") return "bg-emerald-500";
    if (status === "completed_with_failures") return "bg-amber-400";
    if (status === "failed") return "bg-rose-500";
    if (status === "running") return "bg-blue-400 animate-pulse";
    return "bg-zinc-500";
  };

  const resolveRunStatusLabel = (status: CodingBenchmarkRunStatus) => {
    if (status === "completed") return t("benchmark.coding.status.completed");
    if (status === "completed_with_failures") {
      return t("benchmark.coding.status.completedWithFailures");
    }
    if (status === "failed") return t("benchmark.coding.status.failed");
    if (status === "running") return t("benchmark.coding.status.running");
    return t("benchmark.coding.status.pending");
  };

  return (
    <div className="space-y-6">
      <BenchmarkCodingCharts jobs={selectedRun?.jobs ?? []} />

      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-4 xl:order-2">
          <div className="flex items-center justify-between">
            <h4 className="heading-h4 text-[color:var(--text-heading)]">
              {t("benchmark.coding.results.selectedRun")}
            </h4>
            {loadingSelected && (
              <RefreshCw className="h-4 w-4 animate-spin text-[color:var(--ui-muted)]" />
            )}
          </div>

          {!selectedRun ? (
            <div className="text-sm text-[color:var(--ui-muted)] py-6 text-center">
              {t("benchmark.coding.results.noSelectedRun")}
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--terminal)] p-3 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[color:var(--ui-muted)]">{selectedRun.run_id}</span>
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-[10px] font-medium",
                      selectedRun.status === "completed" && "bg-emerald-500/20 text-emerald-300",
                      selectedRun.status === "completed_with_failures" && "bg-amber-500/20 text-amber-300",
                      selectedRun.status === "failed" && "bg-rose-500/20 text-rose-300",
                      selectedRun.status === "running" && "bg-blue-500/20 text-blue-300",
                      selectedRun.status === "pending" && "bg-zinc-500/20 text-zinc-300",
                    )}
                  >
                    {resolveRunStatusLabel(selectedRun.status)}
                  </span>
                </div>

                {selectedRun.summary && (
                  <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[color:var(--text-secondary)] sm:grid-cols-3">
                    <span>{t("benchmark.coding.results.models")}: {selectedRun.config.models.length}</span>
                    <span>{t("benchmark.coding.results.tasks")}: {selectedRun.config.tasks.join(", ")}</span>
                    <span>{selectedRun.summary.completed}/{selectedRun.summary.total_jobs}</span>
                    <span>{t("benchmark.coding.status.failed")}: {selectedRun.summary.failed}</span>
                    <span>{t("benchmark.coding.status.pending")}: {selectedRun.summary.pending}</span>
                    <span>
                      {selectedRun.summary.queue_finished
                        ? t("benchmark.coding.results.queueFinished")
                        : t("benchmark.coding.results.queueNotFinished")}
                    </span>
                  </div>
                )}
              </div>

              <JobsTable jobs={selectedRun.jobs} t={t} />
            </>
          )}
        </div>

        <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-4 xl:order-1">
          <div className="flex items-center justify-between">
            <h4 className="heading-h4 text-[color:var(--text-heading)]">
              {t("benchmark.coding.results.runHistory")}
            </h4>
            <div className="flex gap-2">
              <button
                onClick={fetchHistory}
                className="rounded-lg p-2 text-[color:var(--ui-muted)] transition-colors hover:bg-[color:var(--ui-surface-hover)] hover:text-[color:var(--text-primary)]"
                title={t("benchmark.coding.results.refresh")}
              >
                <RefreshCw className={cn("h-4 w-4", loadingHistory && "animate-spin")} />
              </button>
              {history.length > 0 && (
                <button
                  onClick={handleClearAll}
                  className="flex items-center gap-2 rounded-lg p-2 text-xs font-medium text-rose-400 transition-colors hover:bg-rose-500/20 hover:text-rose-300"
                >
                  <Trash2 className="h-4 w-4" />
                  {t("benchmark.coding.results.clearAll")}
                </button>
              )}
            </div>
          </div>

          {history.length === 0 ? (
            <div className="text-center py-8 text-[color:var(--ui-muted)] text-sm">
              {t("benchmark.coding.results.noHistory")}
            </div>
          ) : (
            <div className="grid max-h-[28rem] gap-3 overflow-y-auto pr-1">
              {history.map((item) => (
                <div
                  key={item.run_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelectedRunId(item.run_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSelectedRunId(item.run_id);
                    }
                  }}
                  className={cn(
                    "group rounded-xl border p-3 text-left transition-colors focus:outline-none focus:ring-2 focus:ring-violet-500/50",
                    selectedRunId === item.run_id
                      ? "border-violet-500/50 bg-violet-500/10"
                      : "border-[color:var(--ui-border)] bg-[color:var(--terminal)] hover:border-[color:var(--ui-border-strong)]",
                  )}
                >
                  <div className="mb-2 flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className={cn("h-2 w-2 shrink-0 rounded-full", resolveStatusDot(item.status))} />
                        <span className="font-mono text-xs text-[color:var(--ui-muted)]">
                          {item.run_id.slice(0, 8)}
                        </span>
                        <span className="text-[10px] text-[color:var(--text-secondary)] flex items-center gap-1">
                          <Clock className="h-3 w-3" />
                          {formatDate(item.created_at)}
                        </span>
                      </div>
                      <div className="mt-1 text-xs text-[color:var(--text-primary)]">
                        {resolveRunStatusLabel(item.status)}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        void handleDelete(item.run_id);
                      }}
                      className="opacity-0 p-1 text-[color:var(--ui-muted)] transition-all hover:text-rose-400 group-hover:opacity-100"
                      title={t("benchmark.coding.results.deleteRun")}
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>

                  <div className="text-xs text-[color:var(--text-secondary)]">
                    {t("benchmark.coding.results.models")}: {item.config.models.join(", ")}
                  </div>
                  <div className="text-xs text-[color:var(--text-secondary)]">
                    {t("benchmark.coding.results.tasks")}: {item.config.tasks.join(", ")}
                  </div>

                  {item.summary && (
                    <div className="mt-1 text-xs text-[color:var(--ui-muted)]">
                      {item.summary.completed}/{item.summary.total_jobs} • {item.summary.success_rate.toFixed(1)}%
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function JobsTable({
  jobs,
  t,
}: Readonly<{ jobs: ReadonlyArray<CodingJob>; t: (path: string) => string }>) {
  const renderJobResult = (job: CodingJob) => {
    if (job.passed === true) {
      return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mx-auto" />;
    }
    if (job.passed === false) {
      return <XCircle className="w-3.5 h-3.5 text-rose-400 mx-auto" />;
    }
    if (job.status === "running") {
      return <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin mx-auto" />;
    }
    return <span className="text-[color:var(--ui-muted)]">-</span>;
  };

  const formatDuration = (value: number | null | undefined) =>
    value == null ? "-" : value.toFixed(1);

  return (
    <div className="overflow-x-auto rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)]">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-[color:var(--ui-border)] text-[color:var(--text-secondary)]">
            <th className="py-2 px-3 font-medium">{t("benchmark.coding.results.table.model")}</th>
            <th className="py-2 px-3 font-medium">{t("benchmark.coding.results.table.task")}</th>
            <th className="py-2 px-3 font-medium">{t("benchmark.coding.results.table.mode")}</th>
            <th className="py-2 px-3 text-center font-medium">{t("benchmark.coding.results.table.status")}</th>
            <th className="py-2 px-3 text-right font-medium">{t("benchmark.coding.results.table.timeSeconds")}</th>
            <th className="py-2 px-3 text-center font-medium">{t("benchmark.coding.results.table.result")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--ui-border)]">
          {jobs.map((job) => (
            <tr key={job.id}>
              <td className="py-2 px-3 font-medium text-[color:var(--text-primary)]">{job.model}</td>
              <td className="py-2 px-3 text-[color:var(--text-secondary)]">{job.task}</td>
              <td className="py-2 px-3 text-[color:var(--ui-muted)]">{job.mode}</td>
              <td className="py-2 px-3 text-center">
                <JobStatusBadge status={job.status} />
              </td>
              <td className="py-2 px-3 text-right text-[color:var(--ui-muted)]">
                {formatDuration(job.coding_seconds)}
              </td>
              <td className="py-2 px-3 text-center">{renderJobResult(job)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JobStatusBadge({ status }: Readonly<{ status: string }>) {
  const classes = cn(
    "px-2 py-0.5 rounded-full text-[10px] font-medium",
    status === "completed" && "bg-emerald-500/20 text-emerald-300",
    status === "failed" && "bg-rose-500/20 text-rose-300",
    status === "running" && "bg-amber-500/20 text-amber-300",
    status === "pending" && "bg-zinc-500/20 text-zinc-400",
    status === "skipped" && "bg-blue-500/20 text-blue-300",
  );
  return <span className={classes}>{status}</span>;
}

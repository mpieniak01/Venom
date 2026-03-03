"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import type { CodingBenchmarkRun, CodingJob } from "@/lib/types";
import { Clock, RefreshCw, Trash2, X, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { getApiBaseUrl } from "@/lib/env";
import { useTranslation } from "@/lib/i18n";

interface BenchmarkCodingResultsProps {
  readonly currentRun: CodingBenchmarkRun | null;
  readonly onDelete: (runId: string) => Promise<boolean>;
  readonly onClearAll: () => Promise<boolean>;
}

interface HistoryItem {
  run_id: string;
  status: string;
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
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const apiBase = useMemo(() => getApiBaseUrl() || "", []);

  const fetchHistory = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/benchmark/coding/list?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data.runs || []);
      }
    } catch (e) {
      console.error("Failed to fetch coding benchmark history", e);
    } finally {
      setLoading(false);
    }
  }, [apiBase]);

  useEffect(() => {
    fetchHistory();
  }, [currentRun, fetchHistory]);

  const handleDelete = async (id: string) => {
    if (confirm(t("benchmark.coding.results.confirmDelete"))) {
      const success = await onDelete(id);
      if (success) fetchHistory();
    }
  };

  const handleClearAll = async () => {
    if (confirm(t("benchmark.coding.results.confirmClearAll"))) {
      const success = await onClearAll();
      if (success) fetchHistory();
    }
  };

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return "-";
    return new Date(iso).toLocaleString("pl-PL", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const resolveStatusDot = (status: string) => {
    if (status === "completed") return "bg-emerald-500";
    if (status === "failed") return "bg-rose-500";
    if (status === "running") return "bg-amber-400 animate-pulse";
    return "bg-zinc-500";
  };

  return (
    <div className="space-y-6">
      {/* Bieżący run – szczegóły jobów */}
      {currentRun?.jobs?.length ? (
        <div className="space-y-3">
          <h4 className="heading-h4 text-[color:var(--text-heading)]">
            {currentRun.run_id.slice(0, 8)}...
          </h4>
          <JobsTable jobs={currentRun.jobs} />
        </div>
      ) : null}

      {/* Historia */}
      <div className="space-y-3 pt-6 border-t border-[color:var(--ui-border)]">
        <div className="flex items-center justify-between">
          <h4 className="heading-h4 text-[color:var(--text-heading)]">
            {t("benchmark.coding.results.title")}
          </h4>
          <div className="flex gap-2">
            <button
              onClick={fetchHistory}
              className="p-2 rounded-lg hover:bg-[color:var(--ui-surface-hover)] text-[color:var(--ui-muted)] hover:text-[color:var(--text-primary)] transition-colors"
              title={t("benchmark.coding.results.refresh")}
            >
              <RefreshCw className={cn("w-4 h-4", loading && "animate-spin")} />
            </button>
            {history.length > 0 && (
              <button
                onClick={handleClearAll}
                className="p-2 rounded-lg hover:bg-rose-500/20 text-rose-400 hover:text-rose-300 transition-colors flex items-center gap-2 text-xs font-medium"
              >
                <Trash2 className="w-4 h-4" />
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
          <div className="grid gap-4">
            {history.map((item) => (
              <div
                key={item.run_id}
                className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--surface-muted)] p-4 relative group"
              >
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={cn("w-2 h-2 rounded-full", resolveStatusDot(item.status))} />
                      <span className="font-mono text-xs text-[color:var(--ui-muted)]">
                        {item.run_id.slice(0, 8)}
                      </span>
                      <span className="text-xs text-[color:var(--text-secondary)] flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {formatDate(item.created_at)}
                      </span>
                    </div>
                    <div className="text-sm font-medium text-[color:var(--text-primary)]">
                      {t("benchmark.coding.results.models")}: {item.config.models.join(", ")}
                    </div>
                    <div className="text-xs text-[color:var(--text-secondary)]">
                      {t("benchmark.coding.results.tasks")}: {item.config.tasks.join(", ")}
                    </div>
                    {item.summary && (
                      <div className="text-xs text-[color:var(--ui-muted)] mt-1">
                        {item.summary.completed}/{item.summary.total_jobs} •{" "}
                        <span
                          className={cn(
                            "font-medium",
                            item.summary.success_rate >= 80
                              ? "text-emerald-400"
                              : "text-amber-400",
                          )}
                        >
                          {item.summary.success_rate.toFixed(1)}%
                        </span>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => handleDelete(item.run_id)}
                    className="opacity-0 group-hover:opacity-100 p-2 text-[color:var(--ui-muted)] hover:text-rose-400 transition-all"
                    title={t("benchmark.coding.results.deleteRun")}
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function JobsTable({ jobs }: Readonly<{ jobs: ReadonlyArray<CodingJob> }>) {
  return (
    <div className="overflow-x-auto rounded-xl bg-[color:var(--surface-muted)] border border-[color:var(--ui-border)]">
      <table className="w-full text-left text-xs">
        <thead>
          <tr className="border-b border-[color:var(--ui-border)] text-[color:var(--text-secondary)]">
            <th className="py-2 px-3 font-medium">Model</th>
            <th className="py-2 px-3 font-medium">Task</th>
            <th className="py-2 px-3 font-medium">Mode</th>
            <th className="py-2 px-3 text-center font-medium">Status</th>
            <th className="py-2 px-3 text-right font-medium">Time (s)</th>
            <th className="py-2 px-3 text-center font-medium">Result</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--ui-border)]">
          {jobs.map((job) => (
            <tr key={job.id}>
              <td className="py-2 px-3 font-medium text-[color:var(--text-primary)]">
                {job.model}
              </td>
              <td className="py-2 px-3 text-[color:var(--text-secondary)]">{job.task}</td>
              <td className="py-2 px-3 text-[color:var(--ui-muted)]">{job.mode}</td>
              <td className="py-2 px-3 text-center">
                <JobStatusBadge status={job.status} />
              </td>
              <td className="py-2 px-3 text-right text-[color:var(--ui-muted)]">
                {job.coding_seconds != null ? job.coding_seconds.toFixed(1) : "-"}
              </td>
              <td className="py-2 px-3 text-center">
                {job.passed === true && (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 mx-auto" />
                )}
                {job.passed === false && (
                  <XCircle className="w-3.5 h-3.5 text-rose-400 mx-auto" />
                )}
                {job.passed == null && job.status === "running" ? (
                  <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin mx-auto" />
                ) : job.passed == null ? (
                  <span className="text-[color:var(--ui-muted)]">-</span>
                ) : null}
              </td>
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

"use client";

import { useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import type { BenchmarkLog, CodingBenchmarkRun } from "@/lib/types";
import { useLanguage, useTranslation } from "@/lib/i18n";

const LEVEL_ICONS = {
  error: "❌",
  warning: "⚠️",
  info: "ℹ️",
} as const;

function getLevelColor(level: BenchmarkLog["level"]): string {
  if (level === "error") return "text-rose-400";
  if (level === "warning") return "text-amber-400";
  return "text-emerald-400";
}

function getLevelIcon(level: BenchmarkLog["level"]): string {
  return LEVEL_ICONS[level] ?? LEVEL_ICONS.info;
}

interface BenchmarkCodingConsoleProps {
  readonly logs: ReadonlyArray<BenchmarkLog>;
  readonly run: CodingBenchmarkRun | null;
  readonly isRunning?: boolean;
}

export function BenchmarkCodingConsole({
  logs,
  run,
  isRunning = false,
}: BenchmarkCodingConsoleProps) {
  const t = useTranslation();
  const { language } = useLanguage();
  const consoleRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (consoleRef.current) {
      consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
    }
  }, [logs]);

  const summary = run?.summary ?? null;
  const totalJobs = summary?.total_jobs ?? 0;
  const finishedJobs =
    (summary?.completed ?? 0) + (summary?.failed ?? 0) + (summary?.skipped ?? 0);
  const progressPct = totalJobs > 0 ? Math.round((finishedJobs / totalJobs) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="heading-h4 text-zinc-300">{t("benchmark.coding.console.title")}</h4>
        {isRunning && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
            <span className="text-xs text-emerald-400">{t("benchmark.coding.console.running")}</span>
          </div>
        )}
      </div>

      {/* Progress bar (shown when run is active and has jobs) */}
      {totalJobs > 0 && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-[color:var(--ui-muted)]">
            <span>
              {t("benchmark.coding.console.progressLabel", {
                completed: finishedJobs,
                total: totalJobs,
              })}
            </span>
            <span>{progressPct}%</span>
          </div>
          <div className="h-1.5 rounded-full bg-[color:var(--ui-border)] overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                progressPct === 100 ? "bg-emerald-500" : "bg-violet-500",
              )}
              style={{ width: `${progressPct}%` }}
            />
          </div>
        </div>
      )}

      <div
        ref={consoleRef}
        className="h-64 overflow-y-auto rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--terminal)] text-[color:var(--text-primary)] p-4 font-mono text-xs"
      >
        {logs.length === 0 ? (
          <p className="text-[color:var(--ui-muted)]">
            {t("benchmark.coding.console.empty")}
          </p>
        ) : (
          <div className="space-y-1">
            {logs.map((log) => (
              <div
                key={`${log.timestamp}-${log.level}-${log.message}`}
                className="flex gap-2"
              >
                <span className="text-hint">
                  {new Date(log.timestamp).toLocaleTimeString(language)}
                </span>
                <span className={getLevelColor(log.level)}>{getLevelIcon(log.level)}</span>
                <span className={cn("flex-1", getLevelColor(log.level))}>{log.message}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

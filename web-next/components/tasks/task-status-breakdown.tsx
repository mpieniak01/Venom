"use client";

import type { ReactNode } from "react";
import { statusTone, type StatusTone } from "@/lib/status";

type StatusEntry = Readonly<{
  label: string;
  value: number;
  hint?: string;
  tone?: StatusTone;
  icon?: ReactNode;
}>;

type TaskStatusBreakdownProps = Readonly<{
  title?: string;
  datasetLabel?: string;
  totalLabel?: string;
  totalValue?: string | number;
  entries: ReadonlyArray<StatusEntry>;
  emptyMessage?: string;
}>;

export function TaskStatusBreakdown({
  title = "Task status",
  datasetLabel,
  totalLabel = "Zadania",
  totalValue,
  entries,
  emptyMessage = "Brak danych do analizy.",
}: TaskStatusBreakdownProps) {
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  const safeEntries = entries.map((entry) => ({
    ...entry,
    tone: entry.tone ?? statusTone(entry.label),
  }));

  return (
    <div className="card-shell card-base p-4 text-sm">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">{title}</p>
          {datasetLabel && <p className="text-hint">{datasetLabel}</p>}
        </div>
        {totalValue !== undefined && (
          <div className="text-right">
            <p className="text-caption">
              {totalLabel}
            </p>
            <p className="text-xl font-semibold text-white">{totalValue}</p>
          </div>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {safeEntries.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
            {emptyMessage}
          </p>
        ) : (
          safeEntries.map((entry) => {
            const percent = total > 0 ? Math.round((entry.value / total) * 100) : 0;
            return (
              <div key={entry.label} className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2 text-zinc-400">
                    {entry.icon}
                    <span className="uppercase tracking-[0.25em]">{entry.label}</span>
                  </div>
                  <span className="font-semibold text-white">
                    {entry.value} <span className="text-hint">{percent}%</span>
                  </span>
                </div>
                <div className="h-2 rounded-full bg-black/40">
                  <div
                    className={`h-full rounded-full ${toneGradient(entry.tone ?? "neutral")}`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
                {entry.hint && <p className="text-hint">{entry.hint}</p>}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function toneGradient(tone: StatusTone) {
  switch (tone) {
    case "success":
      return "bg-gradient-to-r from-emerald-400/80 via-emerald-500/50 to-emerald-500/20";
    case "warning":
      return "bg-gradient-to-r from-amber-300/80 via-amber-400/50 to-amber-400/20";
    case "danger":
      return "bg-gradient-to-r from-rose-400/80 via-rose-500/50 to-rose-500/20";
    default:
      return "bg-gradient-to-r from-zinc-400/60 to-zinc-500/20";
  }
}

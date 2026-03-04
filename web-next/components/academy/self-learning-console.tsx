"use client";

import { useMemo } from "react";

import type { SelfLearningStatus } from "@/lib/academy-api";
import { useTranslation } from "@/lib/i18n";

interface Props {
  readonly logs: readonly string[];
  readonly status: SelfLearningStatus;
}

const STATUS_BADGE_CLASS: Record<SelfLearningStatus, string> = {
  pending: "text-amber-300 bg-amber-500/10",
  running: "text-blue-300 bg-blue-500/10",
  completed: "text-emerald-300 bg-emerald-500/10",
  completed_with_warnings: "text-yellow-300 bg-yellow-500/10",
  failed: "text-red-300 bg-red-500/10",
};

export function SelfLearningConsole({ logs, status }: Props) {
  const t = useTranslation();

  const statusLabel = useMemo(() => {
    const map: Record<SelfLearningStatus, string> = {
      pending: t("academy.selfLearning.status.pending"),
      running: t("academy.selfLearning.status.running"),
      completed: t("academy.selfLearning.status.completed"),
      completed_with_warnings: t("academy.selfLearning.status.completedWithWarnings"),
      failed: t("academy.selfLearning.status.failed"),
    };
    return map[status];
  }, [status, t]);

  return (
    <div className="space-y-3 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-[color:var(--text-heading)]">
            {t("academy.selfLearning.console.title")}
          </h3>
          <p className="text-sm text-hint">{t("academy.selfLearning.console.description")}</p>
        </div>
        <span
          className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${STATUS_BADGE_CLASS[status]}`}
        >
          {statusLabel}
        </span>
      </div>

      <div className="max-h-80 overflow-y-auto rounded-lg border border-[color:var(--ui-border)] bg-black/30 p-3 font-mono text-xs text-zinc-200">
        {logs.length === 0 ? (
          <p className="text-zinc-400">{t("academy.selfLearning.console.empty")}</p>
        ) : (
          <ul className="space-y-1">
            {logs.map((line, index) => (
              <li key={`${index}-${line.slice(0, 24)}`} className="whitespace-pre-wrap break-words">
                {line}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

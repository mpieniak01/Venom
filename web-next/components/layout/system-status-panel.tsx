"use client";

import { useMemo } from "react";
import { useActiveLlmServer, useQueueStatus } from "@/hooks/use-api";
import { useTranslation } from "@/lib/i18n";

type StatusTone = "success" | "warning" | "danger" | "neutral";

type StatusRow = {
  id: string;
  label: string;
  hint: string;
  tone: StatusTone;
};

export function SystemStatusPanel() {
  const { data: queue, error: queueError } = useQueueStatus(10000);
  const { data: llmActive, error: llmError } = useActiveLlmServer(10000);
  const t = useTranslation();

  const statuses: StatusRow[] = useMemo(() => {
    const hasQueue = Boolean(queue);
    let apiTone: StatusTone = "warning";
    if (hasQueue) {
      apiTone = "success";
    } else if (queueError) {
      apiTone = "danger";
    }

    let queueTone: StatusTone = "neutral";
    if (hasQueue) {
      queueTone = queue?.paused ? "warning" : "success";
    }

    const hasLlm = Boolean(llmActive?.active_server || llmActive?.active_model);
    let llmTone: StatusTone = "warning";
    if (hasLlm) {
      llmTone = "success";
    } else if (llmError) {
      llmTone = "danger";
    }
    const llmHint = hasLlm
      ? t("systemStatus.hints.llmDetails", {
        server: llmActive?.active_server ?? "unknown",
        model: llmActive?.active_model ?? "unknown",
      })
      : llmError ?? t("systemStatus.hints.llmNone");

    return [
      {
        id: "api",
        label: t("systemStatus.api"),
        hint: hasQueue ? "/api/v1/*" : queueError ?? t("systemStatus.hints.waiting"),
        tone: apiTone,
      },
      {
        id: "queue",
        label: t("systemStatus.queue"),
        hint: hasQueue
          ? t("systemStatus.hints.queueDetails", { active: queue?.active ?? 0, pending: queue?.pending ?? 0 })
          : t("systemStatus.hints.queueEmpty"),
        tone: queueTone,
      },
      {
        id: "llm",
        label: t("systemStatus.llm"),
        hint: llmHint,
        tone: llmTone,
      },
    ];
  }, [llmActive, llmError, queue, queueError, t]);

  const toneClassName = (tone: StatusTone) => {
    if (tone === "success") return "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.6)]";
    if (tone === "warning") return "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.6)]";
    return "bg-rose-500 shadow-[0_0_10px_rgba(244,63,94,0.6)]";
  };

  return (
    <div className="surface-card p-4 text-sm text-[color:var(--text-primary)]" data-testid="system-status-panel">
      <p className="eyebrow">{t("systemStatus.title")}</p>
      <div className="mt-3 space-y-3">
        {statuses.map((status) => (
          <div
            key={status.id}
            className="flex items-start justify-between gap-3"
            data-testid={`system-status-${status.id}`}
          >
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide">{status.label}</p>
              <p className="text-hint">{status.hint}</p>
            </div>
            <span
              className={[
                "mt-1 h-2.5 w-2.5 rounded-full",
                toneClassName(status.tone),
              ].join(" ")}
              aria-hidden="true"
            />
          </div>
        ))}
      </div>
      {queueError && (
        <p className="mt-3 text-xs text-amber-300" data-testid="system-status-error">
          {queueError}
        </p>
      )}
    </div>
  );
}

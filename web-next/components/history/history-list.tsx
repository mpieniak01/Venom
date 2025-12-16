"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import type { HistoryRequest } from "@/lib/types";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/date";
import { History as HistoryIcon } from "lucide-react";

type HistoryListProps = {
  entries?: HistoryRequest[] | null;
  limit?: number;
  selectedId?: string | null;
  onSelect?: (entry: HistoryRequest) => void;
  emptyTitle?: string;
  emptyDescription?: string;
  variant?: "preview" | "full";
  viewAllHref?: string;
};

export function HistoryList({
  entries,
  limit,
  selectedId,
  onSelect,
  emptyTitle = "Brak historii",
  emptyDescription = "Historia requestów pojawi się po wysłaniu zadań.",
  variant = "full",
  viewAllHref,
}: HistoryListProps) {
  const prepared = useMemo(() => {
    const source = entries || [];
    if (limit && limit > 0) {
      return source.slice(0, limit);
    }
    return source;
  }, [entries, limit]);

  const remaining =
    entries && limit && limit > 0 && entries.length > limit
      ? entries.length - limit
      : 0;

  if (!prepared.length) {
    return (
      <EmptyState
        icon={<HistoryIcon className="h-5 w-5" />}
        title={emptyTitle}
        description={emptyDescription}
        className={cn(
          "rounded-3xl border px-4 py-6",
          variant === "preview"
            ? "border-emerald-400/20 bg-gradient-to-br from-emerald-500/5 via-black/20 to-transparent"
            : "border-white/10 bg-black/30",
        )}
      />
    );
  }

  return (
    <div
      className={cn(
        "rounded-3xl border p-4",
        variant === "preview"
          ? "border-emerald-400/20 bg-gradient-to-b from-emerald-500/5 via-black/30 to-transparent"
          : "border-white/10 bg-black/30",
      )}
    >
      <div className="space-y-2">
        {prepared.map((item) => {
          const isSelected = selectedId === item.request_id;
          return (
            <button
              key={item.request_id}
              type="button"
              onClick={() => onSelect?.(item)}
              className={cn(
                "w-full rounded-2xl border px-4 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400/60",
                variant === "preview"
                  ? "bg-black/30 hover:bg-black/50"
                  : "bg-zinc-950/40 hover:bg-zinc-900/60",
                isSelected
                  ? "border-emerald-400/60 shadow-[0_0_20px_rgba(0,255,157,0.15)]"
                  : "border-white/5",
              )}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-xs uppercase tracking-[0.3em] text-emerald-200/70">
                      {formatRelativeTime(item.created_at)}
                    </p>
                    <p className="mt-1 font-mono text-sm text-white">
                      #{item.request_id.slice(0, 10)}
                    </p>
                    <p className="mt-1 text-[11px] uppercase tracking-[0.2em] text-zinc-500">
                      {formatHistoryModel(item)}
                    </p>
                  </div>
                  <Badge tone={historyStatusTone(item.status)}>
                    {item.status ?? "UNKNOWN"}
                  </Badge>
                </div>
              <p className="mt-2 line-clamp-2 text-sm text-zinc-300">
                {item.prompt?.trim() ? item.prompt : "Brak promptu."}
              </p>
            </button>
          );
        })}
      </div>
      {remaining > 0 && viewAllHref && (
        <Link
          href={viewAllHref}
          className="mt-4 flex items-center justify-between rounded-2xl border border-emerald-400/30 bg-emerald-500/5 px-3 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-emerald-200 transition hover:border-emerald-400/60"
        >
          <span>+{remaining} w Inspectorze</span>
          <span className="text-[11px]">Zobacz wszystko ↗</span>
        </Link>
      )}
    </div>
  );
}

function historyStatusTone(status?: string | null) {
  if (!status) return "neutral" as const;
  const normalized = status.toUpperCase();
  if (normalized === "COMPLETED") return "success" as const;
  if (normalized === "FAILED") return "danger" as const;
  if (normalized === "PROCESSING") return "warning" as const;
  return "neutral" as const;
}

function formatHistoryModel(entry: HistoryRequest): string {
  const model = entry.llm_model ?? entry.model ?? "LLM";
  const provider = entry.llm_provider ?? "local";
  if (entry.llm_endpoint) {
    return `${model} • ${provider} @ ${entry.llm_endpoint}`;
  }
  return `${model} • ${provider}`;
}

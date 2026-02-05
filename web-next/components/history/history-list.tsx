"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

export function selectHistoryWindow(
  entries: HistoryRequest[] | null | undefined,
  limit?: number,
) {
  const source = entries || [];
  if (limit && limit > 0) {
    return source.slice(-limit);
  }
  return source;
}

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
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  const prepared = useMemo(() => {
    return selectHistoryWindow(entries, limit);
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
          "rounded-3xl px-4 py-6",
          variant === "preview"
            ? "card-shell bg-gradient-to-br from-emerald-500/5 via-black/20 to-transparent"
            : "box-muted",
        )}
      />
    );
  }

  return (
    <div
      className={cn(
        "rounded-3xl p-4",
        variant === "preview"
          ? "card-shell bg-gradient-to-b from-emerald-500/5 via-black/30 to-transparent"
          : "box-muted",
      )}
    >
      <div className="space-y-2">
        {prepared.map((item) => {
          const isSelected = selectedId === item.request_id;
          return (
            <Button
              key={item.request_id}
              type="button"
              onClick={() => onSelect?.(item)}
              variant="ghost"
              size="sm"
              className={cn(
                "flex w-full flex-col items-start gap-2 rounded-2xl border px-4 py-3 text-left transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-400/60",
                variant === "preview"
                  ? "bg-black/30 hover:bg-black/50"
                  : "bg-zinc-950/40 hover:bg-zinc-900/60",
                isSelected
                  ? "border-emerald-400/60 shadow-[0_0_20px_rgba(0,255,157,0.15)]"
                  : "border-white/5",
              )}
            >
              <div className="flex w-full flex-wrap items-center justify-between gap-3 text-xs uppercase tracking-[0.3em] text-emerald-200/70">
                <span>
                  {mounted ? formatRelativeTime(item.created_at) : item.created_at}
                </span>
                <span className="font-mono tracking-normal text-white">
                  #{item.request_id.slice(0, 10)}
                </span>
              </div>
              <p className="text-sm text-zinc-300">
                {item.prompt?.trim() ? item.prompt : "Brak promptu."}
              </p>
              <p className="text-caption text-zinc-400">
                {formatHistoryModel(item)}
              </p>
              {item.error_code && (
                <div className="flex w-full justify-end">
                  <Badge tone="danger" className="max-w-full truncate">
                    {item.error_code}
                  </Badge>
                </div>
              )}
              {item.error_code && (
                <p className="mt-2 text-caption text-rose-300">
                  {formatErrorDetail(item)}
                </p>
              )}
            </Button>
          );
        })}
      </div>
      {remaining > 0 && viewAllHref && (
        <Link
          href={viewAllHref}
          className="mt-4 flex items-center justify-between rounded-2xl border border-emerald-400/30 bg-emerald-500/5 px-3 py-2 text-xs font-semibold uppercase tracking-[0.3em] text-emerald-200 transition hover:border-emerald-400/60"
        >
          <span>+{remaining} w Inspectorze</span>
          <span className="text-hint">Zobacz wszystko ↗</span>
        </Link>
      )}
    </div>
  );
}

function formatHistoryModel(entry: HistoryRequest): string {
  const model = entry.llm_model ?? entry.model ?? "LLM";
  const provider = entry.llm_provider ?? "local";
  return `${model} • ${provider}`;
}

function formatErrorDetail(entry: HistoryRequest): string {
  const details = entry.error_details;
  if (!details || typeof details !== "object") return "error";
  const missing = details["missing"];
  if (Array.isArray(missing) && missing.length > 0) {
    return `missing: ${missing[0]}`;
  }
  const expectedHash = details["expected_hash"];
  const actualHash = details["actual_hash"];
  if (typeof expectedHash === "string" && typeof actualHash === "string") {
    return `expected_hash: ${expectedHash.slice(0, 8)}`;
  }
  const stage = details["stage"];
  if (typeof stage === "string") {
    return `stage: ${stage}`;
  }
  return "error";
}

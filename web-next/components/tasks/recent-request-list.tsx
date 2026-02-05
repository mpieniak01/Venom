"use client";

import type { HistoryRequest } from "@/lib/types";
import { statusTone } from "@/lib/status";
import { Badge } from "@/components/ui/badge";

type RecentRequestListProps = {
  requests?: HistoryRequest[] | null;
  limit?: number;
  emptyMessage?: string;
};

export function RecentRequestList({
  requests,
  limit = 5,
  emptyMessage = "Brak historii do analizy.",
}: RecentRequestListProps) {
  const items = (requests || []).slice(-limit);

  return (
    <div className="card-shell card-base p-4 text-sm">
      <p className="text-caption">Ostatnie requesty</p>
      {items.length === 0 ? (
        <p className="mt-3 rounded-2xl border border-dashed border-white/10 bg-black/20 px-3 py-2 text-hint">
          {emptyMessage}
        </p>
      ) : (
        <ul className="mt-3 space-y-3 text-xs text-zinc-300">
          {items.map((item) => (
            <li
              key={`recent-${item.request_id}`}
              className="rounded-2xl box-muted px-3 py-2"
            >
              <div className="flex items-center justify-between gap-3 text-caption">
                <span>{item.finished_at ? new Date(item.finished_at).toLocaleTimeString() : "—"}</span>
                <Badge tone={statusTone(item.status)}>{item.status}</Badge>
              </div>
              <p className="mt-1 text-white">{item.prompt}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

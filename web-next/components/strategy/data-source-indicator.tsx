"use client";

import { Badge } from "@/components/ui/badge";
import { formatRelativeTime } from "@/lib/date";
import { cn } from "@/lib/utils";

type DataSourceStatus = "live" | "cache" | "stale" | "offline";

type DataSourceIndicatorProps = {
  status: DataSourceStatus;
  timestamp?: number | null;
  className?: string;
};

const statusConfig: Record<DataSourceStatus, { label: string; tone: "success" | "warning" | "danger" | "neutral"; icon: string }> = {
  live: { label: "Live", tone: "success", icon: "🟢" },
  cache: { label: "Cache", tone: "warning", icon: "💾" },
  stale: { label: "Stare dane", tone: "danger", icon: "⚠️" },
  offline: { label: "Offline", tone: "danger", icon: "🔴" },
};

export function DataSourceIndicator({
  status,
  timestamp,
  className,
}: DataSourceIndicatorProps) {
  const config = statusConfig[status];

  const timestampText = timestamp
    ? formatRelativeTime(new Date(timestamp).toISOString())
    : null;

  return (
    <div className={cn("flex items-center gap-2 text-xs", className)}>
      <Badge tone={config.tone}>
        <span aria-hidden>{config.icon}</span>
        {config.label}
      </Badge>
      {timestampText && (
        <span className="text-hint">{timestampText}</span>
      )}
    </div>
  );
}

export function calculateDataSourceStatus(
  hasLiveData: boolean,
  hasCachedData: boolean,
  timestamp: number | null,
  staleThresholdMs: number,
): DataSourceStatus {
  if (hasLiveData) return "live";
  if (!hasCachedData) return "offline";
  if (timestamp && Date.now() - timestamp > staleThresholdMs) return "stale";
  return "cache";
}

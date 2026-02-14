/**
 * Provider status component - displays connection status for a provider
 */

import React from "react";
import { ConnectionStatus } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

interface ProviderStatusIndicatorProps {
  status: ConnectionStatus;
  message?: string | null;
  latency_ms?: number | null;
}

const statusColors: Record<ConnectionStatus, string> = {
  connected: "bg-green-500",
  degraded: "bg-yellow-500",
  offline: "bg-red-500",
  unknown: "bg-gray-400",
};

export function ProviderStatusIndicator({
  status,
  message,
  latency_ms,
}: ProviderStatusIndicatorProps) {
  const { t } = useTranslation();
  
  return (
    <div className="flex items-center gap-2">
      <div className={`h-2 w-2 rounded-full ${statusColors[status]}`} />
      <span className="text-sm text-gray-700 dark:text-gray-300">
        {t(`providers.status.${status}`)}
      </span>
      {latency_ms !== null && latency_ms !== undefined && status === "connected" && (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          ({Math.round(latency_ms)}ms)
        </span>
      )}
      {message && status !== "connected" && (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {message}
        </span>
      )}
    </div>
  );
}

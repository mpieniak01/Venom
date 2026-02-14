/**
 * Provider alerts list component - displays active alerts with filtering
 */

"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n";

interface Alert {
  id: string;
  severity: "info" | "warning" | "critical";
  alert_type: string;
  provider: string;
  message: string;
  technical_details: string | null;
  timestamp: string;
  expires_at: string | null;
  metadata: Record<string, any>;
}

interface AlertsListProps {
  alerts: Alert[];
  providerFilter?: string;
  severityFilter?: "info" | "warning" | "critical";
}

export function AlertsList({ alerts, providerFilter, severityFilter }: AlertsListProps) {
  const { t } = useTranslation();

  // Filter alerts
  let filteredAlerts = alerts;
  if (providerFilter) {
    filteredAlerts = filteredAlerts.filter((a) => a.provider === providerFilter);
  }
  if (severityFilter) {
    filteredAlerts = filteredAlerts.filter((a) => a.severity === severityFilter);
  }

  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case "critical":
        return "border-red-500/30 bg-red-500/10 text-red-400";
      case "warning":
        return "border-yellow-500/30 bg-yellow-500/10 text-yellow-400";
      case "info":
        return "border-blue-500/30 bg-blue-500/10 text-blue-400";
      default:
        return "border-zinc-500/30 bg-zinc-500/10 text-zinc-400";
    }
  };

  const getSeverityIcon = (severity: string): string => {
    switch (severity) {
      case "critical":
        return "🔴";
      case "warning":
        return "⚠️";
      case "info":
        return "ℹ️";
      default:
        return "•";
    }
  };

  const formatTimestamp = (timestamp: string): string => {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  };

  const formatAlertMessage = (alert: Alert): string => {
    const messageKey = alert.message;
    
    // Try to translate with metadata substitution
    try {
      return t(messageKey, alert.metadata);
    } catch {
      // Fallback to technical details if translation fails
      return alert.technical_details || messageKey;
    }
  };

  if (filteredAlerts.length === 0) {
    return (
      <div className="card-shell card-base p-5 text-center">
        <p className="text-zinc-400">{t("providers.alerts.noAlerts")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {filteredAlerts.map((alert) => (
        <div
          key={alert.id}
          className={`rounded-2xl border p-4 ${getSeverityColor(alert.severity)}`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="text-lg">{getSeverityIcon(alert.severity)}</span>
                <span className="text-xs font-semibold uppercase tracking-wider">
                  {t(`providers.alerts.severity.${alert.severity}`)}
                </span>
                <span className="text-xs text-zinc-500">•</span>
                <span className="text-xs text-zinc-400">{alert.provider}</span>
              </div>
              <p className="text-sm font-medium mb-1">
                {t(`providers.alerts.types.${alert.alert_type}`, alert.alert_type)}
              </p>
              <p className="text-sm opacity-90">
                {formatAlertMessage(alert)}
              </p>
              {alert.technical_details && (
                <p className="text-xs text-zinc-500 mt-2 font-mono">
                  {alert.technical_details}
                </p>
              )}
            </div>
            <div className="text-right text-xs text-zinc-500 whitespace-nowrap">
              {formatTimestamp(alert.timestamp)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

interface AlertsSummaryProps {
  summary: {
    total_active: number;
    by_severity: {
      info: number;
      warning: number;
      critical: number;
    };
    by_provider: Record<string, number>;
  };
}

export function AlertsSummary({ summary }: AlertsSummaryProps) {
  const { t } = useTranslation();

  return (
    <div className="card-shell card-base p-5">
      <p className="text-xs uppercase tracking-[0.35em] text-zinc-500 mb-4">
        {t("providers.alerts.title")}
      </p>
      
      <div className="grid grid-cols-4 gap-3 mb-4">
        <div className="rounded-2xl box-subtle px-3 py-2 text-center">
          <p className="text-xs text-zinc-400">Total</p>
          <p className="text-2xl font-semibold">{summary.total_active}</p>
        </div>
        <div className="rounded-2xl box-subtle px-3 py-2 text-center">
          <p className="text-xs text-blue-400">Info</p>
          <p className="text-2xl font-semibold text-blue-400">{summary.by_severity.info}</p>
        </div>
        <div className="rounded-2xl box-subtle px-3 py-2 text-center">
          <p className="text-xs text-yellow-400">Warning</p>
          <p className="text-2xl font-semibold text-yellow-400">{summary.by_severity.warning}</p>
        </div>
        <div className="rounded-2xl box-subtle px-3 py-2 text-center">
          <p className="text-xs text-red-400">Critical</p>
          <p className="text-2xl font-semibold text-red-400">{summary.by_severity.critical}</p>
        </div>
      </div>

      {Object.keys(summary.by_provider).length > 0 && (
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">By Provider</p>
          {Object.entries(summary.by_provider).map(([provider, count]) => (
            <div key={provider} className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
              <span className="text-xs text-zinc-400">{provider}</span>
              <span className="text-sm font-semibold">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

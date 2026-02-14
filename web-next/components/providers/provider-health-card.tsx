/**
 * Provider health card component - displays SLO status and health score
 */

"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n";

interface ProviderHealth {
  health_status: "healthy" | "degraded" | "critical" | "unknown";
  health_score: number;
  availability: number;
  latency_p99_ms: number | null;
  error_rate: number;
  cost_usage_usd: number;
  slo_target: {
    availability_target: number;
    latency_p99_ms: number;
    error_rate_target: number;
    cost_budget_usd: number;
  };
  slo_breaches: string[];
}

interface ProviderHealthCardProps {
  provider: string;
  health: ProviderHealth | null;
}

export function ProviderHealthCard({ provider, health }: ProviderHealthCardProps) {
  const { t } = useTranslation();

  if (!health) {
    return (
      <div className="card-shell card-base p-5 text-sm">
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
          {t("providers.health.status.unknown")}
        </p>
        <p className="mt-4 text-center text-zinc-400">
          {t("providers.metrics.noData")}
        </p>
      </div>
    );
  }

  const getHealthColor = (status: string): string => {
    switch (status) {
      case "healthy":
        return "text-emerald-400";
      case "degraded":
        return "text-yellow-400";
      case "critical":
        return "text-red-400";
      default:
        return "text-zinc-400";
    }
  };

  const getHealthBgColor = (status: string): string => {
    switch (status) {
      case "healthy":
        return "from-emerald-500/20 to-emerald-600/20";
      case "degraded":
        return "from-yellow-500/20 to-yellow-600/20";
      case "critical":
        return "from-red-500/20 to-red-600/20";
      default:
        return "from-zinc-500/20 to-zinc-600/20";
    }
  };

  const getScoreColor = (score: number): string => {
    if (score >= 80) return "text-emerald-400";
    if (score >= 50) return "text-yellow-400";
    return "text-red-400";
  };

  return (
    <div className="card-shell card-base p-5 text-sm space-y-4">
      <div>
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
          {t("providers.metrics.healthScore")} - {provider}
        </p>
      </div>

      {/* Health status and score */}
      <div className={`rounded-2xl bg-gradient-to-br ${getHealthBgColor(health.health_status)} p-4`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-400">
              {t("providers.health.status.healthy")}
            </p>
            <p className={`text-3xl font-semibold ${getHealthColor(health.health_status)}`}>
              {t(`providers.health.status.${health.health_status}`)}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-400">
              {t("providers.metrics.healthScore")}
            </p>
            <p className={`text-3xl font-semibold ${getScoreColor(health.health_score)}`}>
              {health.health_score.toFixed(0)}/100
            </p>
          </div>
        </div>
      </div>

      {/* Current metrics vs SLO targets */}
      <div className="space-y-2">
        <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
          <span className="text-xs text-zinc-400">{t("providers.metrics.availability")}</span>
          <span className="text-sm font-semibold">
            {(health.availability * 100).toFixed(2)}% / {(health.slo_target.availability_target * 100).toFixed(2)}%
          </span>
        </div>
        {health.latency_p99_ms !== null && (
          <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
            <span className="text-xs text-zinc-400">{t("providers.metrics.latency.p99")}</span>
            <span className="text-sm font-semibold">
              {health.latency_p99_ms.toFixed(0)}ms / {health.slo_target.latency_p99_ms.toFixed(0)}ms
            </span>
          </div>
        )}
        <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
          <span className="text-xs text-zinc-400">{t("providers.metrics.errorRate")}</span>
          <span className="text-sm font-semibold">
            {(health.error_rate * 100).toFixed(2)}% / {(health.slo_target.error_rate_target * 100).toFixed(2)}%
          </span>
        </div>
        {health.slo_target.cost_budget_usd > 0 && (
          <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
            <span className="text-xs text-zinc-400">{t("providers.metrics.totalCost")}</span>
            <span className="text-sm font-semibold">
              ${health.cost_usage_usd.toFixed(2)} / ${health.slo_target.cost_budget_usd.toFixed(2)}
            </span>
          </div>
        )}
      </div>

      {/* SLO breaches */}
      {health.slo_breaches.length > 0 ? (
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500 mb-2">
            {t("providers.health.sloBreaches")}
          </p>
          <div className="space-y-1">
            {health.slo_breaches.map((breach, idx) => (
              <div key={idx} className="rounded-2xl bg-red-500/10 border border-red-500/20 px-3 py-2">
                <p className="text-xs text-red-400">{breach}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-2xl bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-center">
          <p className="text-xs text-emerald-400">{t("providers.health.noBreaches")}</p>
        </div>
      )}
    </div>
  );
}

/**
 * Provider metrics card component - displays performance metrics for a provider
 */

"use client";

import React from "react";
import { useTranslation } from "@/lib/i18n";

interface ProviderMetrics {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  error_rate: number;
  latency: {
    p50_ms: number | null;
    p95_ms: number | null;
    p99_ms: number | null;
    samples: number;
  };
  errors: {
    total: number;
    timeouts: number;
    auth_errors: number;
    budget_errors: number;
    by_code: Record<string, number>;
  };
  cost: {
    total_usd: number;
    total_tokens: number;
  };
}

interface ProviderMetricsCardProps {
  provider: string;
  metrics: ProviderMetrics | null;
}

export function ProviderMetricsCard({ provider, metrics }: Readonly<ProviderMetricsCardProps>) {
  const t = useTranslation();

  if (!metrics) {
    return (
      <div className="card-shell card-base p-5 text-sm">
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
          {t("providers.metrics.title")}
        </p>
        <p className="mt-4 text-center text-zinc-400">
          {t("providers.metrics.noData")}
        </p>
      </div>
    );
  }

  const formatLatency = (ms: number | null): string => {
    if (ms === null) return "—";
    return `${ms.toFixed(0)}ms`;
  };

  return (
    <div className="card-shell card-base p-5 text-sm space-y-4">
      <div>
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
          {t("providers.metrics.title")} - {provider}
        </p>
      </div>

      {/* Key metrics row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-2xl box-subtle px-3 py-2">
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
            {t("providers.metrics.totalRequests")}
          </p>
          <p className="text-2xl font-semibold">{metrics.total_requests.toLocaleString()}</p>
        </div>
        <div className="rounded-2xl box-subtle px-3 py-2">
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
            {t("providers.metrics.successRate")}
          </p>
          <p className="text-2xl font-semibold">{metrics.success_rate.toFixed(1)}%</p>
        </div>
      </div>

      {/* Latency metrics */}
      <div>
        <p className="text-xs uppercase tracking-[0.35em] text-zinc-500 mb-2">
          {t("providers.metrics.latency.p50")}
        </p>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-2xl box-subtle px-3 py-2 text-center">
            <p className="text-xs text-zinc-400">{t("providers.metrics.latency.p50Label")}</p>
            <p className="text-lg font-semibold">{formatLatency(metrics.latency.p50_ms)}</p>
          </div>
          <div className="rounded-2xl box-subtle px-3 py-2 text-center">
            <p className="text-xs text-zinc-400">{t("providers.metrics.latency.p95Label")}</p>
            <p className="text-lg font-semibold">{formatLatency(metrics.latency.p95_ms)}</p>
          </div>
          <div className="rounded-2xl box-subtle px-3 py-2 text-center">
            <p className="text-xs text-zinc-400">{t("providers.metrics.latency.p99Label")}</p>
            <p className="text-lg font-semibold">{formatLatency(metrics.latency.p99_ms)}</p>
          </div>
        </div>
      </div>

      {/* Cost and tokens */}
      {metrics.cost.total_usd > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-2xl box-subtle px-3 py-2">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              {t("providers.metrics.totalCost")}
            </p>
            <p className="text-2xl font-semibold">${metrics.cost.total_usd.toFixed(4)}</p>
          </div>
          <div className="rounded-2xl box-subtle px-3 py-2">
            <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
              {t("providers.metrics.totalTokens")}
            </p>
            <p className="text-2xl font-semibold">{metrics.cost.total_tokens.toLocaleString()}</p>
          </div>
        </div>
      )}

      {/* Error breakdown */}
      {metrics.errors.total > 0 && (
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500 mb-2">
            {t("providers.metrics.errorRate")}
          </p>
          <div className="space-y-2">
            <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
              <span className="text-xs text-zinc-400">{t("providers.metrics.errors.total")}</span>
              <span className="text-sm font-semibold text-red-400">{metrics.errors.total}</span>
            </div>
            {metrics.errors.timeouts > 0 && (
              <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
                <span className="text-xs text-zinc-400">{t("providers.metrics.errors.timeouts")}</span>
                <span className="text-sm font-semibold">{metrics.errors.timeouts}</span>
              </div>
            )}
            {metrics.errors.auth_errors > 0 && (
              <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
                <span className="text-xs text-zinc-400">{t("providers.metrics.errors.authErrors")}</span>
                <span className="text-sm font-semibold">{metrics.errors.auth_errors}</span>
              </div>
            )}
            {metrics.errors.budget_errors > 0 && (
              <div className="flex items-center justify-between rounded-2xl box-subtle px-3 py-2">
                <span className="text-xs text-zinc-400">{t("providers.metrics.errors.budgetErrors")}</span>
                <span className="text-sm font-semibold">{metrics.errors.budget_errors}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

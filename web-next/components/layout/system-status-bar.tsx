"use client";

import { useMemo } from "react";
import {
  useGitStatus,
  useModelsUsage,
  useTokenMetrics,
} from "@/hooks/use-api";
import { formatGbPair, formatPercentMetric, formatUsd, formatVramMetric } from "@/lib/formatters";
import { useTranslation } from "@/lib/i18n";
import { useAppMeta } from "@/lib/app-meta";
import { cn } from "@/lib/utils";

export function SystemStatusBar() {
  const { data: usageResponse } = useModelsUsage(10000);
  const usage = usageResponse?.usage;
  const { data: tokenMetrics } = useTokenMetrics(15000);
  const { data: gitStatus } = useGitStatus(10000);
  const appMeta = useAppMeta();
  const t = useTranslation();

  const costValue = formatUsd(tokenMetrics?.session_cost_usd);
  const gpuValue =
    usage?.gpu_usage_percent !== undefined
      ? formatPercentMetric(usage.gpu_usage_percent)
      : usage?.vram_usage_mb && usage.vram_usage_mb > 0
        ? t("statusBar.labels.gpuActive")
        : "—";

  const resourceItems = useMemo(
    () => [
      { key: "cpu", label: t("statusBar.labels.cpu"), value: formatPercentMetric(usage?.cpu_usage_percent) },
      { key: "gpu", label: t("statusBar.labels.gpu"), value: gpuValue },
      {
        key: "ram",
        label: t("statusBar.labels.ram"),
        value: formatGbPair(usage?.memory_used_gb, usage?.memory_total_gb),
      },
      {
        key: "vram",
        label: t("statusBar.labels.vram"),
        value: formatVramMetric(usage?.vram_usage_mb, usage?.vram_total_mb),
      },
      {
        key: "disk",
        label: t("statusBar.labels.disk"),
        value:
          usage?.disk_usage_percent !== undefined
            ? formatPercentMetric(usage.disk_usage_percent)
            : "—",
      },
      {
        key: "cost",
        label: t("statusBar.labels.cost"),
        value: costValue,
      },
    ],
    [
      costValue,
      gpuValue,
      t,
      usage?.cpu_usage_percent,
      usage?.disk_usage_percent,
      usage?.memory_total_gb,
      usage?.memory_used_gb,
      usage?.vram_total_mb,
      usage?.vram_usage_mb,
    ],
  );

  const versionText = appMeta?.commit ?? appMeta?.version ?? t("statusBar.versionUnknown");
  const repoText = gitStatus
    ? gitStatus.dirty
      ? t("statusBar.repoDirty")
      : t("statusBar.repoClean")
    : t("statusBar.repoUnknown");
  const repoTone = cn(
    "font-semibold",
    gitStatus
      ? gitStatus.dirty
        ? "text-amber-300"
        : "text-emerald-300"
      : "text-zinc-400",
  );
  const repoTitle = gitStatus?.changes || gitStatus?.status || undefined;

  return (
    <div
      data-testid="bottom-status-bar"
      className="pointer-events-none absolute inset-x-0 bottom-6 z-30 px-4 sm:px-10 lg:pl-72"
    >
      <div className="pointer-events-auto w-full border border-white/15 bg-black/75 px-5 py-4 text-xs text-left shadow-2xl shadow-emerald-900/40 backdrop-blur-2xl">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-zinc-300"
            data-testid="status-bar-resources"
          >
            <span className="font-semibold text-white">{t("statusBar.resourcesLabel")}:</span>
            {resourceItems.map((item) => (
              <span key={item.key} className="flex items-center gap-1">
                <span className="text-zinc-400">{item.label}</span>
                <span className="text-white">{item.value}</span>
              </span>
            ))}
          </div>
          <div
            className="flex flex-wrap items-center gap-2 text-sm text-zinc-300 lg:justify-end lg:text-right"
            aria-live="polite"
          >
            <span>{t("statusBar.versionLabel")}:</span>
            <span data-testid="status-bar-version" className="font-semibold text-white">
              {versionText}
            </span>
            <span className="text-zinc-600">•</span>
            <span>{t("statusBar.repoLabel")}:</span>
            <span data-testid="status-bar-repo" className={repoTone} title={repoTitle}>
              {repoText}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

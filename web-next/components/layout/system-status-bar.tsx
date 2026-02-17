"use client";

import { useMemo } from "react";
import { useGitStatus, useModelsUsage, useTokenMetrics } from "@/hooks/use-api";
import {
  formatDiskSnapshot,
  formatGbPair,
  formatPercentMetric,
  formatUsd,
  formatVramMetric,
} from "@/lib/formatters";
import { useTranslation } from "@/lib/i18n";
import { useAppMeta } from "@/lib/app-meta";
import { cn } from "@/lib/utils";
import type { GitStatus, ModelsUsageResponse, TokenMetrics } from "@/lib/types";

type SystemStatusInitialData = {
  modelsUsage?: ModelsUsageResponse | null;
  tokenMetrics?: TokenMetrics | null;
  gitStatus?: GitStatus | null;
};

export function SystemStatusBar({ initialData }: Readonly<{ initialData?: SystemStatusInitialData }>) {
  const { data: usageResponse } = useModelsUsage(30000);
  const usage = usageResponse?.usage ?? initialData?.modelsUsage?.usage;
  const { data: liveTokenMetrics } = useTokenMetrics(30000);
  const {
    data: liveGitStatus,
    loading: gitLoadingLive,
  } = useGitStatus();
  const tokenMetrics = liveTokenMetrics ?? initialData?.tokenMetrics ?? null;
  const gitStatus = liveGitStatus ?? initialData?.gitStatus ?? null;
  const gitLoading = gitLoadingLive && !liveGitStatus;
  const appMeta = useAppMeta();
  const t = useTranslation();

  const costValue = formatUsd(tokenMetrics?.session_cost_usd);
  let gpuValue = "—";
  if (usage?.gpu_usage_percent !== undefined) {
    gpuValue = formatPercentMetric(usage.gpu_usage_percent);
  } else if (usage?.vram_usage_mb && usage.vram_usage_mb > 0) {
    gpuValue = t("statusBar.labels.gpuActive");
  }

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
        value: (() => {
          if (usage?.disk_system_usage_percent !== undefined) {
            return formatDiskSnapshot(usage?.disk_system_used_gb, usage?.disk_system_total_gb);
          }
          if (usage?.disk_usage_percent !== undefined) {
            return formatDiskSnapshot(usage?.disk_usage_gb, usage?.disk_limit_gb);
          }
          return "—";
        })(),
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
      usage?.disk_system_usage_percent,
      usage?.disk_system_total_gb,
      usage?.disk_system_used_gb,
      usage?.disk_usage_gb,
      usage?.disk_limit_gb,
      usage?.disk_usage_percent,
      usage?.memory_total_gb,
      usage?.memory_used_gb,
      usage?.vram_total_mb,
      usage?.vram_usage_mb,
    ],
  );

  const versionDisplay = formatVersionDisplay(appMeta?.version) ?? t("statusBar.versionUnknown");
  const repoState = resolveRepoStatus(gitStatus, gitLoading, appMeta?.commit, t);
  const repoTone = cn("font-medium", repoState.tone);
  const repoTitle = repoState.title;

  return (
    <div
      data-testid="bottom-status-bar"
      className="pointer-events-none absolute inset-x-0 bottom-6 z-30 px-4 sm:px-8 lg:px-10 lg:pl-[calc(var(--sidebar-width)+2.5rem)] xl:px-12 xl:pl-[calc(var(--sidebar-width)+3rem)]"
    >
      <div className="pointer-events-auto mr-auto w-full max-w-[1320px] xl:max-w-[1536px] 2xl:max-w-[85vw] border border-white/15 bg-black/75 px-5 py-4 text-xs text-left shadow-2xl shadow-emerald-900/40 backdrop-blur-2xl">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 text-hint"
            data-testid="status-bar-resources"
          >
            <span className="font-semibold text-white" suppressHydrationWarning>{t("statusBar.resourcesLabel")}:</span>
            {resourceItems.map((item) => (
              <span key={item.key} className="flex items-center gap-1">
                <span className="text-zinc-400" suppressHydrationWarning>{item.label}</span>
                <span className="text-white">{item.value}</span>
              </span>
            ))}
          </div>
          <div className="flex flex-col items-start gap-0.5 text-sm text-zinc-300 lg:items-end lg:text-right" aria-live="polite">
            <div className="flex items-center gap-2">
              <span suppressHydrationWarning>{t("statusBar.versionLabel")}:</span>
              <span data-testid="status-bar-version" className="font-semibold text-white" suppressHydrationWarning>
                {versionDisplay}
              </span>
            </div>
            <div className="flex max-w-full items-center gap-1.5 text-[11px] text-zinc-400">
              <span suppressHydrationWarning>{t("statusBar.repoLabel")}:</span>
              <span
                data-testid="status-bar-repo"
                className={cn(repoTone, "max-w-[52vw] cursor-help truncate lg:max-w-[36vw]")}
                title={repoTitle}
                suppressHydrationWarning
              >
                {gitLoading ? (
                  <span className="text-emerald-300/80">…</span>
                ) : (
                  repoState.text
                )}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

type RepoStatusTone = Record<string, boolean>;
type RepoStatus = {
  text: string;
  tone: RepoStatusTone;
  title?: string;
};

function getRepoStatusTitle(gitStatus: GitStatus): string | undefined {
  return gitStatus.status_output || gitStatus.changes || gitStatus.status || undefined;
}

function resolveRepoBaseText(
  compareStatus: string | undefined,
  hasChanges: boolean,
  t: ReturnType<typeof useTranslation>,
): string {
  if (!compareStatus) {
    return hasChanges ? t("statusBar.repoDirty") : t("statusBar.repoClean");
  }
  const compareTextMap: Record<string, string> = {
    ahead: t("statusBar.repoAhead"),
    behind: t("statusBar.repoBehind"),
    diverged: t("statusBar.repoDiverged"),
    equal: t("statusBar.repoEqual"),
    no_remote: t("statusBar.repoNoRemote"),
    no_remote_main: t("statusBar.repoNoRemoteMain"),
    no_local_main: t("statusBar.repoNoLocalMain"),
  };
  return compareTextMap[compareStatus] || t("statusBar.repoUnknown");
}

function resolveRepoTone(compareStatus: string | undefined, hasChanges: boolean): RepoStatusTone {
  const isBehindOrDiverged = compareStatus === "behind" || compareStatus === "diverged";
  const isNeedsAttention =
    hasChanges ||
    compareStatus === "ahead" ||
    compareStatus === "no_remote" ||
    compareStatus === "no_remote_main" ||
    compareStatus === "no_local_main";
  const isClean = (!compareStatus && !hasChanges) || (compareStatus === "equal" && !hasChanges);
  return {
    "text-zinc-400": false,
    "text-rose-300/80": isBehindOrDiverged,
    "text-amber-300/75": isNeedsAttention,
    "text-emerald-300/75": isClean,
  };
}

function resolveRepoStatus(
  gitStatus: GitStatus | null,
  gitLoading: boolean,
  commit: string | undefined,
  t: ReturnType<typeof useTranslation>,
): RepoStatus {
  if (!gitStatus) {
    return {
      text: gitLoading ? t("statusBar.versionLoading") : t("statusBar.repoUnavailable"),
      tone: { "text-zinc-400": true },
      title: undefined,
    };
  }

  if (gitStatus.is_git_repo === false) {
    return {
      text: t("statusBar.repoNotGit"),
      tone: { "text-zinc-400": true },
      title: getRepoStatusTitle(gitStatus),
    };
  }

  const hasChanges = gitStatus.has_changes ?? gitStatus.dirty ?? false;
  const compareStatus = gitStatus.compare_status;
  const baseText = resolveRepoBaseText(compareStatus, hasChanges, t);
  const branch = gitStatus.branch?.trim() || "unknown";
  const commitShort = commit?.trim() || "unknown";
  const identityText = `${branch}@${commitShort}`;

  const text = hasChanges ? `${identityText} ${t("statusBar.repoDirtySuffix")}` : identityText;
  const tone = resolveRepoTone(compareStatus, hasChanges);
  const statusTitle = getRepoStatusTitle(gitStatus);
  const title = statusTitle ? `${baseText}\n${statusTitle}` : baseText;

  return {
    text,
    tone,
    title,
  };
}

function formatVersionDisplay(version: string | undefined): string | null {
  if (!version) return null;
  const match = version.trim().match(/^(\d+)\.(\d+)\.(\d+)$/);
  if (!match) return version.trim();
  const [, major, minor, patch] = match;
  if (patch === "0") {
    return `${major}.${minor}`;
  }
  return `${major}.${minor}.${patch}`;
}

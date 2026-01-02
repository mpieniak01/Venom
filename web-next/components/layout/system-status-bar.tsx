"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useGitStatus, useModelsUsage, useTokenMetrics } from "@/hooks/use-api";
import {
  formatDiskSnapshot,
  formatGbPair,
  formatPercentMetric,
  formatUsd,
  formatVramMetric,
} from "@/lib/formatters";
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { useAppMeta } from "@/lib/app-meta";
import { cn } from "@/lib/utils";
import type { GitStatus, ModelsUsageResponse, TokenMetrics } from "@/lib/types";

type SystemStatusInitialData = {
  modelsUsage?: ModelsUsageResponse | null;
  tokenMetrics?: TokenMetrics | null;
  gitStatus?: GitStatus | null;
};

export function SystemStatusBar({ initialData }: { initialData?: SystemStatusInitialData }) {
  const { data: usageResponse } = useModelsUsage(10000);
  const usage = usageResponse?.usage ?? initialData?.modelsUsage?.usage;
  const { data: liveTokenMetrics } = useTokenMetrics(15000);
  const {
    data: liveGitStatus,
    loading: gitLoadingLive,
  } = useGitStatus();
  const tokenMetrics = liveTokenMetrics ?? initialData?.tokenMetrics ?? null;
  const gitStatus = liveGitStatus ?? initialData?.gitStatus ?? null;
  const gitLoading = gitLoadingLive && !liveGitStatus;
  const appMeta = useAppMeta();
  const t = useTranslation();
  const commitValue = appMeta?.commit ?? null;
  const [commitCopied, setCommitCopied] = useState(false);
  const commitResetRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCommitCopy = useCallback(async () => {
    if (!commitValue) return;

    const markCopied = () => {
      setCommitCopied(true);
      if (commitResetRef.current) {
        clearTimeout(commitResetRef.current);
      }
      commitResetRef.current = setTimeout(() => setCommitCopied(false), 1500);
    };

    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(commitValue);
        markCopied();
        return;
      } catch {
        // Fallback below.
      }
    }

    try {
      const textarea = document.createElement("textarea");
      textarea.value = commitValue;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "absolute";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      markCopied();
    } catch {
      setCommitCopied(false);
    }
  }, [commitValue]);

  useEffect(() => {
    return () => {
      if (commitResetRef.current) {
        clearTimeout(commitResetRef.current);
      }
    };
  }, []);

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
          usage?.disk_system_usage_percent !== undefined
            ? formatDiskSnapshot(usage?.disk_system_used_gb, usage?.disk_system_total_gb)
            : usage?.disk_usage_percent !== undefined
              ? formatDiskSnapshot(usage?.disk_usage_gb, usage?.disk_limit_gb)
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

  const versionText = appMeta?.commit ?? appMeta?.version ?? t("statusBar.versionUnknown");
  const versionDisplay = commitCopied ? t("statusBar.commitCopied") : versionText;
  const repoState = resolveRepoStatus(gitStatus, gitLoading, t);
  const repoTone = cn("font-semibold", repoState.tone);
  const repoTitle = repoState.title;

  return (
    <div
      data-testid="bottom-status-bar"
      className="pointer-events-none absolute inset-x-0 bottom-6 z-30 px-4 sm:px-8 lg:px-10 lg:pl-[calc(18rem+2.5rem)] xl:px-12 xl:pl-[calc(18rem+3rem)]"
    >
      <div className="pointer-events-auto mr-auto w-full max-w-[1320px] 2xl:max-w-[68vw] border border-white/15 bg-black/75 px-5 py-4 text-xs text-left shadow-2xl shadow-emerald-900/40 backdrop-blur-2xl">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div
            className="flex flex-wrap items-center gap-x-4 gap-y-1 text-hint"
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
            {commitValue ? (
              <Button
                type="button"
                data-testid="status-bar-version"
                variant="ghost"
                size="xs"
                className="px-0 py-0 text-xs font-semibold text-white"
                title={commitCopied ? t("statusBar.commitCopied") : t("statusBar.commitCopy")}
                onClick={handleCommitCopy}
              >
                {versionDisplay}
              </Button>
            ) : (
              <span data-testid="status-bar-version" className="font-semibold text-white">
                {versionDisplay}
              </span>
            )}
            <span className="text-zinc-600">•</span>
            <span>{t("statusBar.repoLabel")}:</span>
            <span
              data-testid="status-bar-repo"
              className={cn(repoTone, "cursor-help")}
              title={repoTitle}
            >
              {gitLoading ? (
                <span className="text-emerald-300">…</span>
              ) : (
                repoState.text
              )}
            </span>
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

function resolveRepoStatus(
  gitStatus: GitStatus | null,
  gitLoading: boolean,
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
      title: gitStatus.status_output || gitStatus.changes || gitStatus.status || undefined,
    };
  }

  const hasChanges = gitStatus.has_changes ?? gitStatus.dirty ?? false;
  const compareStatus = gitStatus.compare_status;
  let baseText = t("statusBar.repoUnknown");
  if (!compareStatus) {
    baseText = hasChanges ? t("statusBar.repoDirty") : t("statusBar.repoClean");
  } else if (compareStatus === "ahead") {
    baseText = t("statusBar.repoAhead");
  } else if (compareStatus === "behind") {
    baseText = t("statusBar.repoBehind");
  } else if (compareStatus === "diverged") {
    baseText = t("statusBar.repoDiverged");
  } else if (compareStatus === "equal") {
    baseText = t("statusBar.repoEqual");
  } else if (compareStatus === "no_remote") {
    baseText = t("statusBar.repoNoRemote");
  } else if (compareStatus === "no_remote_main") {
    baseText = t("statusBar.repoNoRemoteMain");
  } else if (compareStatus === "no_local_main") {
    baseText = t("statusBar.repoNoLocalMain");
  }

  const text = hasChanges ? `${baseText} ${t("statusBar.repoDirtySuffix")}` : baseText;
  const tone = {
    "text-zinc-400": false,
    "text-rose-300": compareStatus === "behind" || compareStatus === "diverged",
    "text-amber-300":
      hasChanges ||
      compareStatus === "ahead" ||
      compareStatus === "no_remote" ||
      compareStatus === "no_remote_main" ||
      compareStatus === "no_local_main",
    "text-emerald-300":
      (!compareStatus && !hasChanges) || (compareStatus === "equal" && !hasChanges),
  };

  return {
    text,
    tone,
    title: gitStatus.status_output || gitStatus.changes || gitStatus.status || undefined,
  };
}

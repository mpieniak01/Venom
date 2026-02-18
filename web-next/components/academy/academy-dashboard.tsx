"use client";

import { useState, useEffect } from "react";
import { GraduationCap, Database, Zap, Server, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { cn } from "@/lib/utils";
import { AcademyOverview } from "./academy-overview";
import { DatasetPanel } from "./dataset-panel";
import { TrainingPanel } from "./training-panel";
import { AdaptersPanel } from "./adapters-panel";
import { getAcademyStatus, type AcademyStatus } from "@/lib/academy-api";
import { useTranslation } from "@/lib/i18n";

export function AcademyDashboard() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<"overview" | "dataset" | "training" | "adapters">("overview");
  const [status, setStatus] = useState<AcademyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  async function loadStatus() {
    try {
      setLoading(true);
      setError(null);
      const data = await getAcademyStatus();
      setStatus(data);
    } catch (err) {
      console.error("Failed to load Academy status:", err);
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  }

  if (!loading && (error || !status)) {
    return (
      <div className="space-y-6">
        <SectionHeading
          eyebrow={t("academy.dashboard.eyebrow")}
          title={t("academy.dashboard.title")}
          description={t("academy.dashboard.description")}
          as="h1"
          size="lg"
          rightSlot={<GraduationCap className="page-heading-icon" />}
        />
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
          <p className="text-sm text-red-300">
            ❌ {t("academy.dashboard.unavailable")} {error || t("academy.common.unknownError")}
          </p>
          <p className="mt-2 text-xs text-zinc-400">
            {t("academy.dashboard.unavailableHint")}
          </p>
          <Button
            onClick={loadStatus}
            variant="outline"
            size="sm"
            className="mt-4"
          >
            {t("academy.common.retry")}
          </Button>
        </div>
      </div>
    );
  }

  if (!loading && status && !status.enabled) {
    return (
      <div className="space-y-6">
        <SectionHeading
          eyebrow={t("academy.dashboard.eyebrow")}
          title={t("academy.dashboard.title")}
          description={t("academy.dashboard.description")}
          as="h1"
          size="lg"
          rightSlot={<GraduationCap className="page-heading-icon" />}
        />
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-6">
          <p className="text-sm text-yellow-300">
            ⚠️ {t("academy.dashboard.disabled")}
          </p>
          <p className="mt-2 text-xs text-zinc-400">
            {t("academy.dashboard.disabledHint")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <SectionHeading
        eyebrow={t("academy.dashboard.eyebrow")}
        title={t("academy.dashboard.title")}
        description={t("academy.dashboard.description")}
        as="h1"
        size="lg"
        rightSlot={<GraduationCap className="page-heading-icon" />}
      />

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10">
        <Button
          onClick={() => setActiveTab("overview")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "overview"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Server className="h-4 w-4" />
          {t("academy.dashboard.tabs.overview")}
        </Button>
        <Button
          onClick={() => setActiveTab("dataset")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "dataset"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Database className="h-4 w-4" />
          {t("academy.dashboard.tabs.dataset")}
        </Button>
        <Button
          onClick={() => setActiveTab("training")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "training"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Play className="h-4 w-4" />
          {t("academy.dashboard.tabs.training")}
        </Button>
        <Button
          onClick={() => setActiveTab("adapters")}
          variant="ghost"
          size="sm"
          className={cn(
            "gap-2 rounded-t-xl rounded-b-none px-4 py-3 text-sm font-medium",
            activeTab === "adapters"
              ? "border-b-2 border-emerald-400 bg-emerald-500/10 text-emerald-300"
              : "text-zinc-400 hover:bg-white/5 hover:text-zinc-200"
          )}
        >
          <Zap className="h-4 w-4" />
          {t("academy.dashboard.tabs.adapters")}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {loading && (
          <div className="space-y-4 rounded-xl border border-white/10 bg-black/20 p-6">
            <p className="text-sm text-zinc-400">{t("academy.common.loadingAcademy")}</p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="h-24 rounded-lg bg-white/5 animate-pulse" />
              <div className="h-24 rounded-lg bg-white/5 animate-pulse" />
              <div className="h-24 rounded-lg bg-white/5 animate-pulse" />
              <div className="h-24 rounded-lg bg-white/5 animate-pulse" />
            </div>
          </div>
        )}
        {!loading && status && activeTab === "overview" && <AcademyOverview status={status} onRefresh={loadStatus} />}
        {!loading && status && activeTab === "dataset" && <DatasetPanel />}
        {!loading && status && activeTab === "training" && <TrainingPanel />}
        {!loading && status && activeTab === "adapters" && <AdaptersPanel />}
      </div>
    </div>
  );
}

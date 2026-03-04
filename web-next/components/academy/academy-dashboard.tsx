"use client";

import { useState, useEffect } from "react";
import {
  GraduationCap,
  Database,
  Zap,
  Server,
  Play,
  ArrowRightLeft,
  BrainCircuit,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionHeading } from "@/components/ui/section-heading";
import { THEME_TAB_BAR_CLASS, getThemeTabClass } from "@/lib/theme-ui";
import { cn } from "@/lib/utils";
import { AcademyOverview } from "./academy-overview";
import { DatasetPanel } from "./dataset-panel";
import { DatasetConversionPanel } from "./dataset-conversion-panel";
import { TrainingPanel } from "./training-panel";
import { AdaptersPanel } from "./adapters-panel";
import { SelfLearningPanel } from "./self-learning-panel";
import { getAcademyStatus, type AcademyStatus } from "@/lib/academy-api";
import { useTranslation } from "@/lib/i18n";

export function AcademyDashboard() {
  const t = useTranslation();
  const [activeTab, setActiveTab] = useState<
    "overview" | "dataset" | "conversion" | "training" | "adapters" | "selfLearning"
  >("overview");
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
          <p className="text-sm font-medium text-[color:var(--text-heading)]">
            ❌ {t("academy.dashboard.unavailable")} {error || t("academy.common.unknownError")}
          </p>
          <p className="mt-2 text-xs text-[color:var(--ui-muted)]">
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
          <p className="text-sm font-medium text-[color:var(--text-heading)]">
            ⚠️ {t("academy.dashboard.disabled")}
          </p>
          <p className="mt-2 text-xs text-[color:var(--ui-muted)]">
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
      <div className={THEME_TAB_BAR_CLASS}>
        <Button
          onClick={() => setActiveTab("overview")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "overview"))}
        >
          <Server className="h-4 w-4" />
          {t("academy.dashboard.tabs.overview")}
        </Button>
        <Button
          onClick={() => setActiveTab("conversion")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "conversion"))}
        >
          <ArrowRightLeft className="h-4 w-4" />
          {t("academy.dashboard.tabs.conversion")}
        </Button>
        <Button
          onClick={() => setActiveTab("dataset")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "dataset"))}
        >
          <Database className="h-4 w-4" />
          {t("academy.dashboard.tabs.dataset")}
        </Button>
        <Button
          onClick={() => setActiveTab("training")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "training"))}
        >
          <Play className="h-4 w-4" />
          {t("academy.dashboard.tabs.training")}
        </Button>
        <Button
          onClick={() => setActiveTab("selfLearning")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "selfLearning"))}
        >
          <BrainCircuit className="h-4 w-4" />
          {t("academy.dashboard.tabs.selfLearning")}
        </Button>
        <Button
          onClick={() => setActiveTab("adapters")}
          variant="ghost"
          size="sm"
          className={cn(getThemeTabClass(activeTab === "adapters"))}
        >
          <Zap className="h-4 w-4" />
          {t("academy.dashboard.tabs.adapters")}
        </Button>
      </div>

      {/* Content */}
      <div className="min-h-[500px]">
        {loading && (
          <div className="space-y-4 rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
            <p className="text-sm text-[color:var(--ui-muted)]">{t("academy.common.loadingAcademy")}</p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="h-24 rounded-lg bg-[color:var(--ui-surface-hover)] animate-pulse" />
              <div className="h-24 rounded-lg bg-[color:var(--ui-surface-hover)] animate-pulse" />
              <div className="h-24 rounded-lg bg-[color:var(--ui-surface-hover)] animate-pulse" />
              <div className="h-24 rounded-lg bg-[color:var(--ui-surface-hover)] animate-pulse" />
            </div>
          </div>
        )}
        {!loading && status && activeTab === "overview" && <AcademyOverview status={status} onRefresh={loadStatus} />}
        {!loading && status && activeTab === "conversion" && <DatasetConversionPanel />}
        {!loading && status && activeTab === "dataset" && <DatasetPanel />}
        {!loading && status && activeTab === "training" && <TrainingPanel />}
        {!loading && status && activeTab === "selfLearning" && <SelfLearningPanel />}
        {!loading && status && activeTab === "adapters" && <AdaptersPanel />}
      </div>
    </div>
  );
}

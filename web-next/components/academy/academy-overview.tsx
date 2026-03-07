"use client";

import { RefreshCw, CheckCircle2, XCircle, AlertCircle, Cpu, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AcademyStatus } from "@/lib/academy-api";
import { useTranslation } from "@/lib/i18n";

interface AcademyOverviewProps {
  readonly status: AcademyStatus;
  readonly onRefresh: () => void;
}

interface ComponentStatusProps {
  readonly name: string;
  readonly active: boolean;
}

const ComponentStatus = ({ name, active }: ComponentStatusProps) => (
  <div className="flex items-center gap-2 rounded-lg border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-3">
    {active ? (
      <CheckCircle2 className="h-4 w-4 text-emerald-400" />
    ) : (
      <XCircle className="h-4 w-4 text-red-400" />
    )}
    <span className="text-sm text-[color:var(--text-primary)]">{name}</span>
  </div>
);

interface StatCardProps {
  readonly label: string;
  readonly value: string | number;
  readonly icon: React.ElementType;
  readonly color?: "emerald" | "blue" | "yellow" | "red";
}

const StatCard = ({ label, value, icon: Icon, color = "emerald" }: StatCardProps) => {
  const colorClasses = {
    emerald: "border-[color:var(--stat-card-emerald-border)] bg-[color:var(--stat-card-emerald-bg)] text-[color:var(--stat-card-emerald-text)]",
    blue: "border-[color:var(--stat-card-blue-border)] bg-[color:var(--stat-card-blue-bg)] text-[color:var(--stat-card-blue-text)]",
    yellow: "border-[color:var(--stat-card-yellow-border)] bg-[color:var(--stat-card-yellow-bg)] text-[color:var(--stat-card-yellow-text)]",
    red: "border-[color:var(--stat-card-red-border)] bg-[color:var(--stat-card-red-bg)] text-[color:var(--stat-card-red-text)]",
  };

  return (
    <div className={`rounded-xl border p-4 ${colorClasses[color]}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs opacity-70">{label}</p>
          <p className="mt-1 text-2xl font-bold">{value}</p>
        </div>
        <Icon className="h-5 w-5 opacity-50" />
      </div>
    </div>
  );
};

export function AcademyOverview({ status, onRefresh }: AcademyOverviewProps) {
  const t = useTranslation();
  return (
    <div className="space-y-6">
      {/* Status nagłówek */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-[color:var(--text-heading)]">{t("academy.overview.title")}</h2>
          <p className="text-sm text-hint">{t("academy.overview.subtitle")}</p>
        </div>
        <Button onClick={onRefresh} variant="outline" size="sm" className="gap-2">
          <RefreshCw className="h-4 w-4" />
          {t("academy.common.refresh")}
        </Button>
      </div>

      {/* GPU Status */}
      <div className={`rounded-xl border p-4 ${status.gpu.available
        ? "border-emerald-500/20 bg-emerald-500/5"
        : "border-yellow-500/20 bg-yellow-500/5"
        }`}>
        <div className="flex items-center gap-3">
          <Cpu className={`h-6 w-6 ${status.gpu.available ? "text-emerald-400" : "text-yellow-400"
            }`} />
          <div>
            <p className="font-medium text-[color:var(--text-heading)]">
              {status.gpu.available
                ? t("academy.overview.gpuAvailable")
                : t("academy.overview.gpuUnavailable")}
            </p>
            <p className="text-sm text-hint">
              {status.gpu.enabled
                ? t("academy.overview.gpuEnabledHint")
                : t("academy.overview.gpuDisabledHint")}
            </p>
          </div>
        </div>
      </div>

      {/* Statystyki */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t("academy.overview.cards.lessonsStore")}
          value={status.lessons.total_lessons || 0}
          icon={Database}
          color="blue"
        />
        <StatCard
          label={t("academy.overview.cards.totalJobs")}
          value={status.jobs.total}
          icon={Database}
          color="emerald"
        />
        <StatCard
          label={t("academy.overview.cards.runningJobs")}
          value={status.jobs.running}
          icon={AlertCircle}
          color="yellow"
        />
        <StatCard
          label={t("academy.overview.cards.finishedJobs")}
          value={status.jobs.finished}
          icon={CheckCircle2}
          color="emerald"
        />
      </div>

      {/* Komponenty */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-[color:var(--text-secondary)]">{t("academy.overview.componentsTitle")}</h3>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-5">
          <ComponentStatus name="Professor" active={status.components.professor} />
          <ComponentStatus name="DatasetCurator" active={status.components.dataset_curator} />
          <ComponentStatus name="GPUHabitat" active={status.components.gpu_habitat} />
          <ComponentStatus name="LessonsStore" active={status.components.lessons_store} />
          <ComponentStatus name="ModelManager" active={status.components.model_manager} />
        </div>
      </div>

      {/* Konfiguracja */}
      <div className="rounded-xl border border-[color:var(--ui-border)] bg-[color:var(--ui-surface)] p-6">
        <h3 className="mb-4 text-sm font-medium text-[color:var(--text-secondary)]">{t("academy.overview.configTitle")}</h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <p className="text-xs text-hint">{t("academy.overview.minLessons")}</p>
            <p className="mt-1 text-lg font-semibold text-[color:var(--text-heading)]">{status.config.min_lessons}</p>
          </div>
          <div>
            <p className="text-xs text-hint">{t("academy.overview.trainingInterval")}</p>
            <p className="mt-1 text-lg font-semibold text-[color:var(--text-heading)]">{status.config.training_interval_hours}h</p>
          </div>
        </div>
      </div>

      {/* Ostrzeżenia */}
      {status.jobs.failed > 0 && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-red-400" />
            <p className="text-sm text-red-300">
              {t("academy.overview.failedJobs", { count: status.jobs.failed })}
            </p>
          </div>
        </div>
      )}

      {!status.gpu.available && status.gpu.enabled && (
        <div className="rounded-xl border border-yellow-500/20 bg-yellow-500/5 p-4">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-5 w-5 text-yellow-400" />
            <div>
              <p className="text-sm text-yellow-300">
                {t("academy.overview.gpuWarningTitle")}
              </p>
              <p className="mt-1 text-xs text-zinc-400">
                {t("academy.overview.gpuWarningHint")}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

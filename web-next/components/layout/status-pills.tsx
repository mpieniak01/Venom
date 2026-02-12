"use client";

import { useMemo } from "react";
import { useQueueStatus, useMetrics, useTasks } from "@/hooks/use-api";
import type { Metrics, QueueStatus, Task } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useTranslation } from "@/lib/i18n";

export type StatusPillsInitialData = {
  queue?: QueueStatus | null;
  metrics?: Metrics | null;
  tasks?: Task[] | null;
};

type PillTone = "success" | "warning" | "danger" | "neutral";

type StatusPill = {
  id: "queue" | "success" | "tasks";
  label: string;
  value: string | number;
  hint: string;
  tone: PillTone;
  loading: boolean;
};

const resolveQueueTone = (queueAvailable: boolean, paused?: boolean): PillTone => {
  if (!queueAvailable) return "neutral";
  return paused ? "warning" : "success";
};

const resolveSuccessTone = (metricsAvailable: boolean, successRate: number): PillTone => {
  if (!metricsAvailable) return "neutral";
  return successRate > 70 ? "success" : "danger";
};

const resolveTasksTone = (tasksAvailable: boolean, activeTasks: number): PillTone => {
  if (!tasksAvailable) return "neutral";
  return activeTasks > 0 ? "warning" : "neutral";
};

const resolvePillToneClass = (tone: PillTone): string => {
  if (tone === "success") return "status-pill--success";
  if (tone === "warning") return "status-pill--warning";
  if (tone === "danger") return "status-pill--danger";
  return "status-pill--neutral";
};

const resolvePillHint = (input: {
  loading: boolean;
  available: boolean;
  loadingText: string;
  availableText: string;
  fallbackText: string;
}) => {
  const { loading, available, loadingText, availableText, fallbackText } = input;
  if (loading) return loadingText;
  if (available) return availableText;
  return fallbackText;
};

function buildStatusPills(input: {
  t: (key: string) => string;
  queueAvailable: boolean;
  queueActive: number;
  queueLimit: number | string;
  queuePending: number;
  queuePaused?: boolean;
  queuePendingLoading: boolean;
  metricsAvailable: boolean;
  successRate: number;
  metricsPendingLoading: boolean;
  tasksAvailable: boolean;
  activeTasks: number;
  tasksPendingLoading: boolean;
}): StatusPill[] {
  const {
    t,
    queueAvailable,
    queueActive,
    queueLimit,
    queuePending,
    queuePaused,
    queuePendingLoading,
    metricsAvailable,
    successRate,
    metricsPendingLoading,
    tasksAvailable,
    activeTasks,
    tasksPendingLoading,
  } = input;

  return [
    {
      id: "queue",
      label: t("mobileNav.systemStatus.queue"),
      value: queueAvailable ? `${queueActive}/${queueLimit}` : "—",
      hint: resolvePillHint({
        loading: queuePendingLoading,
        available: queueAvailable,
        loadingText: t("mobileNav.systemStatus.loading"),
        availableText: `${queuePending} ${t("mobileNav.systemStatus.pending")}`,
        fallbackText: t("mobileNav.systemStatus.noData"),
      }),
      tone: resolveQueueTone(queueAvailable, queuePaused),
      loading: queuePendingLoading,
    },
    {
      id: "success",
      label: t("mobileNav.systemStatus.efficiency"),
      value: metricsAvailable ? `${successRate}%` : "—",
      hint: resolvePillHint({
        loading: metricsPendingLoading,
        available: metricsAvailable,
        loadingText: t("mobileNav.systemStatus.loading"),
        availableText: t("mobileNav.systemStatus.lastTasks"),
        fallbackText: t("mobileNav.systemStatus.offline"),
      }),
      tone: resolveSuccessTone(metricsAvailable, successRate),
      loading: metricsPendingLoading,
    },
    {
      id: "tasks",
      label: t("mobileNav.systemStatus.tasks"),
      value: tasksAvailable ? activeTasks : "—",
      hint: resolvePillHint({
        loading: tasksPendingLoading,
        available: tasksAvailable,
        loadingText: t("mobileNav.systemStatus.loading"),
        availableText: t("mobileNav.systemStatus.active"),
        fallbackText: t("mobileNav.systemStatus.noData"),
      }),
      tone: resolveTasksTone(tasksAvailable, activeTasks),
      loading: tasksPendingLoading,
    },
  ];
}

export function StatusPills({ initialData }: Readonly<{ initialData?: StatusPillsInitialData }>) {
  const { data: queue, loading: queueLoading } = useQueueStatus(10000);
  const { data: metrics, loading: metricsLoading } = useMetrics(15000);
  const { data: tasks, loading: tasksLoading } = useTasks(15000);

  const queueData = queue ?? initialData?.queue ?? null;
  const metricsData = metrics ?? initialData?.metrics ?? null;
  const tasksData = tasks ?? initialData?.tasks ?? null;

  const successRateRaw = metricsData?.tasks?.success_rate;
  const metricsAvailable = typeof successRateRaw === "number";
  const queueAvailable = Boolean(queueData);
  const tasksAvailable = Array.isArray(tasksData);
  const queuePendingLoading = queueLoading && !queueData;
  const metricsPendingLoading = metricsLoading && !metricsData;
  const tasksPendingLoading = tasksLoading && !tasksData;

  const successRate = successRateRaw ?? 0;
  const activeTasks = tasksData?.length ?? 0;
  const queueActive = queueData?.active ?? 0;
  const queuePending = queueData?.pending ?? 0;

  const t = useTranslation();

  const pills = useMemo(
    () =>
      buildStatusPills({
        t,
        queueAvailable,
        queueActive,
        queueLimit: queueData?.limit ?? "∞",
        queuePending,
        queuePaused: queueData?.paused,
        queuePendingLoading,
        metricsAvailable,
        successRate,
        metricsPendingLoading,
        tasksAvailable,
        activeTasks,
        tasksPendingLoading,
      }),
    [
      queueAvailable,
      queueActive,
      queuePending,
      queueData?.limit,
      queueData?.paused,
      metricsAvailable,
      successRate,
      tasksAvailable,
      activeTasks,
      queuePendingLoading,
      metricsPendingLoading,
      tasksPendingLoading,
      t,
    ],
  );

  return (
    <div className="hidden items-center gap-3 lg:flex">
      {pills.map((pill) => (
        <div
          key={pill.id}
          data-testid={`status-pill-${pill.id}`}
          className={cn("status-pill", resolvePillToneClass(pill.tone))}
        >
          <span className="status-pill-label" suppressHydrationWarning>{pill.label}</span>
          <span className="text-lg font-semibold" data-testid={`status-pill-${pill.id}-value`} suppressHydrationWarning>
            {pill.loading ? (
              <span className="text-sm" suppressHydrationWarning>{t("mobileNav.systemStatus.loading")}</span>
            ) : (
              pill.value
            )}
          </span>
          <span className="status-pill-hint" suppressHydrationWarning>{pill.hint}</span>
        </div>
      ))}
    </div>
  );
}

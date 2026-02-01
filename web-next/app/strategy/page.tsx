"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { MarkdownPreview } from "@/components/ui/markdown";
import { SectionHeading } from "@/components/ui/section-heading";
import {
  createRoadmap,
  requestRoadmapStatus,
  startCampaign,
  useHistory,
  useRoadmap,
  useTasks,
} from "@/hooks/use-api";
import { useTaskStream } from "@/hooks/use-task-stream";
import { NOTIFICATIONS } from "@/lib/ui-config";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Target } from "lucide-react";
import { statusTone } from "@/lib/status";
import { RoadmapKpiCard } from "@/components/strategy/roadmap-kpi-card";
import { DataSourceIndicator, calculateDataSourceStatus } from "@/components/strategy/data-source-indicator";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/date";
import type { RoadmapResponse, Task } from "@/lib/types";
import { useTranslation } from "@/lib/i18n";

const ROADMAP_CACHE_KEY = "strategy-roadmap-cache";
const REPORT_CACHE_KEY = "strategy-status-report";
const REPORT_TS_KEY = "strategy-status-report-ts";
const REPORT_STALE_MS = 60_000;
const ROADMAP_TS_KEY = "strategy-roadmap-ts";
const AUTO_REFRESH_DELAY_MS = 2000;

const safeParseJson = <T,>(payload: string | null): T | null => {
  if (!payload) return null;
  try {
    return JSON.parse(payload) as T;
  } catch {
    return null;
  }
};

const safeNumber = (payload: string | null): number | null => {
  if (!payload) return null;
  const parsed = Number(payload);
  return Number.isFinite(parsed) ? parsed : null;
};

export default function StrategyPage() {
  const t = useTranslation();
  const { data: liveRoadmap, refresh: refreshRoadmap, error: roadmapError } = useRoadmap();
  const { data: liveTasks, loading: liveTasksLoading } = useTasks();
  const { data: timelineHistory, loading: timelineLoading } = useHistory(10);
  const [cachedRoadmap, setCachedRoadmap] = useState<RoadmapResponse | null>(null);
  const [roadmapTimestamp, setRoadmapTimestamp] = useState<number | null>(null);
  const [visionInput, setVisionInput] = useState("");
  const [showVisionForm, setShowVisionForm] = useState(false);
  const [statusReport, setStatusReport] = useState<string | null>(null);
  const [reportTimestamp, setReportTimestamp] = useState<number | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [toast, setToast] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const showToast = useCallback(
    (tone: "success" | "error", message: string) => {
      setToast({ tone, message });
    },
    [],
  );
  const roadmapData = liveRoadmap ?? cachedRoadmap;
  const autoReportTriggered = useRef(false);
  const campaignRefreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setCachedRoadmap(
      safeParseJson<RoadmapResponse>(window.sessionStorage.getItem(ROADMAP_CACHE_KEY)),
    );
    setRoadmapTimestamp(safeNumber(window.sessionStorage.getItem(ROADMAP_TS_KEY)));
    setStatusReport(window.sessionStorage.getItem(REPORT_CACHE_KEY));
    setReportTimestamp(safeNumber(window.sessionStorage.getItem(REPORT_TS_KEY)));
  }, []);
  const persistStatusReport = useCallback((value: string) => {
    if (typeof window === "undefined") return;
    try {
      const timestamp = Date.now();
      window.sessionStorage.setItem(REPORT_CACHE_KEY, value);
      window.sessionStorage.setItem(REPORT_TS_KEY, timestamp.toString());
      setReportTimestamp(timestamp);
    } catch (err) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("[strategy] Nie udało się zapisać raportu statusu w sessionStorage", err);
      }
    }
  }, []);
  const fetchStatusReport = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!silent) {
        setReportLoading(true);
        setStatusReport(null);
      }
      try {
        const res = await requestRoadmapStatus();
        const reportText = res.report || "Brak danych z Executive.";
        setStatusReport(reportText);
        persistStatusReport(reportText);
        if (!silent) {
          showToast("success", "Pobrano raport statusu.");
        }
      } catch (err) {
        if (!silent) {
          const message =
            err instanceof Error ? err.message : t("strategy.messages.reportError");
          setStatusReport(message);
          showToast("error", message);
        }
      } finally {
        if (!silent) {
          setReportLoading(false);
        }
      }
    },
    [persistStatusReport, showToast, t],
  );

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), NOTIFICATIONS.STRATEGY_TOAST_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    if (!liveRoadmap) return;
    setCachedRoadmap(liveRoadmap);
    if (typeof window === "undefined") return;
    try {
      const timestamp = Date.now();
      window.sessionStorage.setItem(ROADMAP_CACHE_KEY, JSON.stringify(liveRoadmap));
      window.sessionStorage.setItem(ROADMAP_TS_KEY, timestamp.toString());
      setRoadmapTimestamp(timestamp);
    } catch (err) {
      if (process.env.NODE_ENV !== "production") {
        console.warn("[strategy] Nie udało się zapisać roadmapy w sessionStorage", err);
      }
    }
  }, [liveRoadmap]);

  useEffect(() => {
    if (autoReportTriggered.current) return;
    autoReportTriggered.current = true;
    const shouldRefresh =
      !reportTimestamp || Date.now() - reportTimestamp > REPORT_STALE_MS;
    if (shouldRefresh) {
      fetchStatusReport({ silent: true }).catch(() => undefined);
    }
  }, [fetchStatusReport, reportTimestamp]);

  useEffect(() => {
    return () => {
      if (campaignRefreshTimer.current) {
        clearTimeout(campaignRefreshTimer.current);
      }
    };
  }, []);

  const kpis = roadmapData?.kpis;
  const visionProgress = roadmapData?.vision?.progress ?? 0;
  const milestonesRaw =
    kpis && kpis.milestones_total
      ? ((kpis.milestones_completed ?? 0) / Math.max(kpis.milestones_total, 1)) * 100
      : 0;
  const tasksRaw =
    kpis && kpis.tasks_total
      ? ((kpis.tasks_completed ?? 0) / Math.max(kpis.tasks_total, 1)) * 100
      : 0;
  const milestones = useMemo(
    () => roadmapData?.milestones ?? [],
    [roadmapData?.milestones],
  );
  const timelineEntriesRaw = useMemo(
    () => (timelineHistory ?? []).slice(0, 8),
    [timelineHistory],
  );
  const trackedStrategyTaskIds = useMemo(() => {
    const ids = new Set<string>();
    (liveTasks ?? []).forEach((task) => {
      const identifier = task.task_id || task.id;
      if (!identifier) return;
      const normalized = (task.status || "").toUpperCase();
      if (["PENDING", "PROCESSING", "IN_PROGRESS", "RUNNING"].includes(normalized)) {
        ids.add(identifier);
      }
    });
    timelineEntriesRaw.forEach((entry) => {
      if (!entry.request_id) return;
      if (entry.status === "PENDING" || entry.status === "PROCESSING") {
        ids.add(entry.request_id);
      }
    });
    return Array.from(ids);
  }, [liveTasks, timelineEntriesRaw]);
  const { streams: strategyStreams } = useTaskStream(trackedStrategyTaskIds, {
    enabled: trackedStrategyTaskIds.length > 0,
  });
  const mergedLiveTasks = useMemo(() => {
    if (!liveTasks) return liveTasks;
    return liveTasks.map((task) => {
      const identifier = task.task_id || task.id;
      if (!identifier) return task;
      const stream = strategyStreams[identifier];
      if (stream?.status) {
        return { ...task, status: stream.status };
      }
      return task;
    });
  }, [liveTasks, strategyStreams]);
  const liveTaskStats = useMemo(() => buildLiveTaskStats(mergedLiveTasks, t), [mergedLiveTasks, t]);
  const timelineEntries = useMemo(
    () =>
      timelineEntriesRaw.map((entry) => {
        const stream = entry.request_id ? strategyStreams[entry.request_id] : undefined;
        if (!stream?.status) return entry;
        return { ...entry, status: stream.status };
      }),
    [timelineEntriesRaw, strategyStreams],
  );
  const taskSummary = useMemo(() => {
    const summary: Record<string, number> = {};
    milestones.forEach((milestone) =>
      (milestone.tasks || []).forEach((task) => {
        const key = (task.status || "PENDING").toUpperCase();
        summary[key] = (summary[key] || 0) + 1;
      }),
    );
    return Object.entries(summary).map(([name, value]) => ({ name, value }));
  }, [milestones]);

  const summaryCards = useMemo(
    () => [
      {
        label: t("strategy.kpi.visionProgress"),
        value: `${visionProgress.toFixed(1)}%`,
        percent: visionProgress,
        description: t("strategy.kpi.visionDesc"),
        tone: "violet" as const,
        source: t("strategy.kpi.source"),
      },
      {
        label: t("strategy.kpi.milestones"),
        value: `${kpis?.milestones_completed ?? 0} / ${kpis?.milestones_total ?? 0}`,
        percent: milestonesRaw,
        description: t("strategy.kpi.milestonesDesc"),
        tone: "indigo" as const,
        source: t("strategy.kpi.source"),
      },
      {
        label: t("strategy.kpi.tasks"),
        value: `${kpis?.tasks_completed ?? 0} / ${kpis?.tasks_total ?? 0}`,
        percent: tasksRaw,
        description: t("strategy.kpi.tasksDesc"),
        tone: "emerald" as const,
        source: t("strategy.kpi.source"),
      },
    ],
    [visionProgress, kpis, milestonesRaw, tasksRaw, t],
  );

  const roadmapDataStatus = calculateDataSourceStatus(
    !!liveRoadmap,
    !!cachedRoadmap,
    roadmapTimestamp,
    REPORT_STALE_MS,
  );

  const reportDataStatus = calculateDataSourceStatus(
    false, // Report is always from cache/manual fetch
    !!statusReport,
    reportTimestamp,
    REPORT_STALE_MS,
  );

  const handleCreateRoadmap = async () => {
    if (!visionInput.trim()) {
      setActionMessage(t("strategy.messages.visionPayload"));
      return;
    }
    setCreating(true);
    setActionMessage(null);
    try {
      await createRoadmap(visionInput.trim());
      showToast("success", "Roadmapa utworzona.");
      setVisionInput("");
      setShowVisionForm(false);
      refreshRoadmap();
    } catch (err) {
      showToast(
        "error",
        err instanceof Error ? err.message : t("strategy.messages.roadmapError"),
      );
    } finally {
      setCreating(false);
    }
  };

  const handleStatusReport = () => {
    fetchStatusReport();
  };

  const handleStartCampaign = async () => {
    if (!confirm(t("strategy.messages.campaignConfirm")))
      return;
    setActionMessage(null);
    try {
      const res = await startCampaign();
      showToast("success", res.message || t("strategy.messages.campaignSuccess"));
      // Automatycznie odśwież dane po uruchomieniu kampanii
      if (campaignRefreshTimer.current) {
        clearTimeout(campaignRefreshTimer.current);
      }
      campaignRefreshTimer.current = setTimeout(() => {
        refreshRoadmap();
        fetchStatusReport({ silent: true });
      }, AUTO_REFRESH_DELAY_MS);
    } catch (err) {
      showToast(
        "error",
        err instanceof Error ? err.message : t("strategy.messages.campaignError"),
      );
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <SectionHeading
        eyebrow={t("strategy.page.eyebrow")}
        title={t("strategy.page.title")}
        description={t("strategy.page.description")}
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="neutral">/api/roadmap</Badge>
              <Badge tone="neutral">/api/roadmap/status</Badge>
              <Badge tone="neutral">/api/campaign/start</Badge>
            </div>
            <Target className="page-heading-icon" />
          </div>
        }
      />
      {toast && (
        <div
          className={cn(
            "flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm shadow-card",
            toast.tone === "success"
              ? "border-emerald-400/40 bg-emerald-500/10 text-emerald-50"
              : "border-rose-400/40 bg-rose-500/10 text-rose-50",
          )}
        >
          <span>{toast.tone === "success" ? "✅" : "⚠️"}</span>
          <p>{toast.message}</p>
        </div>
      )}
      <div className="glass-panel flex flex-wrap gap-3 border border-white/10 p-6 shadow-card">
        <Button variant="primary" size="sm" onClick={() => refreshRoadmap()}>
          🔄 {t("strategy.actions.refresh")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => setShowVisionForm((prev) => !prev)}>
          ✨ {showVisionForm ? t("strategy.actions.hideVision") : t("strategy.actions.defineVision")}
        </Button>
        <Button variant="outline" size="sm" onClick={handleStartCampaign}>
          🚀 {t("strategy.actions.startCampaign")}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleStatusReport}
          disabled={reportLoading}
        >
          📊 {reportLoading ? t("strategy.actions.loading") : t("strategy.actions.statusReport")}
        </Button>
        {actionMessage && <p className="text-hint">{actionMessage}</p>}
      </div>

      {showVisionForm && (
        <Panel title={t("strategy.panels.newVision.title")} description={t("strategy.panels.newVision.description")}>
          <div className="space-y-3">
            <textarea
              className="min-h-[120px] w-full rounded-2xl box-base p-3 text-sm text-white outline-none focus:border-violet-500/40"
              placeholder={t("strategy.panels.newVision.placeholder")}
              value={visionInput}
              onChange={(e) => setVisionInput(e.target.value)}
            />
            <Button
              variant="primary"
              size="sm"
              disabled={creating}
              onClick={handleCreateRoadmap}
            >
              {creating ? t("strategy.actions.creating") : t("strategy.actions.createRoadmap")}
            </Button>
          </div>
        </Panel>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {summaryCards.map((card) => (
          <RoadmapKpiCard
            key={card.label}
            label={card.label}
            value={card.value}
            description={card.description}
            percent={card.percent}
            tone={card.tone}
            source={card.source}
          />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel
          title={t("strategy.panels.vision.title")}
          description={t("strategy.panels.vision.description")}
          action={
            <DataSourceIndicator
              status={roadmapDataStatus}
              timestamp={roadmapTimestamp}
            />
          }
        >
          {roadmapData?.vision ? (
            <div className="space-y-3 text-sm text-muted">
              <div className="flex items-center justify-between">
                <h3 className="heading-h3">{roadmapData.vision.title}</h3>
                <Badge tone="neutral">{roadmapData.vision.status ?? "n/a"}</Badge>
              </div>
              <MarkdownPreview content={roadmapData.vision.description} />
              <div>
                <p className="text-caption">{t("strategy.panels.vision.progress")}</p>
                <GradientProgress value={visionProgress} tone="violet" className="mt-2" />
              </div>
            </div>
          ) : roadmapError ? (
            <EmptyState
              icon={<span className="text-lg">⚠️</span>}
              title={t("strategy.panels.vision.backendError")}
              description={t("strategy.panels.vision.backendErrorDesc")}
            />
          ) : (
            <EmptyState
              icon={<span className="text-lg">✨</span>}
              title={t("strategy.panels.vision.noVision")}
              description={t("strategy.panels.vision.noVisionDesc")}
            />
          )}
        </Panel>
        <Panel
          title={t("strategy.panels.report.title")}
          description={t("strategy.panels.report.description")}
          action={
            <DataSourceIndicator
              status={reportDataStatus}
              timestamp={reportTimestamp}
            />
          }
        >
          {statusReport ? (
            <MarkdownPreview content={statusReport} />
          ) : (
            <EmptyState
              icon={<span className="text-lg">📊</span>}
              title={t("strategy.panels.report.emptyTitle")}
              description={t("strategy.panels.report.emptyDesc")}
            />
          )}
        </Panel>
        <Panel title={t("strategy.panels.tasks.title")} description={t("strategy.panels.tasks.description")}>
          <TaskStatusBreakdown
            title={t("strategy.panels.tasks.title")}
            datasetLabel="Milestones summary"
            totalLabel={t("common.total")}
            totalValue={taskSummary.reduce((acc, entry) => acc + entry.value, 0)}
            entries={taskSummary.map((entry) => ({ label: entry.name, value: entry.value }))}
            emptyMessage={t("strategy.panels.tasks.empty")}
          />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t("strategy.panels.liveKpis.title")} description={t("strategy.panels.liveKpis.description")}>
          {liveTasksLoading ? (
            <p className="text-hint">{t("strategy.panels.liveKpis.loading")}</p>
          ) : liveTaskStats.length ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {liveTaskStats.map((stat) => (
                <StatCard key={stat.label} label={stat.label} value={stat.value} hint={stat.hint} accent={stat.accent} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<span className="text-lg">🛰️</span>}
              title={t("strategy.panels.liveKpis.emptyTitle")}
              description={t("strategy.panels.liveKpis.emptyDesc")}
            />
          )}
        </Panel>

        <Panel title={t("strategy.panels.timeline.title")} description={t("strategy.panels.timeline.description")}>
          {timelineLoading && <p className="text-hint">{t("strategy.panels.timeline.loading")}</p>}
          {!timelineLoading && timelineEntries.length === 0 ? (
            <EmptyState
              icon={<span className="text-lg">🕒</span>}
              title={t("strategy.panels.timeline.emptyTitle")}
              description={t("strategy.panels.timeline.emptyDesc")}
            />
          ) : (
            <div className="space-y-3">
              {timelineEntries.map((entry) => (
                <div
                  key={entry.request_id}
                  className="flex items-start justify-between rounded-2xl box-base px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-semibold text-white">
                      #{entry.request_id.slice(0, 8)} • {entry.prompt?.slice(0, 32) ?? "Request"}
                    </p>
                    <p className="text-hint">
                      {formatRelativeTime(entry.created_at)} • {entry.model ?? "model n/d"}
                    </p>
                  </div>
                  <Badge tone={statusTone(entry.status)}>{entry.status ?? "n/a"}</Badge>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title={t("strategy.panels.milestones.title")} description={t("strategy.panels.milestones.description")}>
        {milestones.length === 0 ? (
          <EmptyState
            icon={<span className="text-lg">🏁</span>}
            title={t("strategy.panels.milestones.emptyTitle")}
            description={t("strategy.panels.milestones.emptyDesc")}
          />
        ) : (
          <Accordion type="multiple" className="space-y-3">
            {milestones.map((milestone, index) => {
              const progressValue = milestone.progress ?? 0;
              const totalTasks = milestone.tasks?.length ?? 0;
              const completedTasks = (milestone.tasks || []).filter((task) =>
                (task.status || "").toUpperCase().includes("DONE"),
              ).length;
              const emoji =
                totalTasks === 0
                  ? "🧭"
                  : completedTasks === totalTasks
                    ? "✅"
                    : completedTasks === 0
                      ? "🚧"
                      : "⚙️";
              return (
                <AccordionItem key={milestone.title ?? `ms-${index}`} value={milestone.title ?? `ms-${index}`}>
                  <AccordionTrigger className="text-white">
                    <div className="flex w-full items-center justify-between pr-4">
                      <div className="flex items-center gap-3">
                        <span className="text-lg" aria-hidden>
                          {emoji}
                        </span>
                        <div>
                          <p className="text-sm font-semibold">{milestone.title}</p>
                          <p className="text-hint">
                            {t("strategy.panels.milestones.progress")} {progressValue.toFixed(1)}% • {t("strategy.panels.milestones.priority")} {milestone.priority ?? "-"}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge tone={statusTone(milestone.status)}>{milestone.status ?? "n/a"}</Badge>
                        <p className="text-hint">
                          {t("strategy.panels.milestones.tasksCount", { completed: completedTasks, total: totalTasks })}
                        </p>
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <GradientProgress value={progressValue} tone="indigo" className="mb-3" />
                    <p className="text-hint">{milestone.description}</p>
                    <div className="mt-3 space-y-2 text-xs text-zinc-300">
                      {(milestone.tasks || []).length === 0 && <p className="text-hint">{t("strategy.panels.milestones.noTasks")}</p>}
                      {(milestone.tasks || []).map((task, idx) => (
                        <div
                          key={`${milestone.title}-${idx}`}
                          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                        >
                          <p className="font-semibold text-white">{task.title}</p>
                          <p className="text-hint">
                            {task.description || t("strategy.panels.milestones.noDesc")} • {task.status || "UNKNOWN"}
                          </p>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        )}
      </Panel>

      <Panel title={t("strategy.panels.fullReport.title")} description={t("strategy.panels.fullReport.description")}>
        <MarkdownPreview content={roadmapData?.report} emptyState={t("strategy.panels.fullReport.empty")} />
      </Panel>
    </div>
  );
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function buildLiveTaskStats(tasks: Task[] | null | undefined, t: (path: string, options?: any) => string) {
  const list = tasks ?? [];
  const total = list.length;

  const normalized = (status?: string | null) => (status ?? "").toUpperCase();
  const matches = (status: string, candidates: string[]) =>
    candidates.includes(normalized(status));

  const inProgress = list.filter((task) =>
    matches(task.status ?? "", ["IN_PROGRESS", "RUNNING", "EXECUTING"]),
  ).length;
  const queued = list.filter((task) =>
    matches(task.status ?? "", ["PENDING", "QUEUED", "WAITING"]),
  ).length;
  const failed = list.filter((task) =>
    matches(task.status ?? "", ["FAILED", "ERROR"]),
  ).length;

  return [
    {
      label: t("strategy.liveStats.active"),
      value: inProgress,
      hint: t("strategy.liveStats.activeHint", { total }),
      accent: "violet" as const,
    },
    {
      label: t("strategy.liveStats.queued"),
      value: queued,
      hint: t("strategy.liveStats.queuedHint"),
      accent: "blue" as const,
    },
    {
      label: t("strategy.liveStats.failed"),
      value: failed,
      hint: t("strategy.liveStats.failedHint"),
      accent: "indigo" as const,
    },
  ];
}

type GradientProgressProps = {
  value?: number;
  tone?: "violet" | "indigo" | "emerald";
  className?: string;
};

const progressToneClasses: Record<NonNullable<GradientProgressProps["tone"]>, string> = {
  violet: "bg-gradient-to-r from-violet-500 via-fuchsia-500 to-pink-500 shadow-[0_0_15px_rgba(167,139,250,0.6)]",
  indigo: "bg-gradient-to-r from-indigo-500 via-blue-500 to-cyan-500 shadow-[0_0_15px_rgba(99,102,241,0.5)]",
  emerald: "bg-gradient-to-r from-emerald-500 via-lime-400 to-amber-300 shadow-[0_0_15px_rgba(16,185,129,0.5)]",
};

function GradientProgress({ value = 0, tone = "violet", className }: GradientProgressProps) {
  const safeValue = Math.max(0, Math.min(100, Number.isFinite(value) ? (value as number) : 0));
  const toneClass = progressToneClasses[tone] ?? progressToneClasses.violet;
  return (
    <div className={cn("h-2 w-full rounded-full bg-white/10", className)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-300 ease-out", toneClass)}
        style={{ width: `${safeValue}%` }}
      />
    </div>
  );
}

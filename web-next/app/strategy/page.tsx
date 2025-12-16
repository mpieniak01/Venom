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
import { ProgressBar } from "@tremor/react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useEffect, useMemo, useState } from "react";
import { statusTone } from "@/lib/status";
import { RoadmapKpiCard } from "@/components/strategy/roadmap-kpi-card";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/date";
import type { Task } from "@/lib/types";

export default function StrategyPage() {
  const { data: roadmap, refresh: refreshRoadmap } = useRoadmap();
  const { data: liveTasks, loading: liveTasksLoading } = useTasks();
  const {
    data: timelineHistory,
    loading: timelineLoading,
  } = useHistory(10);
  const [visionInput, setVisionInput] = useState("");
  const [showVisionForm, setShowVisionForm] = useState(false);
  const [statusReport, setStatusReport] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [toast, setToast] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const showToast = (tone: "success" | "error", message: string) => {
    setToast({ tone, message });
  };

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const kpis = roadmap?.kpis;
  const visionProgress = roadmap?.vision?.progress ?? 0;
  const milestonesRaw =
    kpis && kpis.milestones_total
      ? ((kpis.milestones_completed ?? 0) / Math.max(kpis.milestones_total, 1)) * 100
      : 0;
  const tasksRaw =
    kpis && kpis.tasks_total
      ? ((kpis.tasks_completed ?? 0) / Math.max(kpis.tasks_total, 1)) * 100
      : 0;
  const milestones = useMemo(() => roadmap?.milestones ?? [], [roadmap?.milestones]);
  const liveTaskStats = useMemo(() => buildLiveTaskStats(liveTasks), [liveTasks]);
  const timelineEntries = useMemo(
    () => (timelineHistory ?? []).slice(0, 8),
    [timelineHistory],
  );
  const taskSummary = useMemo(() => {
    const summary: Record<string, number> = {};
    milestones.forEach((milestone) =>
      (milestone.tasks || []).forEach((task) => {
        const key = (task.status || "TODO").toUpperCase();
        summary[key] = (summary[key] || 0) + 1;
      }),
    );
    return Object.entries(summary).map(([name, value]) => ({ name, value }));
  }, [milestones]);

  const summaryCards = useMemo(
    () => [
      {
        label: "Postęp wizji",
        value: `${visionProgress.toFixed(1)}%`,
        percent: visionProgress,
        description: "Roadmap vision progress",
        tone: "violet" as const,
      },
      {
        label: "Milestones",
        value: `${kpis?.milestones_completed ?? 0} / ${kpis?.milestones_total ?? 0}`,
        percent: milestonesRaw,
        description: "Incomplete milestones",
        tone: "indigo" as const,
      },
      {
        label: "Tasks",
        value: `${kpis?.tasks_completed ?? 0} / ${kpis?.tasks_total ?? 0}`,
        percent: tasksRaw,
        description: "Execution tasks",
        tone: "emerald" as const,
      },
    ],
    [visionProgress, kpis, milestonesRaw, tasksRaw],
  );

  const handleCreateRoadmap = async () => {
    if (!visionInput.trim()) {
      setActionMessage("Podaj opis wizji.");
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
        err instanceof Error ? err.message : "Nie udało się utworzyć roadmapy.",
      );
    } finally {
      setCreating(false);
    }
  };

  const handleStatusReport = async () => {
    setReportLoading(true);
    setStatusReport(null);
    try {
      const res = await requestRoadmapStatus();
      setStatusReport(res.report || "Brak danych z Executive.");
      showToast("success", "Pobrano raport statusu.");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Nie udało się pobrać raportu.";
      setStatusReport(message);
      showToast("error", message);
    } finally {
      setReportLoading(false);
    }
  };

  const handleStartCampaign = async () => {
    if (!confirm("😳 Na pewno uruchomić kampanię? Wyśle to żądanie do API."))
      return;
    setActionMessage(null);
    try {
      const res = await startCampaign();
      showToast("success", res.message || "Kampania wystartowała (patrz logi).");
    } catch (err) {
      showToast(
        "error",
        err instanceof Error ? err.message : "Nie udało się uruchomić kampanii.",
      );
    }
  };

  return (
    <div className="space-y-8 pb-10">
      <SectionHeading
        eyebrow="War Room"
        title="Strategia i roadmapa"
        description="`/api/roadmap` + Strategy Agent — wizja, kampanie, status Executive."
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="neutral">/api/roadmap</Badge>
            <Badge tone="neutral">/api/roadmap/status</Badge>
            <Badge tone="neutral">/api/campaign/start</Badge>
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
          🔄 Odśwież Roadmapę
        </Button>
        <Button variant="outline" size="sm" onClick={() => setShowVisionForm((prev) => !prev)}>
          ✨ {showVisionForm ? "Ukryj" : "Zdefiniuj"} Wizję
        </Button>
        <Button variant="outline" size="sm" onClick={handleStartCampaign}>
          🚀 Uruchom Kampanię
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={handleStatusReport}
          disabled={reportLoading}
        >
          📊 {reportLoading ? "Ładuję..." : "Raport Statusu"}
        </Button>
        {actionMessage && (
          <p className="text-xs text-zinc-400">{actionMessage}</p>
        )}
      </div>

      {showVisionForm && (
        <Panel title="Nowa wizja" description="Utwórz roadmapę na bazie swojej wizji (/api/roadmap/create).">
          <div className="space-y-3">
            <textarea
              className="min-h-[120px] w-full rounded-2xl border border-white/10 bg-white/5 p-3 text-sm text-white outline-none focus:border-violet-500/40"
              placeholder="Opisz wizję produktową..."
              value={visionInput}
              onChange={(e) => setVisionInput(e.target.value)}
            />
            <Button
              variant="primary"
              size="sm"
              disabled={creating}
              onClick={handleCreateRoadmap}
            >
              {creating ? "Tworzenie..." : "Utwórz roadmapę"}
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
          />
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Wizja" description="Migawka magazynu celów">
          {roadmap?.vision ? (
            <div className="space-y-3 text-sm text-zinc-400">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold text-white">{roadmap.vision.title}</h3>
                <Badge tone="neutral">{roadmap.vision.status ?? "n/a"}</Badge>
              </div>
              <MarkdownPreview content={roadmap.vision.description} />
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Postęp wizji</p>
                <ProgressBar value={visionProgress} color="violet" className="mt-2" />
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<span className="text-lg">✨</span>}
              title="Brak zdefiniowanej wizji"
              description="Skorzystaj z formularza powyżej, aby utworzyć roadmapę."
            />
          )}
        </Panel>
        <Panel title="Raport statusu" description="Ostatni snapshot z `/api/roadmap/status`.">
          {statusReport ? (
            <MarkdownPreview content={statusReport} />
          ) : (
            <EmptyState
              icon={<span className="text-lg">📊</span>}
              title="Brak raportu"
              description="Kliknij „Raport Statusu”, aby pobrać aktualny stan kampanii."
            />
          )}
        </Panel>
        <Panel title="Podsumowanie zadań" description="Statusy tasków z milestones.">
          <TaskStatusBreakdown
            title="Stany zadań"
            datasetLabel="Milestones summary"
            totalLabel="Łącznie"
            totalValue={taskSummary.reduce((acc, entry) => acc + entry.value, 0)}
            entries={taskSummary.map((entry) => ({ label: entry.name, value: entry.value }))}
            emptyMessage="Brak zadań w roadmapie."
          />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Live KPIs" description="/api/v1/tasks – bieżące operacje agentów.">
          {liveTasksLoading ? (
            <p className="text-sm text-zinc-400">Ładuję metryki zadań…</p>
          ) : liveTaskStats.length ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {liveTaskStats.map((stat) => (
                <StatCard key={stat.label} label={stat.label} value={stat.value} hint={stat.hint} accent={stat.accent} />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={<span className="text-lg">🛰️</span>}
              title="Brak danych o zadaniach"
              description="Gdy agenci uruchomią nowe zadania, pojawią się tutaj statystyki."
            />
          )}
        </Panel>

        <Panel title="Timeline KPI" description="/api/v1/history – ostatnie przepływy.">
          {timelineLoading && <p className="text-sm text-zinc-400">Ładuję historię requestów…</p>}
          {!timelineLoading && timelineEntries.length === 0 ? (
            <EmptyState
              icon={<span className="text-lg">🕒</span>}
              title="Brak historii"
              description="Wyślij zadanie lub odśwież backend, by wypełnić timeline."
            />
          ) : (
            <div className="space-y-3">
              {timelineEntries.map((entry) => (
                <div
                  key={entry.request_id}
                  className="flex items-start justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-semibold text-white">
                      #{entry.request_id.slice(0, 8)} • {entry.prompt?.slice(0, 32) ?? "Request"}
                    </p>
                    <p className="text-xs text-zinc-400">
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

      <Panel title="Milestones" description="Accordion + progress dla kluczowych etapów.">
        {milestones.length === 0 ? (
          <EmptyState
            icon={<span className="text-lg">🏁</span>}
            title="Brak kamieni milowych"
            description="Utwórz wizję lub dodaj kamienie, aby zobaczyć postęp."
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
                          <p className="text-xs text-zinc-400">
                            Postęp {progressValue.toFixed(1)}% • Priorytet {milestone.priority ?? "-"}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge tone={statusTone(milestone.status)}>{milestone.status ?? "n/a"}</Badge>
                        <p className="text-[11px] text-zinc-500">
                          {completedTasks}/{totalTasks} zadań
                        </p>
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent>
                    <ProgressBar value={progressValue} color="indigo" className="mb-3" />
                    <p className="text-sm text-zinc-400">{milestone.description}</p>
                    <div className="mt-3 space-y-2 text-xs text-zinc-300">
                      {(milestone.tasks || []).length === 0 && <p className="text-zinc-500">Brak zadań.</p>}
                      {(milestone.tasks || []).map((task, idx) => (
                        <div
                          key={`${milestone.title}-${idx}`}
                          className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                        >
                          <p className="font-semibold text-white">{task.title}</p>
                          <p className="text-zinc-400">
                            {task.description || "Brak opisu."} • {task.status || "TODO"}
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

      <Panel title="Pełny raport" description="/api/roadmap (pole report)">
        <MarkdownPreview content={roadmap?.report} emptyState="Brak raportu." />
      </Panel>
    </div>
  );
}

function buildLiveTaskStats(tasks: Task[] | null | undefined) {
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
      label: "Aktywne",
      value: inProgress,
      hint: `z ${total} zadań`,
      accent: "violet" as const,
    },
    {
      label: "W kolejce",
      value: queued,
      hint: "oczekuje na wykonanie",
      accent: "blue" as const,
    },
    {
      label: "Niepowodzenia",
      value: failed,
      hint: "ostatnie incydenty",
      accent: "indigo" as const,
    },
  ];
}

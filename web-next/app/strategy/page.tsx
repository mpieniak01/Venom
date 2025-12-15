"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import { MarkdownPreview } from "@/components/ui/markdown";
import { SectionHeading } from "@/components/ui/section-heading";
import {
  createRoadmap,
  requestRoadmapStatus,
  startCampaign,
  useRoadmap,
} from "@/hooks/use-api";
import { ProgressBar } from "@tremor/react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useMemo, useState } from "react";
import { statusTone } from "@/lib/status";
import { RoadmapKpiCard } from "@/components/strategy/roadmap-kpi-card";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";

export default function StrategyPage() {
  const { data: roadmap, refresh: refreshRoadmap } = useRoadmap();
  const [visionInput, setVisionInput] = useState("");
  const [showVisionForm, setShowVisionForm] = useState(false);
  const [statusReport, setStatusReport] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);

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
      setActionMessage("Roadmapa utworzona.");
      setVisionInput("");
      setShowVisionForm(false);
      refreshRoadmap();
    } catch (err) {
      setActionMessage(
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
    } catch (err) {
      setStatusReport(
        err instanceof Error ? err.message : "Nie udało się pobrać raportu.",
      );
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
      setActionMessage(res.message || "Kampania wystartowała (patrz logi).");
    } catch (err) {
      setActionMessage(
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
        <Panel title="Wizja" description="Goal Store snapshot">
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
              return (
                <AccordionItem key={milestone.title ?? `ms-${index}`} value={milestone.title ?? `ms-${index}`}>
                  <AccordionTrigger className="text-white">
                    <div className="flex w-full items-center justify-between pr-4">
                      <div>
                        <p className="text-sm font-semibold">{milestone.title}</p>
                        <p className="text-xs text-zinc-400">
                          Postęp {progressValue.toFixed(1)}% • Priorytet {milestone.priority ?? "-"}
                        </p>
                      </div>
                      <Badge tone={statusTone(milestone.status)}>{milestone.status ?? "n/a"}</Badge>
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

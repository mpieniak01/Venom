"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { fetchHistoryDetail, useHistory, useTasks } from "@/hooks/use-api";
import type { HistoryStep as HistoryStepType, HistoryRequest, Task } from "@/lib/types";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { Activity, Layers, Radar, TimerReset, ListFilter, ZoomIn, ZoomOut, RotateCcw } from "lucide-react";
import { LatencyCard } from "@/components/inspector/lag-card";
import { HistoryList } from "@/components/history/history-list";
import { formatRelativeTime } from "@/lib/date";
import { statusTone } from "@/lib/status";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";

export default function InspectorPage() {
  const { data: history } = useHistory(50);
  const { data: tasks } = useTasks();
  const [diagram, setDiagram] = useState<string>("graph TD\nA[Brak danych]");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<HistoryStep[]>([]);
  const [stepFilter, setStepFilter] = useState("");
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const svgRef = useRef<HTMLDivElement | null>(null);
  const filteredSteps = useMemo(() => filterSteps(steps, stepFilter), [steps, stepFilter]);
  const stepsCount = steps.length;
  const selectedRequest = useMemo(
    () => (history || []).find((req) => req.request_id === selectedId) ?? null,
    [history, selectedId],
  );
  const focusedStep = useMemo(
    () => (focusedIndex !== null ? filteredSteps[focusedIndex] : null),
    [filteredSteps, focusedIndex],
  );
  const inspectorStats = useMemo(() => buildInspectorStats(history, tasks), [history, tasks]);
  const taskBreakdown = useMemo(() => buildTaskBreakdown(tasks), [tasks]);
  const latencyCards = useMemo(
    () => [
      {
        label: "Średni SLA",
        value: formatDuration(inspectorStats.avgDuration),
        hint: "czas wykonania requestu",
      },
      {
        label: "Aktywne śledzenia",
        value: inspectorStats.processing.toString(),
        hint: `z ${inspectorStats.total} logów`,
      },
      {
        label: "Kroki (filtr)",
        value: filteredSteps.length.toString(),
        hint: `${stepsCount} w bieżącym flow`,
      },
    ],
    [filteredSteps.length, inspectorStats.avgDuration, inspectorStats.processing, inspectorStats.total, stepsCount],
  );

  useEffect(() => {
    let isMounted = true;
    (async () => {
      const mermaid = (await import("mermaid")).default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        securityLevel: "loose",
      });
      try {
        const { svg } = await mermaid.render("flow-chart", diagram);
        if (svgRef.current && isMounted) {
          svgRef.current.innerHTML = svg;
        }
      } catch (err) {
        console.error("Mermaid render error:", err);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [diagram]);

  useEffect(() => {
    if (!filteredSteps.length) {
      setFocusedIndex(null);
      return;
    }
    setFocusedIndex((current) => {
      if (current === null || current >= filteredSteps.length) {
        return 0;
      }
      return current;
    });
  }, [filteredSteps]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Inspector / Debugging"
        title="Trace Intelligence"
        description="RequestTracer + Mermaid: natychmiastowy podgląd przepływu, kroków i kondycji kolejki."
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap gap-2 text-xs">
            <Badge tone="neutral">/api/v1/history/requests</Badge>
            <Badge tone="neutral">/api/v1/tasks</Badge>
            <Badge tone="neutral">/history/requests/:id</Badge>
          </div>
        }
      />
      <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <HeroStat
          icon={<Activity className="h-4 w-4 text-emerald-300" />}
          label="Skuteczność"
          primary={`${inspectorStats.successRate}%`}
          hint={`${inspectorStats.completed} zakończonych`}
        />
        <HeroStat
          icon={<Layers className="h-4 w-4 text-violet-300" />}
          label="Historia requestów"
          primary={inspectorStats.total.toString()}
          hint={`${inspectorStats.processing} aktywnych śledzeń`}
        />
        <HeroStat
          icon={<TimerReset className="h-4 w-4 text-sky-300" />}
          label="Śr. czas realizacji"
          primary={formatDuration(inspectorStats.avgDuration)}
          hint="ostatnie 50"
        />
        <HeroStat
          icon={<Radar className="h-4 w-4 text-indigo-300" />}
          label="Aktywne zadania"
          primary={inspectorStats.activeTasks.toString()}
          hint={`${taskBreakdown.find((b) => b.status === "PROCESSING")?.count ?? 0} procesowanych`}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {latencyCards.map((card) => (
          <LatencyCard key={card.label} label={card.label} value={card.value} hint={card.hint} />
        ))}
      </div>

      <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <Panel
            title="Kolejka requestów"
            description="Ostatnie 50 historii RequestTracer."
          >
            <HistoryList
              entries={history}
              selectedId={selectedId}
              onSelect={(entry) =>
                loadHistoryDetail(
                  entry.request_id,
                  setDiagram,
                  setSelectedId,
                  setSteps,
                  () => setStepFilter(""),
                  () => setCopyMessage(null),
                )
              }
              emptyTitle="Brak historii do wyświetlenia"
              emptyDescription="Wyślij zadanie, aby zobaczyć przepływ w historii."
            />
          </Panel>

          <Panel
            title="Task telemetry"
            description="Status agentów oczekujących na wykonanie."
          >
            <TaskStatusBreakdown
              title="Task telemetry"
              datasetLabel="Zadania w obserwacji"
              totalLabel="Aktywne"
              totalValue={inspectorStats.activeTasks}
              entries={taskBreakdown.map((entry) => ({
                label: entry.status,
                value: entry.count,
              }))}
              emptyMessage="Taski pojawią się, gdy kolejka uruchomi nowe zadania."
            />
          </Panel>
        </aside>

        <section className="space-y-6">
          <Panel
            title="Diagnoza przepływu"
            description="Mermaid flow graph + zoom/drag (react-zoom-pan-pinch)."
            action={
              <div className="text-sm text-zinc-400">
                Wybrany request:{" "}
                <span className="font-semibold text-white">{selectedId ?? "—"}</span>
              </div>
            }
          >
            <TransformWrapper>
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                    <IconButton label="Przybliż" icon={<ZoomIn className="h-4 w-4" />} onClick={() => zoomIn()} />
                    <IconButton label="Oddal" icon={<ZoomOut className="h-4 w-4" />} onClick={() => zoomOut()} />
                    <IconButton label="Resetuj" icon={<RotateCcw className="h-4 w-4" />} onClick={() => resetTransform()} />
                  </div>
                  <div className="rounded-[28px] border border-white/10 bg-black/30 p-4">
                    <TransformComponent>
                      <div className="min-h-[420px] min-w-full">
                        <div ref={svgRef} className="min-h-[420px]" />
                      </div>
                    </TransformComponent>
                  </div>
                </>
              )}
            </TransformWrapper>
          </Panel>

          <div className="grid gap-6 lg:grid-cols-2">
            <Panel
              title="Kroki RequestTracer"
              description="Przefiltruj i wybierz krok, aby zobaczyć telemetrię."
              action={
                <div className="flex flex-col gap-2 text-xs sm:flex-row">
                  <input
                    type="text"
                    placeholder="Filtruj kroki..."
                    value={stepFilter}
                    onChange={(e) => setStepFilter(e.target.value)}
                    className="w-full rounded-full border border-white/10 bg-white/5 px-4 py-1 text-white outline-none placeholder:text-zinc-500 focus:border-violet-500/40"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleCopySteps(filteredSteps, setCopyMessage)}
                  >
                    Kopiuj JSON
                  </Button>
                </div>
              }
            >
              {copyMessage && (
                <p className="mb-3 text-xs text-emerald-300">{copyMessage}</p>
              )}
              <div className="space-y-3">
                {filteredSteps.length === 0 && (
                  <EmptyState
                    icon={<ListFilter className="h-4 w-4" />}
                    title="Brak kroków – wybierz request"
                    description="Kroki pojawią się po załadowaniu szczegółów requestu."
                    className="text-sm"
                  />
                )}
                {filteredSteps.map((step, idx) => (
                  <button
                    key={`${selectedId}-${idx}`}
                    onClick={() => setFocusedIndex(idx)}
                    className={`w-full rounded-2xl border px-4 py-3 text-left text-sm transition ${
                      focusedIndex === idx
                        ? "border-violet-400/60 bg-violet-500/10"
                        : "border-white/10 bg-white/5"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-white">{step.component || "Nieznany komponent"}</p>
                        <p className="text-xs text-zinc-400">{step.action || step.details || "—"}</p>
                      </div>
                      {step.status && <Badge tone={statusTone(step.status)}>{step.status}</Badge>}
                    </div>
                    {step.timestamp && (
                      <p className="mt-1 text-[11px] uppercase tracking-wide text-zinc-500">
                        {formatTimestamp(step.timestamp)}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            </Panel>

            <Panel
              title="Telemetria requestu"
              description="Status, czas i szczegóły aktualnego przepływu."
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <StatCard
                  label="Status"
                  value={selectedRequest?.status ?? "—"}
                  hint={selectedRequest ? `Zakończone: ${formatRelativeTime(selectedRequest.finished_at)}` : "Wybierz request z listy"}
                  accent="purple"
                />
                <StatCard
                  label="Czas wykonania"
                  value={formatDuration(selectedRequest?.duration_seconds ?? null)}
                  hint={`Start: ${formatTimestamp(selectedRequest?.created_at)}`}
                  accent="blue"
                />
                <StatCard
                  label="Łączna liczba kroków"
                  value={steps.length}
                  hint={`Po filtrze: ${filteredSteps.length}`}
                  accent="green"
                />
                <StatCard
                  label="Wskaźnik awarii"
                  value={`${inspectorStats.failed}`}
                  hint="Fail w ostatnich requestach"
                  accent="purple"
                />
              </div>
              <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">
                  Wybrany krok
                </p>
                <h4 className="mt-2 text-lg font-semibold text-white">
                  {focusedStep?.component ?? "—"}
                </h4>
                <p className="text-sm text-zinc-300">
                  {focusedStep?.action || focusedStep?.details || "Kliknij krok, aby zobaczyć treść."}
                </p>
                <dl className="mt-3 grid gap-3 text-xs text-zinc-400 sm:grid-cols-2">
                  <div>
                    <dt className="uppercase tracking-wide text-[11px] text-zinc-500">
                      Status
                    </dt>
                    <dd className="text-white">
                      {focusedStep?.status ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="uppercase tracking-wide text-[11px] text-zinc-500">
                      Timestamp
                    </dt>
                    <dd>{focusedStep?.timestamp ? formatTimestamp(focusedStep.timestamp) : "—"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="uppercase tracking-wide text-[11px] text-zinc-500">
                      Detale
                    </dt>
                    <dd className="text-zinc-300">
                      {focusedStep?.details ?? "Brak dodatkowych danych."}
                    </dd>
                  </div>
                </dl>
              </div>
            </Panel>
          </div>
        </section>
      </div>
    </div>
  );
}

type HistoryStep = HistoryStepType;

const filterSteps = (steps: HistoryStep[], query: string) => {
  if (!query.trim()) return steps;
  const lower = query.toLowerCase();
  return steps.filter((step) =>
    `${step.component ?? ""} ${step.action ?? ""}`.toLowerCase().includes(lower),
  );
};

async function handleCopySteps(
  steps: HistoryStep[],
  setCopyMessage: (msg: string | null) => void,
) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(steps, null, 2));
    setCopyMessage("Skopiowano kroki.");
    setTimeout(() => setCopyMessage(null), 2000);
  } catch (err) {
    console.error("Clipboard error:", err);
    setCopyMessage("Nie udało się skopiować.");
    setTimeout(() => setCopyMessage(null), 2000);
  }
}

async function loadHistoryDetail(
  requestId: string,
  setDiagram: (d: string) => void,
  setSelected: (id: string) => void,
  setSteps: (s: HistoryStep[]) => void,
  resetFilter: () => void,
  resetCopy: () => void,
) {
  const detail = (await fetchHistoryDetail(requestId)) as { steps?: HistoryStep[] };
  const steps = detail.steps || [];
  const diagram = buildMermaid(steps);
  setDiagram(diagram);
  setSelected(requestId);
  setSteps(steps);
  resetFilter();
  resetCopy();
}

function buildMermaid(steps: HistoryStep[]) {
  if (!steps.length) {
    return "graph TD\nA[Brak kroków]";
  }
  const lines = ["graph TD"];
  steps.forEach((step, idx) => {
    const nodeId = `S${idx}`;
    const label = `${step.component || "step"}: ${step.action || ""}`
      .replace(/"/g, "'")
      .slice(0, 40);
    lines.push(`${nodeId}["${label}"]`);
    if (idx > 0) {
      lines.push(`S${idx - 1} --> ${nodeId}`);
    }
  });
  return lines.join("\n");
}

function buildInspectorStats(history: HistoryRequest[] | null | undefined, tasks?: Task[] | null) {
  const requests = history || [];
  const total = requests.length;
  const completed = requests.filter((req) => req.status === "COMPLETED").length;
  const failed = requests.filter((req) => req.status === "FAILED").length;
  const processing = requests.filter((req) => req.status === "PROCESSING").length;
  const durations = requests
    .map((req) => req.duration_seconds ?? 0)
    .filter((value) => value > 0);
  const avgDuration = durations.length
    ? durations.reduce((sum, value) => sum + value, 0) / durations.length
    : 0;
  const successRate = total ? Math.round((completed / Math.max(total, 1)) * 100) : 0;
  return {
    total,
    completed,
    failed,
    processing,
    avgDuration,
    successRate,
    activeTasks: tasks?.length ?? 0,
  };
}

function buildTaskBreakdown(tasks?: Task[] | null) {
  if (!tasks || tasks.length === 0) return [];
  const summary: Record<string, number> = {};
  tasks.forEach((task) => {
    const key = task.status || "UNKNOWN";
    summary[key] = (summary[key] || 0) + 1;
  });
  return Object.entries(summary).map(([status, count]) => ({ status, count }));
}

function formatDuration(durationSeconds: number | null | undefined) {
  if (!durationSeconds || durationSeconds <= 0) return "—";
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = Math.floor(durationSeconds % 60);
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds.toString().padStart(2, "0")}s`;
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

type HeroStatProps = {
  icon: ReactNode;
  label: string;
  primary: string;
  hint: string;
};

function HeroStat({ icon, label, primary, hint }: HeroStatProps) {
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.03] px-4 py-3">
      <span className="rounded-full border border-white/10 bg-black/40 p-2">
        {icon}
      </span>
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
        <p className="text-xl font-semibold text-white">{primary}</p>
        <p className="text-xs text-zinc-400">{hint}</p>
      </div>
    </div>
  );
}

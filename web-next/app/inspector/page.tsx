"use client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel, StatCard } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import { fetchFlowTrace, fetchHistoryDetail, useHistory, useTasks } from "@/hooks/use-api";
import { useTaskStream } from "@/hooks/use-task-stream";
import type { FlowTrace, HistoryStep as HistoryStepType, HistoryRequest, Task } from "@/lib/types";
import { useEffect, useMemo, useRef, useState, useCallback, type ReactNode } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import {
  Activity,
  Layers,
  Radar,
  BugPlay,
  TimerReset,
  ListFilter,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  RefreshCw,
  Loader2,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { LatencyCard } from "@/components/inspector/lag-card";
import { HistoryList } from "@/components/history/history-list";
import { formatRelativeTime } from "@/lib/date";
import { statusTone } from "@/lib/status";
import { TaskStatusBreakdown } from "@/components/tasks/task-status-breakdown";

function sanitizeMermaidDiagram(value: string) {
  const cleaned = value.replace(/\r?\n/g, "\n");
  const safeChars = new Set(
    Array.from(
      "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,:/_-[]()>",
    ),
  );
  let output = "";
  for (const char of cleaned) {
    if (char === "\n") {
      output += "\n";
      continue;
    }
    output += safeChars.has(char) ? char : " ";
  }
  return output;
}

function decorateExecutionFailed(container: HTMLDivElement) {
  const svg = container.querySelector("svg");
  if (!svg) return;
  const textNodes = svg.querySelectorAll("text");
  textNodes.forEach((node) => {
    if (!node.textContent?.includes("execution.failed")) return;
    if (node.querySelector(".execution-failed-marker")) return;
    const marker = document.createElementNS(
      "http://www.w3.org/2000/svg",
      "tspan",
    );
    marker.setAttribute("class", "execution-failed-marker");
    marker.setAttribute("dx", "6");
    marker.textContent = "✖";
    node.appendChild(marker);
  });
}

export default function InspectorPage() {
  const {
    data: history,
    refresh: refreshHistory,
    loading: historyLoading,
  } = useHistory(50);
  const { data: tasks } = useTasks();
  const DEFAULT_DIAGRAM = [
    "sequenceDiagram",
    "    autonumber",
    "    Note over User: Wybierz request z listy",
  ].join("\n");
  const [diagram, setDiagram] = useState<string>(DEFAULT_DIAGRAM);
  const [diagramLoading, setDiagramLoading] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [steps, setSteps] = useState<HistoryStep[]>([]);
  const [stepFilter, setStepFilter] = useState("");
  const [contractOnly, setContractOnly] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number | null>(null);
  const [historyRefreshPending, setHistoryRefreshPending] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mermaidError, setMermaidError] = useState<string | null>(null);
  const [mermaidReloadKey, setMermaidReloadKey] = useState(0);
  const [flowFullscreen, setFlowFullscreen] = useState(false);
  type MermaidAPI = typeof import("mermaid").default;
  const [mermaidApi, setMermaidApi] = useState<MermaidAPI | null>(null);
  const svgRef = useRef<HTMLDivElement | null>(null);
  const mermaidInitializedRef = useRef(false);
  const fitViewRef = useRef<(() => void) | null>(null);
  const streamRefreshRef = useRef<Record<string, string | null>>({});
  const lastHistoryAutoRefreshRef = useRef<number>(0);
  const HISTORY_AUTO_REFRESH_MS = 5000;
  const filteredSteps = useMemo(
    () => filterSteps(steps, stepFilter, contractOnly),
    [steps, stepFilter, contractOnly],
  );
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
  const trackedTaskIds = useMemo(() => {
    const ids = new Set<string>();
    (history ?? []).forEach((entry) => {
      if (entry.status === "PENDING" || entry.status === "PROCESSING") {
        ids.add(entry.request_id);
      }
    });
    (tasks ?? []).forEach((task) => {
      const identifier = task.task_id || task.id;
      if (!identifier) return;
      const normalized = (task.status || "").toUpperCase();
      if (normalized === "PENDING" || normalized === "PROCESSING") {
        ids.add(identifier);
      }
    });
    if (selectedId) {
      ids.add(selectedId);
    }
    return Array.from(ids);
  }, [history, tasks, selectedId]);
  const { streams: inspectorStreams } = useTaskStream(trackedTaskIds, {
    enabled: trackedTaskIds.length > 0,
  });
  const streamForSelected = selectedId ? inspectorStreams[selectedId] : undefined;
  const liveSelectedStatus = streamForSelected?.status ?? selectedRequest?.status ?? "—";
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
    if (typeof window === "undefined") return;
    let cancelled = false;
    import("mermaid")
      .then((mod) => {
        if (cancelled) return;
        const mermaidModule = mod.default ?? (mod as unknown as MermaidAPI);
        setMermaidApi(mermaidModule);
      })
      .catch((err) => {
        console.error("Mermaid import failed:", err);
        if (!cancelled) {
          setMermaidError("Nie udało się załadować biblioteki Mermaid.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!mermaidApi || mermaidInitializedRef.current) {
      return;
    }
    mermaidApi.initialize({
      startOnLoad: false,
      theme: "dark",
      securityLevel: "loose",
      themeCSS: `
        :root {
          --mermaid-font-family: 'Inter, JetBrains Mono', sans-serif;
        }
        .node > rect,
        .node > circle,
        .node > polygon,
        .actor {
          fill: #0f172a !important;
          stroke: #38bdf8 !important;
          stroke-width: 1.4px;
        }
        .messageLine0,
        .loopLine {
          stroke: #38bdf8 !important;
        }
        .messageText,
        .actor > text,
        .noteText {
          fill: #e2e8f0 !important;
        }
        .note {
          fill: #1c1917 !important;
          stroke: #fbbf24 !important;
        }
        .execution-failed-marker {
          fill: #f87171 !important;
          font-weight: 700;
        }
      `,
    });
    mermaidInitializedRef.current = true;
  }, [DEFAULT_DIAGRAM, mermaidApi]);

  useEffect(() => {
    let cancelled = false;

    const render = async () => {
      if (!svgRef.current) return;
      const fallbackDiagram = [
        "sequenceDiagram",
        "    autonumber",
        "    participant User",
        "    participant System",
        "    User->>System: diagram_error",
      ].join("\n");
      try {
        const container = svgRef.current;
        const safeDiagram = sanitizeMermaidDiagram(diagram);
        container.innerHTML = `<div class="mermaid"></div>`;
        const node = container.querySelector(".mermaid");
        if (node) {
          node.textContent = safeDiagram;
        }
        if (!mermaidApi) {
          throw new Error("Mermaid API not ready.");
        }
        try {
          await mermaidApi.run({
            nodes: container.querySelectorAll(".mermaid"),
          });
        } catch {
          const fallback = sanitizeMermaidDiagram(fallbackDiagram);
          if (node) {
            node.textContent = fallback;
          }
          await mermaidApi.run({
            nodes: container.querySelectorAll(".mermaid"),
          });
          if (!cancelled) {
            setMermaidError(
              "Diagram uproszczony – oryginał zawierał niedozwolone znaki.",
            );
          }
          return;
        }
        decorateExecutionFailed(container);
        adjustMermaidSizing(container);
        if (!cancelled) {
          setMermaidError(null);
          requestAnimationFrame(() => fitViewRef.current?.());
        }
      } catch (err) {
        console.error("Mermaid render error:", err);
        if (!cancelled) {
          setMermaidError(
            "Nie udało się wyrenderować diagramu – spróbuj ponownie lub sprawdź, czy RequestTracer działa.",
          );
        }
      }
    };

    if (diagram && mermaidApi) {
      render();
    } else if (svgRef.current) {
      svgRef.current.innerHTML = "";
    }

    return () => {
      cancelled = true;
    };
  }, [diagram, mermaidReloadKey, mermaidApi]);

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

  const handleHistoryRefresh = async () => {
    setHistoryRefreshPending(true);
    try {
      await refreshHistory();
    } finally {
      setHistoryRefreshPending(false);
    }
  };

  const currentDiagramRequestRef = useRef<string | null>(null);

  const handleHistorySelect = useCallback(async (requestId: string, force = false) => {
    if (!force && currentDiagramRequestRef.current === requestId) {
      return;
    }
    currentDiagramRequestRef.current = requestId;
    setDiagramLoading(true);
    setDetailError(null);
    setSelectedId(requestId);
    setSteps([]);
    setFocusedIndex(null);
    setStepFilter("");
    setCopyMessage(null);
    setMermaidError(null);
    try {
      const flow = await fetchFlowTrace(requestId);
      const flowSteps = (flow.steps || []) as HistoryStep[];
      setSteps(flowSteps);
      const diagramSource =
        (flow.mermaid_diagram && flow.mermaid_diagram.trim().length > 0
          ? flow.mermaid_diagram
          : flowSteps.length > 0
            ? buildSequenceDiagram(flow)
            : null) ?? DEFAULT_DIAGRAM;
      setDiagram(diagramSource);
    } catch (flowError) {
      console.error("Flow trace error:", flowError);
      setDetailError(
        flowError instanceof Error ? flowError.message : "Nie udało się pobrać przepływu.",
      );
      try {
        const detail = await fetchHistoryDetail(requestId);
        const detailSteps = detail.steps || [];
        setSteps(detailSteps);
        setDiagram(detailSteps.length > 0 ? buildFlowchartDiagram(detailSteps) : DEFAULT_DIAGRAM);
      } catch (historyError) {
        console.error("Fallback detail error:", historyError);
        setSteps([]);
        setDiagram("graph TD\nE[Błąd ładowania]");
      }
    } finally {
      setDiagramLoading(false);
    }
  }, [DEFAULT_DIAGRAM]);

  useEffect(() => {
    if (historyLoading) return;
    if (!history || history.length === 0) return;
    if (selectedId) return;
    handleHistorySelect(history[0].request_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [historyLoading, history, selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    const stream = inspectorStreams[selectedId];
    if (!stream?.lastEventAt) return;
    const previousTs = streamRefreshRef.current[selectedId];
    if (previousTs === stream.lastEventAt) return;
    streamRefreshRef.current[selectedId] = stream.lastEventAt;
    const now = Date.now();
    if (now - lastHistoryAutoRefreshRef.current < HISTORY_AUTO_REFRESH_MS) {
      return;
    }
    lastHistoryAutoRefreshRef.current = now;
    refreshHistory();
  }, [inspectorStreams, selectedId, refreshHistory]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Inspector / Diagnostyka"
        title="Analiza śladów"
        description="RequestTracer + Mermaid: natychmiastowy podgląd przepływu, kroków i kondycji kolejki."
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-wrap gap-2 text-xs">
              <Badge tone="neutral">/api/v1/history/requests</Badge>
              <Badge tone="neutral">/api/v1/tasks</Badge>
              <Badge tone="neutral">/history/requests/:id</Badge>
            </div>
            <BugPlay className="page-heading-icon" />
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

      <div
        className={`grid gap-6 ${
          flowFullscreen ? "grid-cols-1" : "xl:grid-cols-[360px_minmax(0,1fr)]"
        }`}
      >
        {!flowFullscreen && (
          <aside className="space-y-4">
            <Panel
              title="Kolejka requestów"
              description="Ostatnie 50 historii RequestTracer."
              action={
                <Button
                  variant="outline"
                  size="xs"
                  onClick={handleHistoryRefresh}
                  disabled={historyRefreshPending}
                >
                  <RefreshCw className="mr-2 h-3.5 w-3.5" />
                  {historyRefreshPending ? "Odświeżam…" : "Odśwież"}
                </Button>
              }
            >
              <div className="relative min-h-[280px]">
                <HistoryList
                  entries={history}
                  selectedId={selectedId}
                  onSelect={(entry) => handleHistorySelect(entry.request_id)}
                  emptyTitle="Brak historii do wyświetlenia"
                  emptyDescription="Wyślij zadanie, aby zobaczyć przepływ w historii."
                />
              </div>
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
        )}

        <section className="space-y-6">
          <Panel
            title="Diagnoza przepływu"
            action={
              <div className="flex flex-wrap items-center gap-3 text-sm text-zinc-400">
                <div className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:gap-3">
                  <span>
                    Wybrany request:{" "}
                    <span className="font-semibold text-white">{selectedId ?? "—"}</span>
                  </span>
                  {detailError && <span className="text-rose-300">{detailError}</span>}
                </div>
                <IconButton
                  label={flowFullscreen ? "Wyłącz pełny ekran" : "Pełny ekran"}
                  size="xs"
                  variant="outline"
                  className="border-white/10 text-white"
                  icon={flowFullscreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
                  onClick={() => setFlowFullscreen((prev) => !prev)}
                />
              </div>
            }
          >
            <TransformWrapper wheel={{ step: 0.15 }}>
              {({ zoomIn, zoomOut, resetTransform, setTransform }) => {
                fitViewRef.current = () =>
                  autoFitDiagram(svgRef.current, (x, y, scale, duration, easing) =>
                    setTransform(x, y, scale, duration, easing as Parameters<typeof setTransform>[4]),
                  );
                return (
                  <>
                    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
                      <IconButton label="Przybliż" icon={<ZoomIn className="h-4 w-4" />} onClick={() => zoomIn()} />
                    <IconButton label="Oddal" icon={<ZoomOut className="h-4 w-4" />} onClick={() => zoomOut()} />
                    <IconButton label="Resetuj" icon={<RotateCcw className="h-4 w-4" />} onClick={() => resetTransform()} />
                  </div>
                    <div className="relative rounded-[28px] box-muted p-4">
                      {diagramLoading && (
                        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-[28px] bg-black/70 text-sm text-white">
                          <Loader2 className="h-5 w-5 animate-spin text-emerald-300" />
                          Ładuję kroki…
                        </div>
                      )}
                      {mermaidError && (
                        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-3 rounded-[28px] bg-black/80 px-6 text-center text-sm text-rose-200">
                          <p>{mermaidError}</p>
                          <Button variant="outline" size="sm" onClick={() => setMermaidReloadKey((key) => key + 1)}>
                            Spróbuj ponownie
                          </Button>
                        </div>
                      )}
                      <TransformComponent
                        wrapperStyle={{ width: "100%", height: "100%" }}
                        contentStyle={{ width: "100%", height: "100%" }}
                      >
                        <div className="relative min-h-[700px] w-full">
                          <div
                            ref={svgRef}
                            className="h-full w-full [&>svg]:h-full [&>svg]:w-full [&>svg]:rounded-[20px] [&>svg]:bg-[#020617] [&>svg]:p-4 [&>svg_path]:stroke-[#38bdf8]"
                          />
                          {!selectedId && !diagramLoading && (
                            <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-500">
                              Wybierz request z listy, aby zbudować przepływ.
                            </div>
                          )}
                          {!diagramLoading && (detailError || mermaidError || steps.length === 0) && (
                            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-[28px] bg-black/70 text-center text-sm text-zinc-300">
                              <p>
                                {detailError ||
                                  mermaidError ||
                                  "Brak kroków do pokazania – sprawdź, czy RequestTracer działa na porcie 8000."}
                              </p>
                              {detailError && (
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => handleHistorySelect(selectedId as string, true)}
                                  disabled={!selectedId}
                                >
                                  Spróbuj ponownie
                                </Button>
                              )}
                            </div>
                          )}
                        </div>
                      </TransformComponent>
                    </div>
                  </>
                );
              }}
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
                  <label className="pill-badge flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={contractOnly}
                      onChange={(e) => setContractOnly(e.target.checked)}
                    />
                    Tylko kontrakty
                  </label>
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
                  <Button
                    key={`${selectedId}-${idx}`}
                    onClick={() => setFocusedIndex(idx)}
                    variant="ghost"
                    size="sm"
                    className={`list-row w-full text-left text-sm transition ${
                      focusedIndex === idx
                        ? "border-violet-400/60 bg-violet-500/10"
                        : "border-white/10 bg-white/5"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="font-semibold text-white">{step.component || "Nieznany komponent"}</p>
                        <p className="text-hint">{step.action || step.details || "—"}</p>
                      </div>
                      {step.status && <Badge tone={statusTone(step.status)}>{step.status}</Badge>}
                    </div>
                    {step.timestamp && (
                      <p className="mt-1 text-caption">
                        {formatTimestamp(step.timestamp)}
                      </p>
                    )}
                  </Button>
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
                  value={liveSelectedStatus}
                  hint={
                    streamForSelected?.connected
                      ? "Aktualizowane strumieniem SSE"
                      : selectedRequest
                        ? `Zakończone: ${formatRelativeTime(selectedRequest.finished_at)}`
                        : "Wybierz request z listy"
                  }
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
              {selectedRequest?.error_code && (
                <div className="alert alert--error mt-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="danger">{selectedRequest.error_code}</Badge>
                    {selectedRequest.error_stage && (
                      <Badge tone="neutral">{selectedRequest.error_stage}</Badge>
                    )}
                    {selectedRequest.error_retryable !== null &&
                      selectedRequest.error_retryable !== undefined && (
                        <Badge tone="neutral">
                          retryable: {selectedRequest.error_retryable ? "yes" : "no"}
                        </Badge>
                      )}
                  </div>
                  {selectedRequest.error_message && (
                    <p className="mt-2 text-xs text-rose-100">
                      {selectedRequest.error_message}
                    </p>
                  )}
                  {selectedRequest.error_details && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      {formatErrorDetails(selectedRequest.error_details).map((detail) => (
                        <Badge key={detail} tone="neutral">
                          {detail}
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}
              <div className="mt-4 rounded-2xl box-base p-4">
                <p className="text-xs uppercase tracking-wide text-zinc-500">
                  Wybrany krok
                </p>
                <h3 className="heading-h3 mt-2">
                  {focusedStep?.component ?? "—"}
                </h3>
                <p className="text-sm text-zinc-300">
                  {focusedStep?.action || focusedStep?.details || "Kliknij krok, aby zobaczyć treść."}
                </p>
                <dl className="mt-3 grid gap-3 text-xs text-zinc-400 sm:grid-cols-2">
                  <div>
                    <dt className="text-caption">
                      Status
                    </dt>
                    <dd className="text-white">
                      {focusedStep?.status ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-caption">
                      Timestamp
                    </dt>
                    <dd>{focusedStep?.timestamp ? formatTimestamp(focusedStep.timestamp) : "—"}</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-caption">
                      Detale
                    </dt>
                    <dd className="text-zinc-300">
                      {focusedStep?.details ?? "Brak dodatkowych danych."}
                    </dd>
                  </div>
                </dl>
                <div className="mt-3">
                  <p className="text-caption">JSON kroku</p>
                  <div className="mt-2 rounded-2xl box-muted p-3 text-xs text-emerald-50">
                    {focusedStep ? (
                      <pre className="max-h-48 overflow-auto whitespace-pre-wrap">
                        {JSON.stringify(focusedStep, null, 2)}
                      </pre>
                    ) : (
                      <p className="text-hint">Kliknij krok, aby zobaczyć surowe dane.</p>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          </div>
        </section>
      </div>
    </div>
  );
}

function adjustMermaidSizing(container: HTMLDivElement) {
  const svg = container.querySelector("svg");
  if (!svg) return;
  const width = svg.getAttribute("width");
  const height = svg.getAttribute("height");
  if (width && height && !svg.getAttribute("viewBox")) {
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.style.width = "100%";
  svg.style.height = "100%";
  svg.style.display = "block";
  svg.style.maxWidth = "none";
  svg.style.maxHeight = "none";
}

function autoFitDiagram(
  container: HTMLDivElement | null,
  setTransform: (x: number, y: number, scale: number, duration?: number, easing?: string) => void,
) {
  if (!container) return;
  const svg = container.querySelector("svg");
  if (!svg) return;
  const nodes = svg.querySelectorAll(".node");
  if (nodes.length === 0) return;
  let bbox: DOMRect | SVGRect;
  try {
    bbox = svg.getBBox();
  } catch {
    return;
  }
  if (!bbox.width || !bbox.height) return;
  const padding = 96;
  const availableWidth = Math.max(container.clientWidth - padding, 100);
  const availableHeight = Math.max(container.clientHeight - padding, 100);
  const scale = Math.min(availableWidth / bbox.width, availableHeight / bbox.height);
  const targetScale = Math.max(Math.min(scale, 3), 0.2);
  const offsetX = -bbox.x * targetScale + (container.clientWidth - bbox.width * targetScale) / 2;
  const offsetY = -bbox.y * targetScale + (container.clientHeight - bbox.height * targetScale) / 2;
  setTransform(offsetX, offsetY, targetScale, 200, "easeOut");
}

type HistoryStep = HistoryStepType;

const CONTRACT_ERROR_TERMS = [
  "execution_contract_violation",
  "kernel_required",
  "kernel is required",
  "requirements_missing",
  "capability_required",
  "execution_precheck",
  "execution.precheck.failed",
  "missing=kernel",
];

const isExecutionContractStep = (step: HistoryStep) => {
  const content = `${step.action ?? ""} ${step.details ?? ""}`.toLowerCase();
  if (content.includes("execution_contract_violation")) return true;
  return CONTRACT_ERROR_TERMS.some((term) => content.includes(term));
};

const filterSteps = (steps: HistoryStep[], query: string, contractOnly: boolean) => {
  const normalizedQuery = query.trim().toLowerCase();
  const textMatch = (step: HistoryStep) =>
    `${step.component ?? ""} ${step.action ?? ""} ${step.details ?? ""}`
      .toLowerCase()
      .includes(normalizedQuery);
  const contractMatch = (step: HistoryStep) =>
    `${step.action ?? ""} ${step.details ?? ""}`
      .toLowerCase()
      .includes("execution_contract_violation") ||
    CONTRACT_ERROR_TERMS.some((term) =>
      `${step.action ?? ""} ${step.details ?? ""}`
        .toLowerCase()
        .includes(term),
    );

  return steps.filter((step) => {
    if (contractOnly && !contractMatch(step)) return false;
    if (!normalizedQuery) return true;
    return textMatch(step);
  });
};

function buildSequenceDiagram(flow?: FlowTrace | null) {
  if (!flow) {
    return [
      "sequenceDiagram",
      "    autonumber",
      "    Note over User: Brak danych requestu",
    ].join("\n");
  }

  const steps = flow.steps || [];
  const lines: string[] = ["sequenceDiagram", "    autonumber"];
  const participants = new Set<string>(["User", "Orchestrator"]);

  steps.forEach((step) => {
    const component = sanitizeSequenceText(step.component || "");
    if (component && component !== "User") {
      participants.add(component);
    }
  });

  const participantAliases = new Map<string, string>();
  let participantIndex = 0;
  participants.forEach((participant) => {
    const alias = createParticipantAlias(participant, participantIndex++);
    participantAliases.set(participant, alias);
    if (participant === "User" || participant === "Orchestrator") {
      lines.push(`    participant ${alias} as ${participant}`);
    } else {
      const display = participant.replace(/"/g, "'");
      lines.push(`    participant ${alias} as "${display}"`);
    }
  });

  lines.push("");
  const prompt = truncateText(sanitizeSequenceText(flow.prompt || "Zapytanie"), 70);
  const userAlias = participantAliases.get("User") ?? "User";
  const orchestratorAlias = participantAliases.get("Orchestrator") ?? "Orchestrator";
  lines.push(`    ${userAlias}->>${orchestratorAlias}: ${prompt || "Zapytanie"}`);

  let lastComponent = orchestratorAlias;
  steps.forEach((step) => {
    const componentName = sanitizeSequenceText(step.component || "");
    const componentAlias = componentName
      ? participantAliases.get(componentName) || participantAliases.get("Orchestrator")
      : lastComponent;
    const component = componentAlias ?? lastComponent;
    const action = truncateText(
      sanitizeSequenceText(step.action || step.details || "Krok"),
      80,
    );
    const details = truncateText(sanitizeSequenceText(step.details || ""), 80);

    if (step.is_decision_gate || component.toLowerCase() === "decisiongate") {
      const message = details ? `${action}: ${details}` : action;
      lines.push(`    Note over ${component}: 🔀 ${message || "Decision Gate"}`);
      return;
    }

    const message = details ? `${action}: ${details}` : action;
    const arrow = statusToArrow(step.status);
    if (component !== lastComponent) {
      lines.push(`    ${lastComponent}${arrow}${component}: ${message}`);
      lastComponent = component;
    } else {
      lines.push(`    Note right of ${component}: ${message}`);
    }
  });

  if (flow.status === "COMPLETED") {
    lines.push(`    ${lastComponent}->>${userAlias}: ✅ Task completed`);
  } else if (flow.status === "FAILED") {
    lines.push(`    ${lastComponent}--x${userAlias}: ❌ Task failed`);
  } else if (flow.status === "PROCESSING") {
    lines.push(`    Note over ${lastComponent}: ⏳ Processing...`);
  }

  return lines.join("\n");
}

function createParticipantAlias(participant: string, index: number) {
  const base = participant.replace(/[^a-zA-Z0-9]/g, "_") || `P${index + 1}`;
  return `${base}_${index + 1}`;
}

function sanitizeSequenceText(value?: string | null) {
  if (!value) return "";
  return value
    .replace(/[<>]/g, "")
    .replace(/[\r\n]/g, " ")
    .replace(/[|]/g, "‖")
    .replace(/--/g, "–")
    .replace(/["]/g, "'")
    .trim();
}

function truncateText(value: string, limit: number) {
  if (!value) return "";
  return value.length > limit ? `${value.slice(0, limit)}...` : value;
}

function statusToArrow(status?: string) {
  if (!status) return "->>";
  const normalized = status.toLowerCase();
  if (normalized.includes("fail") || normalized.includes("error")) {
    return "--x";
  }
  return "->>";
}

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

function buildFlowchartDiagram(steps: HistoryStep[]) {
  if (!steps.length) {
    return "graph TD\nA[Brak kroków]";
  }
  const lines = [
    "graph TD",
    "classDef success fill:#052e1a,stroke:#22c55e,color:#d1fae5",
    "classDef failed fill:#331010,stroke:#f87171,color:#fee2e2",
    "classDef running fill:#0f172a,stroke:#38bdf8,color:#e0f2fe",
    "classDef default fill:#111827,stroke:#475569,color:#f8fafc",
    "classDef decision fill:#1f2937,stroke:#facc15,color:#fde68a,stroke-dasharray:5 5",
    "classDef note fill:#1c1917,stroke:#fbbf24,color:#fef3c7",
    "classDef contract fill:#2a1116,stroke:#fb7185,color:#ffe4e6",
  ];
  steps.forEach((step, idx) => {
    const nodeId = `S${idx}`;
    const safeComponent = sanitizeMermaidText(step.component || `Step ${idx + 1}`);
    const safeAction = sanitizeMermaidText(step.action || step.details || "");
    const label = safeAction ? `${safeComponent}\\n${safeAction}` : safeComponent;
    const statusClass = isExecutionContractStep(step)
      ? "contract"
      : statusToMermaidClass(step.status);
    const isDecision = (step.details || step.action || "")
      .toLowerCase()
      .includes("decision");
    lines.push(`${nodeId}["${label}"]:::${isDecision ? "decision" : statusClass}`);
    if (idx > 0) {
      const edgeLabel = sanitizeMermaidText(steps[idx - 1]?.status || "");
      lines.push(`S${idx - 1} -->${edgeLabel ? `|${edgeLabel}|` : ""} ${nodeId}`);
    }
    if (step.details && step.details.length > 80) {
      const noteId = `${nodeId}_note`;
      lines.push(`${noteId}["${sanitizeMermaidText(step.details, 90)}"]:::note`);
      lines.push(`${nodeId} -.-> ${noteId}`);
    }
  });
  return lines.join("\n");
}

function sanitizeMermaidText(value: string, limit = 60) {
  return value.replace(/[\n\r"]/g, " ").trim().slice(0, limit);
}

function statusToMermaidClass(status?: string) {
  if (!status) return "default";
  const normalized = status.toLowerCase();
  if (normalized.includes("success") || normalized.includes("complete")) return "success";
  if (normalized.includes("fail") || normalized.includes("error")) return "failed";
  if (normalized.includes("process") || normalized.includes("run")) return "running";
  return "default";
}

function formatErrorDetails(details: Record<string, unknown>): string[] {
  const entries: string[] = [];
  Object.entries(details).forEach(([key, value]) => {
    if (value === null || value === undefined) return;
    if (Array.isArray(value)) {
      if (value.length === 0) return;
      entries.push(`${key}: ${value.join(", ")}`);
      return;
    }
    if (typeof value === "object") {
      try {
        entries.push(`${key}: ${JSON.stringify(value)}`);
      } catch {
        entries.push(`${key}: [object]`);
      }
      return;
    }
    entries.push(`${key}: ${String(value)}`);
  });
  return entries.slice(0, 6);
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
    <div className="flex items-center gap-3 rounded-2xl box-base px-4 py-3">
      <span className="rounded-full border border-white/10 bg-black/40 p-2">
        {icon}
      </span>
      <div>
        <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
        <p className="text-xl font-semibold text-white">{primary}</p>
        <p className="text-hint">{hint}</p>
      </div>
    </div>
  );
}

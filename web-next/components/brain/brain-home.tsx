"use client";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
import { SectionHeading } from "@/components/ui/section-heading";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  fetchGraphFileInfo,
  fetchGraphImpact,
  triggerGraphScan,
  useGraphSummary,
  useKnowledgeGraph,
  useLessons,
  useLessonsStats,
} from "@/hooks/use-api";
import type { Lesson } from "@/lib/types";
import type { BrainInitialData } from "@/lib/server-data";
import type { TagEntry } from "@/components/brain/types";
import type cytoscapeType from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Radar, AlertTriangle } from "lucide-react";
import { LessonList } from "@/components/tasks/lesson-list";
import { LessonActions } from "@/components/brain/lesson-actions";
import { LessonStats } from "@/components/brain/lesson-stats";
import { FileAnalysisForm, FileAnalysisPanel } from "@/components/brain/file-analytics";
import { BrainMetricCard } from "@/components/brain/metric-card";
import { GraphFilterButtons, GraphFilterType } from "@/components/brain/graph-filters";

type SpecificFilter = Exclude<GraphFilterType, "all">;
import { GraphActionButtons } from "@/components/brain/graph-actions";

export function BrainHome({ initialData }: { initialData: BrainInitialData }) {
  const { data: liveSummary, refresh: refreshSummary } = useGraphSummary();
  const summary = liveSummary ?? initialData.summary ?? null;
  const {
    data: liveGraph,
    loading: liveGraphLoading,
    error: graphError,
    refresh: refreshGraph,
  } = useKnowledgeGraph();
  const graph = liveGraph ?? initialData.knowledgeGraph ?? null;
  const graphLoading = liveGraphLoading && !graph;
  const { data: liveLessons, refresh: refreshLessons } = useLessons(5);
  const lessons = liveLessons ?? initialData.lessons ?? null;
  const { data: liveLessonsStats } = useLessonsStats();
  const lessonsStats = liveLessonsStats ?? initialData.lessonsStats ?? null;
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [detailsSheetOpen, setDetailsSheetOpen] = useState(false);
  const [filters, setFilters] = useState<GraphFilterType[]>(["all"]);
  const [highlightTag, setHighlightTag] = useState<string | null>(null);
  const [scanMessage, setScanMessage] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [filePath, setFilePath] = useState("");
  const [fileInfo, setFileInfo] = useState<Record<string, unknown> | null>(null);
  const [impactInfo, setImpactInfo] = useState<Record<string, unknown> | null>(null);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);
  const [relations, setRelations] = useState<RelationEntry[]>([]);
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstanceRef = useRef<cytoscapeType.Core | null>(null);
  const recentOperations = useMemo(() => {
    const source = lessons?.lessons ?? [];
    return source.slice(0, 6).map((lesson, index) => ({
      id: lesson.id ?? `${lesson.title ?? "lesson"}-${lesson.created_at ?? index}`,
      title: lesson.title ?? "Operacja grafu",
      summary: lesson.summary || "Brak dodatkowych informacji.",
      timestamp: lesson.created_at || null,
      tags: lesson.tags ?? [],
    }));
  }, [lessons?.lessons]);
  const lessonTags = useMemo(() => aggregateTags(lessons?.lessons || []), [lessons]);
  const filteredLessons = useMemo(() => {
    if (!activeTag) return lessons?.lessons || [];
    return (lessons?.lessons || []).filter((lesson) => lesson.tags?.includes(activeTag));
  }, [lessons, activeTag]);
  const summaryStats = summary?.summary || summary;
  const legacySummaryStats = summaryStats as { last_updated?: string } | undefined;
  const legacySummary = summary as { last_updated?: string } | undefined;
  const summaryNodes = summaryStats?.nodes ?? summary?.nodes ?? "—";
  const summaryEdges = summaryStats?.edges ?? summary?.edges ?? "—";
  const summaryUpdated =
    summary?.lastUpdated || legacySummaryStats?.last_updated || legacySummary?.last_updated;
  const lessonsTotal = lessonsStats?.stats?.total_lessons ?? lessons?.lessons?.length ?? 0;
  const lessonStatsEntries = useMemo(() => {
    const raw = lessonsStats?.stats;
    if (!raw) return [];
    return Object.entries(raw)
      .slice(0, 4)
      .map(([key, value]) => ({
        label: key.replace(/_/g, " "),
        value: typeof value === "number" ? value : String(value),
        hint: "LessonsStore",
      }));
  }, [lessonsStats?.stats]);
  const brainMetrics = useMemo(
    () => [
      { label: "Węzły", value: summaryNodes ?? "—", hint: "Nodes w grafie" },
      { label: "Krawędzie", value: summaryEdges ?? "—", hint: "Połączenia grafu" },
      {
        label: "Lekcje",
        value: lessonsTotal ? lessonsTotal.toString() : "—",
        hint: "LessonsStore entries",
      },
    ],
    [lessonsTotal, summaryEdges, summaryNodes],
  );

  const applyFiltersToGraph = useCallback((nextFilters: GraphFilterType[]) => {
    const cy = cyInstanceRef.current;
    if (!cy) return;
    const activeFilters = nextFilters.filter(
      (item): item is SpecificFilter => item !== "all",
    );
    cy.nodes().style("display", "element");
    if (activeFilters.length > 0) {
      cy.nodes().forEach((node) => {
        const nodeType = node.data("type") as SpecificFilter | undefined;
        if (!nodeType || !activeFilters.includes(nodeType)) {
          node.style("display", "none");
        }
      });
    }
    cy.layout({ name: "cose", padding: 30, animate: false }).run();
  }, []);

  const handleFilterToggle = (value: GraphFilterType) => {
    setFilters((prev) => {
      if (value === "all") {
        applyFiltersToGraph(["all"]);
        return ["all"];
      }
      const withoutAll = prev.filter((item) => item !== "all");
      const exists = withoutAll.includes(value);
      const next = exists
        ? withoutAll.filter((item) => item !== value)
        : [...withoutAll, value];
      if (next.length === 0) {
        applyFiltersToGraph(["all"]);
        return ["all"];
      }
      applyFiltersToGraph(next);
      return next;
    });
  };

  const applyHighlightToNodes = (tagName: string | null) => {
    const cy = cyInstanceRef.current;
    if (!cy) return;
    cy.nodes().style("border-width", 1).style("border-color", "#1f2937");
    if (tagName) {
      cy.nodes().forEach((node) => {
        const props = node.data("properties") || {};
        const tags = (props.tags || []) as string[];
        if (tags.includes(tagName)) {
          node.style("border-width", 4).style("border-color", "#f59e0b");
        }
      });
    }
  };

  const resetNodeFocus = useCallback(() => {
    const cy = cyInstanceRef.current;
    if (!cy) return;
    cy.nodes().removeClass("highlighted neighbour faded");
  }, []);

  const focusNodeWithNeighbors = useCallback(
    (node: cytoscapeType.NodeSingular | null) => {
      const cy = cyInstanceRef.current;
      if (!cy || !node) return;
      resetNodeFocus();
      node.addClass("highlighted");
      const neighbors = node.neighborhood("node");
      neighbors.addClass("neighbour");
      cy.nodes()
        .filter((n) => !n.hasClass("highlighted") && !n.hasClass("neighbour"))
        .addClass("faded");
    },
    [resetNodeFocus],
  );

  const clearSelection = useCallback(() => {
    setSelected(null);
    setRelations([]);
    setDetailsSheetOpen(false);
    resetNodeFocus();
  }, [resetNodeFocus]);

  const handleTagToggle = (tagName: string) => {
    const next = highlightTag === tagName ? null : tagName;
    setHighlightTag(next);
    applyHighlightToNodes(next);
  };

  const handleFitGraph = () => {
    const cy = cyInstanceRef.current;
    if (!cy) return;
    cy.fit();
  };

  const handleScanGraph = async () => {
    setScanning(true);
    setScanMessage(null);
    try {
      const res = await triggerGraphScan();
      setScanMessage(res.message || "Skanowanie uruchomione.");
      refreshSummary();
    } catch (err) {
      setScanMessage(
        err instanceof Error ? err.message : "Nie udało się uruchomić skanu.",
      );
    } finally {
      setScanning(false);
    }
  };

  const handleFileFetch = async (mode: "info" | "impact") => {
    if (!filePath.trim()) {
      setFileMessage("Podaj ścieżkę pliku.");
      return;
    }
    setFileLoading(true);
    setFileMessage(null);
    try {
      if (mode === "info") {
        const res = await fetchGraphFileInfo(filePath.trim());
        setFileInfo(res.file_info || null);
        if (!res.file_info) {
          setFileMessage("Brak informacji o pliku.");
        }
      } else {
        const res = await fetchGraphImpact(filePath.trim());
        setImpactInfo(res.impact || null);
        if (!res.impact) {
          setFileMessage("Brak danych impact.");
        }
      }
    } catch (err) {
      setFileMessage(
        err instanceof Error ? err.message : "Nie udało się pobrać danych dla pliku.",
      );
    } finally {
      setFileLoading(false);
    }
  };

  useEffect(() => {
    let cyInstance: cytoscapeType.Core | null = null;
    const mount = async () => {
      if (!cyRef.current || !graph?.elements) return;
      const cytoscape = (await import("cytoscape")).default as typeof cytoscapeType;
      const elements = graph.elements as unknown as cytoscapeType.ElementsDefinition;
      const styles = [
        {
          selector: "node",
          style: {
            "background-color": (ele: cytoscapeType.NodeSingular) =>
              ele.data("type") === "agent"
                ? "#22c55e"
                : ele.data("type") === "memory"
                  ? "#f59e0b"
                  : "#6366f1",
            label: "data(label)",
            color: "#e5e7eb",
            "font-size": 11,
            "text-wrap": "wrap",
            "text-max-width": 120,
            "border-width": 1,
            "border-color": "#1f2937",
          },
        },
        {
          selector: "node.highlighted",
          style: {
            "border-width": 4,
            "border-color": "#c084fc",
            "background-color": "#6d28d9",
            "shadow-blur": 15,
            "shadow-color": "#7c3aed",
          },
        },
        {
          selector: "node.neighbour",
          style: {
            "border-width": 3,
            "border-color": "#fbbf24",
          },
        },
        {
          selector: "node.faded",
          style: {
            opacity: 0.2,
          },
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": 9,
            color: "#94a3b8",
            "text-background-opacity": 0.4,
            "text-background-color": "#0f172a",
            "text-background-padding": 2,
          },
        },
      ] as unknown as cytoscapeType.StylesheetJson;
      cyInstance = cytoscape({
        container: cyRef.current,
        elements,
        layout: { name: "cose", padding: 30, animate: false },
        style: styles,
      });
      cyInstance.on("tap", "node", (evt: cytoscapeType.EventObject) => {
        const data = evt.target.data() || {};
        setSelected(data);
        setDetailsSheetOpen(true);
        setHighlightTag(null);
        const edges = evt.target.connectedEdges();
        const relEntries: RelationEntry[] = edges.map((edge: cytoscapeType.EdgeSingular) => {
          const edgeData = edge.data();
          const source = edge.source();
          const target = edge.target();
          const isOut = source.id() === evt.target.id();
          const otherNode = isOut ? target : source;
          return {
            id: otherNode.id(),
            label: otherNode.data("label") || otherNode.id(),
            type: edgeData.label || edgeData.type,
            direction: isOut ? "out" : "in",
          };
        });
        setRelations(relEntries);
        focusNodeWithNeighbors(evt.target);
      });
      cyInstance.on("tap", (evt: cytoscapeType.EventObject) => {
        if (evt.target === cyInstance) {
          clearSelection();
        }
      });
      cyInstanceRef.current = cyInstance;
    };
    mount();
    return () => {
      if (cyInstance) {
        cyInstance.destroy();
      }
    };
  }, [graph, clearSelection, focusNodeWithNeighbors]);

  useEffect(() => {
    if (graph) {
      applyFiltersToGraph(filters);
    }
  }, [graph, filters, applyFiltersToGraph]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Brain / Graf wiedzy"
        title="Siatka wiedzy"
        description="Pełnoekranowy podgląd pamięci Venoma z filtrami agentów i lekcji."
        as="h1"
        size="lg"
        rightSlot={
          <div className="flex flex-wrap gap-2">
            <Badge tone="neutral">Węzły: {summaryNodes}</Badge>
            <Badge tone="neutral">Krawędzie: {summaryEdges}</Badge>
            <Badge tone="warning">Aktualizacja: {summaryUpdated ?? "—"}</Badge>
          </div>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        {brainMetrics.map((metric) => (
          <BrainMetricCard
            key={metric.label}
            label={metric.label}
            value={metric.value}
            hint={metric.hint}
          />
        ))}
      </div>

      <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-zinc-950/70 to-zinc-900/30 shadow-card">
        <div className="pointer-events-none absolute inset-0 grid-overlay" />
        <div
          ref={cyRef}
          data-testid="graph-container"
          className="relative h-[70vh] w-full"
        />
        {(graphLoading || graphError) && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/80 text-center text-sm text-white">
            {graphLoading ? (
              <Loader2 className="h-6 w-6 animate-spin text-emerald-300" />
            ) : (
              <AlertTriangle className="h-6 w-6 text-amber-300" />
            )}
            <p>
              {graphLoading
                ? "Ładuję graf wiedzy..."
                : "Brak danych z /api/v1/knowledge/graph."}
            </p>
            {graphError && (
              <button
                type="button"
                className="pointer-events-auto rounded-full border border-white/20 px-4 py-2 text-xs uppercase tracking-wider text-white hover:border-white/50"
                onClick={() => refreshGraph()}
              >
                Odśwież
              </button>
            )}
          </div>
        )}
        <div className="pointer-events-auto absolute left-6 top-6">
          <GraphFilterButtons selectedFilters={filters} onToggleFilter={handleFilterToggle} />
        </div>
        <div className="pointer-events-auto absolute right-6 top-6">
          <GraphActionButtons
            onFit={handleFitGraph}
            onScan={handleScanGraph}
            scanning={scanning}
            scanMessage={scanMessage}
          />
        </div>
        <div className="pointer-events-auto absolute left-6 bottom-6 flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-xs text-white backdrop-blur">
          {lessonTags.slice(0, 6).map((tag) => (
            <button
              key={tag.name}
              className={`rounded-full border px-3 py-1 ${
                highlightTag === tag.name
                  ? "border-amber-400/50 bg-amber-500/20"
                  : "border-white/10 bg-white/5 text-zinc-200"
              }`}
              onClick={() => handleTagToggle(tag.name)}
            >
              #{tag.name}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card-shell card-base p-4 text-sm">
          <h4 className="text-sm font-semibold text-white">Podsumowanie zaznaczenia</h4>
          {selected ? (
            <div className="mt-3 space-y-2 text-xs text-zinc-300">
              <p>
                <span className="text-zinc-400">Węzeł:</span>{" "}
                <span className="font-semibold text-white">
                  {String(selected.label || selected.id || "n/a")}
                </span>
              </p>
              <p>
                <span className="text-zinc-400">Typ:</span>{" "}
                <span className="font-semibold text-emerald-300">
                  {String((selected as Record<string, unknown>)?.type || "n/a")}
                </span>
              </p>
              <p>
                <span className="text-zinc-400">Relacje:</span>{" "}
                <span className="font-semibold">{relations.length}</span>
              </p>
              <p className="text-zinc-400">
                Kliknij „Szczegóły”, by zobaczyć pełne dane JSON oraz kierunki relacji.
              </p>
              <button
                className="rounded-full border border-white/20 px-3 py-1 text-[11px] uppercase tracking-[0.3em] text-white hover:border-white/50"
                onClick={() => {
                  if (!selected) return;
                  setDetailsSheetOpen(true);
                }}
              >
                Szczegóły
              </button>
            </div>
          ) : (
            <p className="mt-3 text-xs text-zinc-500">
              Wybierz węzeł w grafie, aby zobaczyć jego podstawowe dane.
            </p>
          )}
        </div>
        <div className="card-shell card-base p-4 text-sm">
          <h4 className="text-sm font-semibold text-white">Relacje (podgląd)</h4>
          {selected && relations.length > 0 ? (
            <ul className="mt-3 space-y-2 text-xs">
              {relations.slice(0, 5).map((rel) => (
                <li key={`${selected.id}-${rel.id}-${rel.direction}`} className="rounded-2xl border border-white/10 bg-black/30 px-3 py-2">
                  <span className="font-semibold text-white">{rel.label}</span>{" "}
                  <span className="text-zinc-400">
                    ({rel.direction === "out" ? "→" : "←"} {rel.type || "link"})
                  </span>
                </li>
              ))}
              {relations.length > 5 && (
                <p className="text-[11px] uppercase tracking-[0.3em] text-zinc-500">
                  +{relations.length - 5} kolejnych relacji w panelu szczegółów.
                </p>
              )}
            </ul>
          ) : (
            <p className="mt-3 text-xs text-zinc-500">
              Brak relacji (lub nie wybrano węzła).
            </p>
          )}
        </div>
        <div className="card-shell card-base p-4 text-sm">
          <h4 className="text-sm font-semibold text-white">Ostatnie operacje grafu</h4>
          {recentOperations.length === 0 ? (
            <p className="mt-3 text-xs text-zinc-500">
              Brak zarejestrowanych operacji. Uruchom skan lub odśwież lekcje.
            </p>
          ) : (
            <ul className="mt-3 space-y-2 text-xs text-zinc-300">
              {recentOperations.map((op) => (
                <li
                  key={op.id}
                  className="rounded-2xl border border-white/10 bg-black/20 px-3 py-2 shadow-inner"
                >
                  <p className="font-semibold text-white">{op.title}</p>
                  <p className="text-[11px] text-zinc-500">
                    {formatOperationTimestamp(op.timestamp)}
                  </p>
                  <p className="text-xs text-zinc-400">{op.summary}</p>
                  {op.tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {op.tags.slice(0, 3).map((tag) => (
                        <span
                          key={`${op.id}-${tag}`}
                          className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.3em] text-emerald-200"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <Panel
        title="Lekcje i operacje grafu"
        description="LessonsStore + akcje skanowania grafu."
        action={
          <button
            className="rounded-lg border border-[--color-border] bg-white/5 px-3 py-2 text-xs text-white hover:bg-white/10"
            onClick={() => refreshLessons()}
          >
            Odśwież lekcje
          </button>
        }
      >
        <div className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-white">
            <h4 className="text-sm font-semibold text-white">Statystyki Lessons</h4>
            {lessonStatsEntries.length > 0 ? (
              <div className="mt-3">
                <LessonStats entries={lessonStatsEntries} />
              </div>
            ) : (
              <EmptyState
                icon={<Radar className="h-4 w-4" />}
                title="Brak statystyk"
                description="LessonsStore może być offline lub puste."
                className="mt-3 text-xs"
              />
            )}
          </div>
          <div>
            <h4 className="text-sm font-semibold text-white">Ostatnie lekcje</h4>
            <LessonActions tags={lessonTags} activeTag={activeTag} onSelect={setActiveTag} />
            <div className="mt-3">
              <LessonList lessons={filteredLessons} emptyMessage="Lekcje pojawią się po zapisaniu nowych wpisów w LessonsStore." />
            </div>
          </div>
        </div>
      </Panel>

      <Panel title="Analiza pliku" description="Pobierz informacje z grafu (file info / impact).">
        <div className="space-y-4">
          <FileAnalysisForm
            filePath={filePath}
            onPathChange={setFilePath}
            loading={fileLoading}
            onFileInfo={() => handleFileFetch("info")}
            onImpact={() => handleFileFetch("impact")}
            message={fileMessage}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <FileAnalysisPanel label="File info" payload={fileInfo} />
            <FileAnalysisPanel label="Impact" payload={impactInfo} />
          </div>
        </div>
      </Panel>

      <Sheet
        open={detailsSheetOpen && selected !== null}
        onOpenChange={(open) => {
          setDetailsSheetOpen(open);
          if (!open) {
            clearSelection();
          }
        }}
      >
        <SheetContent className="bg-zinc-950/95 text-white">
          <SheetHeader>
            <SheetTitle>{String(selected?.label || selected?.id || "Node")}</SheetTitle>
            <SheetDescription>
              Typ: {String((selected as Record<string, unknown>)?.type || "n/a")}
            </SheetDescription>
          </SheetHeader>
          {selected ? (
            <div className="space-y-4 text-sm text-zinc-300">
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Właściwości</p>
                <pre className="mt-2 max-h-60 overflow-auto rounded-xl border border-white/10 bg-black/40 p-3 text-xs text-zinc-100">
                  {JSON.stringify(selected, null, 2)}
                </pre>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wide text-zinc-500">Relacje</p>
                {relations.length === 0 ? (
                  <p className="text-xs text-zinc-500">Brak relacji.</p>
                ) : (
                  <ul className="mt-2 space-y-2 text-xs">
                    {relations.map((rel) => (
                      <li
                        key={`${selected.id}-${rel.id}-${rel.direction}`}
                        className="rounded-xl border border-white/10 bg-white/5 px-3 py-2"
                      >
                        <span className="font-semibold text-white">{rel.label}</span>
                        <span className="text-zinc-400">
                          {" "}
                          ({rel.direction === "out" ? "→" : "←"} {rel.type || "link"})
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Kliknij węzeł, by zobaczyć szczegóły.</p>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function formatOperationTimestamp(value: string | null) {
  if (!value) return "brak daty";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("pl-PL", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  });
}

type RelationEntry = {
  id: string;
  label?: string;
  type?: string;
  direction: "in" | "out";
};

const aggregateTags = (lessons: Lesson[]): TagEntry[] => {
  const counters: Record<string, number> = {};
  lessons.forEach((lesson) => {
    (lesson.tags || []).forEach((tag) => {
      counters[tag] = (counters[tag] || 0) + 1;
    });
  });
  return Object.entries(counters)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);
};

export default BrainHome;

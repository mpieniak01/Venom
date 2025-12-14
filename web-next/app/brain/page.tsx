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
import type cytoscapeType from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";
import { Radar } from "lucide-react";
import { LessonList } from "@/components/tasks/lesson-list";
import { LessonActions } from "@/components/brain/lesson-actions";
import { LessonStats } from "@/components/brain/lesson-stats";
import { FileAnalysisForm, FileAnalysisPanel } from "@/components/brain/file-analytics";
import { BrainMetricCard } from "@/components/brain/metric-card";
import { GraphFilterButtons, GraphFilterType } from "@/components/brain/graph-filters";
import { GraphActionButtons } from "@/components/brain/graph-actions";

export default function BrainPage() {
  const { data: summary, refresh: refreshSummary } = useGraphSummary();
  const { data: graph } = useKnowledgeGraph();
  const { data: lessons, refresh: refreshLessons } = useLessons(5);
  const { data: lessonsStats } = useLessonsStats();
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [filter, setFilter] = useState<GraphFilterType>("all");
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

  const handleFilterChange = (value: GraphFilterType) => {
    setFilter(value);
    const cy = cyInstanceRef.current;
    if (!cy) return;
    cy.nodes().style("display", "element");
    if (value !== "all") {
      cy.nodes().forEach((node) => {
        if (node.data("type") !== value) {
          node.style("display", "none");
        }
      });
    }
    cy.layout({ name: "cose", padding: 30, animate: false }).run();
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
      });
      cyInstanceRef.current = cyInstance;
    };
    mount();
    return () => {
      if (cyInstance) {
        cyInstance.destroy();
      }
    };
  }, [graph]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Brain / Knowledge Graph"
        title="Mind Mesh"
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
        <div className="pointer-events-auto absolute left-6 top-6">
          <GraphFilterButtons activeFilter={filter} onFilterChange={handleFilterChange} />
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
        open={selected !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelected(null);
            setRelations([]);
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

type RelationEntry = {
  id: string;
  label?: string;
  type?: string;
  direction: "in" | "out";
};

export type TagEntry = { name: string; count: number };

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

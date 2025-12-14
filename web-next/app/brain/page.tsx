"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Panel } from "@/components/ui/panel";
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
import { Filter, Scan, Layers, Sparkles, Radar } from "lucide-react";

export default function BrainPage() {
  const { data: summary, refresh: refreshSummary } = useGraphSummary();
  const { data: graph } = useKnowledgeGraph();
  const { data: lessons, refresh: refreshLessons } = useLessons(5);
  const { data: lessonsStats } = useLessonsStats();
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [filter, setFilter] = useState<"all" | "agent" | "memory" | "file" | "function">(
    "all",
  );
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
  const summaryNodes = summaryStats?.nodes ?? summary?.nodes ?? "—";
  const summaryEdges = summaryStats?.edges ?? summary?.edges ?? "—";
  const summaryUpdated =
    summary?.lastUpdated || summaryStats?.last_updated || summary?.last_updated;

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
      cyInstance = cytoscape({
        container: cyRef.current,
        elements: graph.elements,
        layout: { name: "cose", padding: 30, animate: false },
        style: [
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
        ],
      });
      cyInstance.on("tap", "node", (evt) => {
        const data = evt.target.data() || {};
        setSelected(data);
        setHighlightTag(null);
        const edges = evt.target.connectedEdges();
        const relEntries: RelationEntry[] = edges.map((edge) => {
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
      <div className="glass-panel flex flex-wrap items-center justify-between gap-6">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-zinc-500">
            Brain / Knowledge Graph
          </p>
          <h1 className="mt-2 text-3xl font-semibold text-white">Mind Mesh</h1>
          <p className="text-sm text-zinc-400">
            Pełnoekranowy podgląd pamięci Venoma z filtrami agentów i lekcji.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge tone="neutral">Węzły: {summaryNodes}</Badge>
          <Badge tone="neutral">Krawędzie: {summaryEdges}</Badge>
          <Badge tone="warning">
            Aktualizacja: {summaryUpdated ?? "—"}
          </Badge>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-zinc-950/70 to-zinc-900/30 shadow-card">
        <div className="pointer-events-none absolute inset-0 grid-overlay" />
        <div
          ref={cyRef}
          data-testid="graph-container"
          className="relative h-[70vh] w-full"
        />
        <div className="pointer-events-auto absolute left-6 top-6 flex flex-wrap gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-xs text-white backdrop-blur">
          {(["all", "agent", "memory", "file", "function"] as const).map((type) => (
            <Button
              key={type}
              size="xs"
              variant={filter === type ? "primary" : "outline"}
              className="px-3"
              onClick={() => {
                setFilter(type);
                const cy = cyInstanceRef.current;
                if (!cy) return;
                cy.nodes().style("display", "element");
                if (type !== "all") {
                  cy.nodes().forEach((n) => {
                    if (n.data("type") !== type) {
                      n.style("display", "none");
                    }
                  });
                }
                cy.layout({ name: "cose", padding: 30, animate: false }).run();
              }}
            >
              <Filter className="h-3 w-3" />
              {type}
            </Button>
          ))}
        </div>
        <div className="pointer-events-auto absolute right-6 top-6 flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              const cy = cyInstanceRef.current;
              if (!cy) return;
              cy.fit();
            }}
          >
            <Layers className="h-4 w-4" />
            Dopasuj
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={async () => {
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
            }}
            disabled={scanning}
          >
            <Scan className="h-4 w-4" />
            {scanning ? "Skanuję..." : "Skanuj graf"}
          </Button>
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
              onClick={() => {
                const next = highlightTag === tag.name ? null : tag.name;
                setHighlightTag(next);
                const cy = cyInstanceRef.current;
                if (!cy) return;
                cy.nodes().style("border-width", 1).style("border-color", "#1f2937");
                if (next) {
                  cy.nodes().forEach((node) => {
                    const props = node.data("properties") || {};
                    const tags = (props.tags || []) as string[];
                    if (tags.includes(next)) {
                      node.style("border-width", 4).style("border-color", "#f59e0b");
                    }
                  });
                }
              }}
            >
              #{tag.name}
            </button>
          ))}
        </div>
        {scanMessage && (
          <div className="pointer-events-none absolute right-6 bottom-6 rounded-full border border-white/10 bg-black/60 px-4 py-1 text-xs text-zinc-300">
            {scanMessage}
          </div>
        )}
      </div>

      <Panel
        title="Lekcje i operacje grafu"
        description="LessonsStore + akcje skanowania grafu."
        action={
          <button
            className="rounded-lg bg-white/5 px-3 py-2 text-xs text-white border border-[--color-border] hover:bg-white/10"
            onClick={() => refreshLessons()}
          >
            Odśwież lekcje
          </button>
        }
      >
        <div className="space-y-4">
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-3 text-sm text-[--color-muted]">
            <h4 className="text-sm font-semibold text-white">Statystyki Lessons</h4>
            {lessonsStats?.stats ? (
              <JsonPreview data={lessonsStats.stats} />
            ) : (
              <EmptyState
                icon={<Radar className="h-4 w-4" />}
                title="Brak statystyk"
                description="LessonsStore może być offline lub puste."
                className="text-xs"
              />
            )}
          </div>
          <div>
            <h4 className="text-sm font-semibold text-white">Ostatnie lekcje</h4>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <button
                className={`rounded-full px-3 py-1 ${
                  activeTag === null
                    ? "bg-[--color-accent]/30 text-white"
                    : "bg-white/5 text-white border border-[--color-border]"
                }`}
                onClick={() => setActiveTag(null)}
              >
                Wszystkie
              </button>
              {lessonTags.map((tag) => (
                <button
                  key={tag.name}
                  className={`rounded-full px-3 py-1 ${
                    activeTag === tag.name
                      ? "bg-[--color-accent]/30 text-white"
                      : "bg-white/5 text-white border border-[--color-border]"
                  }`}
                  onClick={() => setActiveTag(tag.name)}
                >
                  #{tag.name} ({tag.count})
                </button>
              ))}
            </div>
            <ul className="mt-2 space-y-2 text-sm text-[--color-muted]">
              {filteredLessons.length === 0 && (
                <EmptyState
                  icon={<Sparkles className="h-4 w-4" />}
                  title="Brak lekcji"
                  description="Lekcje pojawią się po zapisaniu nowych wpisów w LessonsStore."
                  className="text-sm"
                />
              )}
              {filteredLessons.map((lesson) => (
                <li
                  key={lesson.id || lesson.title}
                  className="rounded border border-[--color-border] bg-white/5 px-3 py-2"
                >
                  <span className="font-semibold text-white">{lesson.title}</span>
                  <p className="text-xs">{lesson.summary || "Brak opisu."}</p>
                  {lesson.tags && lesson.tags.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {lesson.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-white/10 px-2 py-[2px] text-[10px] uppercase tracking-wide text-[--color-muted]"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Panel>

      <Panel title="Analiza pliku" description="Pobierz informacje z grafu (file info / impact).">
        <div className="space-y-3">
          <div className="flex flex-wrap gap-2">
            <input
              className="w-full max-w-md rounded-lg border border-[--color-border] bg-white/5 px-3 py-2 text-sm text-white outline-none focus:border-[--color-accent]"
              placeholder="Nazwa pliku, np. venom_core/api/routes/system.py"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
            />
            <Button
              variant="outline"
              size="sm"
              disabled={fileLoading}
              onClick={() => handleFileFetch("info")}
            >
              ℹ️ Info
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={fileLoading}
              onClick={() => handleFileFetch("impact")}
            >
              🌐 Impact
            </Button>
          </div>
          {fileMessage && <p className="text-xs text-[--color-muted]">{fileMessage}</p>}
          <div className="grid gap-3 md:grid-cols-2">
            <div className="rounded-xl border border-[--color-border] bg-black/30 p-3 text-xs text-[--color-muted]">
              <p className="text-sm font-semibold text-white">File info</p>
              {fileInfo ? <JsonPreview data={fileInfo} /> : <p>Brak danych.</p>}
            </div>
            <div className="rounded-xl border border-[--color-border] bg-black/30 p-3 text-xs text-[--color-muted]">
              <p className="text-sm font-semibold text-white">Impact</p>
              {impactInfo ? <JsonPreview data={impactInfo} /> : <p>Brak danych.</p>}
            </div>
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
        <SheetContent side="right" className="bg-zinc-950/95 text-white">
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

function JsonPreview({ data }: { data: Record<string, unknown> }) {
  return (
    <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-[--color-border] bg-black/40 p-2 text-xs text-slate-200">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

type RelationEntry = {
  id: string;
  label?: string;
  type?: string;
  direction: "in" | "out";
};

type TagEntry = { name: string; count: number };

const aggregateTags = (lessons: Lesson[]): TagEntry[] => {
  const counters: Record<string, number> = {};
  lessons.forEach((lesson) => {
    (lesson.tags || []).forEach((tag) => {
      counters[tag] = (counters[tag] || 0) + 1;
    });
  });
  return Object.entries(counters).map(([name, count]) => ({ name, count }));
};

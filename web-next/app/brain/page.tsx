"use client";

import { Badge } from "@/components/ui/badge";
import { Panel } from "@/components/ui/panel";
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

export default function BrainPage() {
  const { data: summary, refresh: refreshSummary } = useGraphSummary();
  const { data: graph } = useKnowledgeGraph();
  const { data: lessons, refresh: refreshLessons } = useLessons(5);
  const { data: lessonsStats } = useLessonsStats();
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [filter, setFilter] = useState<"all" | "agent" | "memory" | "file" | "function">(
    "all",
  );
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
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl border border-[--color-border] bg-[--color-panel]/70 p-6 shadow-xl shadow-black/40">
        <p className="text-sm text-[--color-muted]">Brain / Knowledge Graph</p>
        <h1 className="mt-2 text-3xl font-semibold">Wizualizacja pamięci</h1>
        <p className="mt-2 text-sm text-[--color-muted]">
          Widok grafu zasila /api/v1/graph/summary i /api/v1/graph/scan. Rendering
          planowany z użyciem Cytoscape (dynamic import).
        </p>
        <div className="mt-4 flex gap-2">
          <Badge tone="neutral">/graph/summary</Badge>
          <Badge tone="neutral">
            węzły: {summaryNodes} / krawędzie: {summaryEdges}
          </Badge>
          <Badge tone="warning">Cytoscape (client)</Badge>
        </div>
      </div>

      <Panel title="Statystyki grafu" description="Dane z /api/v1/graph/summary.">
        <div className="grid gap-3 sm:grid-cols-3">
          <StatRow label="Węzły" value={summaryNodes} />
          <StatRow label="Krawędzie" value={summaryEdges} />
          <StatRow label="Ostatnia aktualizacja" value={summaryUpdated ?? "—"} />
        </div>
      </Panel>

      <Panel
        title="Obszary filtrów"
        description="Tagi, typy węzłów, ostatnie aktualizacje — do wpięcia w API grafu."
      >
        <div className="flex flex-wrap gap-2 text-sm text-[--color-muted]">
          <Badge tone="neutral">kod</Badge>
          <Badge tone="neutral">workflow</Badge>
          <Badge tone="neutral">dokumentacja</Badge>
          <Badge tone="neutral">lekcje</Badge>
        </div>
      </Panel>

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
              <p className="text-xs">Brak statystyk lub LessonsStore offline.</p>
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
                <li className="rounded border border-[--color-border] bg-white/5 px-3 py-2">
                  Brak danych lub LessonsStore offline.
                </li>
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
          <div className="rounded-xl border border-[--color-border] bg-black/30 p-4 text-sm text-[--color-muted]">
            <p className="text-white font-semibold">Skanowanie grafu</p>
            <p className="text-xs">
              Uruchom /api/v1/graph/scan aby zaktualizować graf po zmianach w kodzie.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                className="rounded-lg bg-[--color-accent]/40 px-4 py-2 text-xs font-semibold text-white hover:bg-[--color-accent]/60 disabled:opacity-60"
                disabled={scanning}
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
              >
                {scanning ? "Skanowanie..." : "Skanuj graf"}
              </button>
            </div>
            {scanMessage && (
              <p className="mt-2 text-xs text-[--color-muted]">{scanMessage}</p>
            )}
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
            <button
              className="rounded-lg border border-[--color-border] px-4 py-2 text-xs text-white hover:bg-white/10 disabled:opacity-60"
              disabled={fileLoading}
              onClick={() => handleFileFetch("info")}
            >
              ℹ️ Info
            </button>
            <button
              className="rounded-lg border border-[--color-border] px-4 py-2 text-xs text-white hover:bg-white/10 disabled:opacity-60"
              disabled={fileLoading}
              onClick={() => handleFileFetch("impact")}
            >
              🌐 Impact
            </button>
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

      <Panel
        title="Widok grafu"
        description="Miejsce na komponent grafu (Cytoscape) + szczegóły węzła."
      >
        <div className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-2 rounded-xl border border-[--color-border] bg-white/5 p-2 text-sm text-[--color-muted]">
            <div className="mb-2 flex flex-wrap items-center gap-2 px-2">
              {(["all", "agent", "memory", "file", "function"] as const).map((type) => (
                <button
                  key={type}
                  className={`rounded-lg px-3 py-1 text-xs capitalize ${
                    filter === type
                      ? "bg-[--color-accent]/30 text-white border border-[--color-border]"
                      : "bg-white/5 text-white border border-[--color-border] hover:bg-white/10"
                  }`}
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
                  {type}
                </button>
              ))}
              <button
                className="rounded-lg bg-white/5 px-3 py-1 text-xs text-white border border-[--color-border] hover:bg-white/10"
                onClick={() => {
                  const cy = cyInstanceRef.current;
                  if (!cy) return;
                  cy.fit();
                }}
              >
                Dopasuj
              </button>
            </div>
            <div ref={cyRef} className="h-[480px] w-full rounded-lg bg-[#0b1220]" />
          </div>
          <div className="rounded-xl border border-[--color-border] bg-white/5 p-6 space-y-3">
            <h4 className="text-sm font-semibold text-white">Szczegóły węzła</h4>
            {selected ? (
              <div className="mt-2 space-y-2 text-sm text-[--color-muted]">
                <p className="text-white">{String(selected.label || selected.id)}</p>
                <p className="text-xs">Typ: {String(selected.type || "n/a")}</p>
                <details className="rounded-lg border border-[--color-border] bg-black/30 p-2">
                  <summary className="cursor-pointer text-xs text-white">
                    Właściwości
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto text-xs text-slate-200">
                    {JSON.stringify(selected, null, 2)}
                  </pre>
                </details>
                <div>
                  <p className="text-xs uppercase tracking-wide text-[--color-muted]">
                    Relacje
                  </p>
                  {relations.length === 0 ? (
                    <p className="text-xs">Brak relacji.</p>
                  ) : (
                    <ul className="text-xs space-y-1">
                      {relations.map((rel) => (
                        <li
                          key={`${selected.id}-${rel.id}-${rel.direction}`}
                          className="rounded border border-[--color-border] bg-white/5 px-2 py-1"
                        >
                          <span className="font-semibold text-white">{rel.label}</span>
                          <span className="text-[--color-muted]">
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
              <p className="mt-2 text-sm text-[--color-muted]">
                Kliknij węzeł, aby zobaczyć szczegóły.
              </p>
            )}
          </div>
        </div>
      </Panel>
    </div>
  );
}

type StatRowProps = {
  label: string;
  value: string | number;
};

function StatRow({ label, value }: StatRowProps) {
  return (
    <div className="rounded-xl border border-[--color-border] bg-white/5 p-4">
      <p className="text-xs uppercase tracking-wide text-[--color-muted]">
        {label}
      </p>
      <p className="mt-2 text-xl font-semibold">{value}</p>
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

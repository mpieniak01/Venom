"use client";

import { Brain, Loader2, Radar, AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type cytoscapeType from "cytoscape";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { SectionHeading } from "@/components/ui/section-heading";
import { Panel } from "@/components/ui/panel";
import { EmptyState } from "@/components/ui/empty-state";
import { useToast } from "@/components/ui/toast";

import {
  fetchGraphFileInfo,
  fetchGraphImpact,
  triggerGraphScan,
  pinMemoryEntry,
  deleteMemoryEntry,
  clearSessionMemory,
  useLessons,
  useLessonsStats,
} from "@/hooks/use-api";
import { useProjectionTrigger } from "@/hooks/use-projection";
import { useTranslation } from "@/lib/i18n";
import type { BrainInitialData } from "@/lib/server-data";
import type { Lesson } from "@/lib/types";

import { LessonList } from "@/components/tasks/lesson-list";
import { LessonActions } from "@/components/brain/lesson-actions";
import { LessonStats } from "@/components/brain/lesson-stats";
import { FileAnalysisForm, FileAnalysisPanel } from "@/components/brain/file-analytics";
import { GraphFilterButtons, GraphFilterType } from "@/components/brain/graph-filters";
import { GraphActionButtons } from "@/components/brain/graph-actions";
import { HygienePanel } from "@/components/brain/hygiene-panel";

// New components and hooks
import { useBrainGraphLogic } from "./hooks/use-brain-graph-logic";
import { useTopicColors } from "./hooks/use-topic-colors";
import { GraphStats } from "./graph-stats";
import { GraphLegend } from "./graph-legend";
import { RecentOperations } from "./recent-operations";
import { RelationList, RelationEntry } from "./relation-list";
import { BrainSelectionSummary } from "./selection-summary";
import { BrainDetailsSheetContent } from "./details-sheet-content";
import { formatOperationTimestamp } from "./utils/graph-utils";

type SpecificFilter = Exclude<GraphFilterType, "all">;

export function BrainHome({ initialData }: Readonly<{ initialData: BrainInitialData }>) {
  const t = useTranslation();
  const { pushToast } = useToast();
  const projection = useProjectionTrigger();

  // Tabs
  const [activeTab, setActiveTab] = useState<"repo" | "memory" | "hygiene">("memory");

  // Filter & UI State
  const [showMemoryLayer, setShowMemoryLayer] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [includeLessons, setIncludeLessons] = useState(false);
  const [memorySessionFilter, setMemorySessionFilter] = useState<string>("");
  const [memoryOnlyPinned, setMemoryOnlyPinned] = useState(false);
  const [topicFilter, setTopicFilter] = useState("");
  const [flowMode, setFlowMode] = useState<"default" | "flow">("flow");
  const [filters, setFilters] = useState<GraphFilterType[]>(["all"]);
  const [highlightTag, setHighlightTag] = useState<string | null>(null);

  // Data Logic Hook
  const {
    mergedGraph,
    loading: graphLoading,
    error: graphError,
    refreshGraph,
    refreshMemoryGraph,
    setMemoryGraphOverride,
    memoryGraphStats,
  } = useBrainGraphLogic(
    initialData.knowledgeGraph,
    activeTab,
    showMemoryLayer,
    memorySessionFilter,
    memoryOnlyPinned,
    includeLessons
  );

  const isMemoryEmpty =
    activeTab === "memory" &&
    showMemoryLayer &&
    !graphLoading &&
    ((memoryGraphStats?.nodes ?? 0) <= 1);

  // Selection state
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [detailsSheetOpen, setDetailsSheetOpen] = useState(false);
  const [relations, setRelations] = useState<RelationEntry[]>([]);
  const [memoryActionPending, setMemoryActionPending] = useState<string | null>(null);
  const [memoryWipePending, setMemoryWipePending] = useState(false);

  // File analysis state
  const [filePath, setFilePath] = useState("");
  const [fileInfo, setFileInfo] = useState<Record<string, unknown> | null>(null);
  const [impactInfo, setImpactInfo] = useState<Record<string, unknown> | null>(null);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  // Metadata
  const { data: liveLessons, refresh: refreshLessons } = useLessons(5);
  const lessons = liveLessons ?? initialData.lessons ?? null;
  const { data: liveLessonsStats } = useLessonsStats();
  const lessonsStats = liveLessonsStats ?? initialData.lessonsStats ?? null;

  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstanceRef = useRef<cytoscapeType.Core | null>(null);

  // Derived Values
  const summary = initialData.summary;
  const renderedNodes = mergedGraph?.elements?.nodes?.length ?? 0;
  const renderedEdges = mergedGraph?.elements?.edges?.length ?? 0;
  const summaryNodes = mergedGraph?.stats?.nodes ?? summary?.nodes ?? "—";
  const summaryEdges = mergedGraph?.stats?.edges ?? summary?.edges ?? "—";

  const lessonTags = useMemo(() => {
    const counters: Record<string, number> = {};
    (lessons?.lessons || []).forEach((lesson) => {
      (lesson.tags || []).forEach((tag) => {
        counters[tag] = (counters[tag] || 0) + 1;
      });
    });
    return Object.entries(counters)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 8);
  }, [lessons]);

  const recentOperations = useMemo(() => {
    return (lessons?.lessons || []).slice(0, 6).map((lesson, index) => ({
      id: lesson.id ?? `${lesson.title ?? "lesson"}-${index}`,
      title: lesson.title ?? t("brain.recentOperations.defaultTitle"),
      summary: lesson.summary || t("brain.recentOperations.defaultSummary"),
      timestamp: lesson.created_at || null,
      tags: lesson.tags ?? [],
    }));
  }, [lessons?.lessons, t]);

  // Handlers
  const handleFilterToggle = (value: GraphFilterType) => {
    setFilters((prev) => {
      if (value === "all") return ["all"];
      const withoutAll = prev.filter((item) => item !== "all");
      const next = withoutAll.includes(value)
        ? withoutAll.filter((item) => item !== value)
        : [...withoutAll, value];
      return next.length === 0 ? ["all"] : next;
    });
  };

  const handleClearSelection = useCallback(() => {
    setSelected(null);
    setRelations([]);
    setDetailsSheetOpen(false);
    if (cyInstanceRef.current) {
      cyInstanceRef.current.nodes().removeClass("highlighted neighbour faded");
    }
  }, []);

  const handlePinMemory = async (entryId: string, pinned: boolean) => {
    try {
      setMemoryActionPending(entryId);
      await pinMemoryEntry(entryId, pinned);
      pushToast(pinned ? t("brain.toasts.pinSuccess") : t("brain.toasts.unpinSuccess"), "success");
      refreshMemoryGraph();
    } catch (err) {
      pushToast(t("brain.toasts.pinError"), "error");
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleDeleteMemory = async (entryId: string) => {
    if (!globalThis.window.confirm(t("brain.toasts.deleteConfirm"))) return;
    try {
      setMemoryActionPending(entryId);
      await deleteMemoryEntry(entryId);
      handleClearSelection();
      refreshMemoryGraph();
      pushToast(t("brain.toasts.deleteSuccess"), "success");
    } catch (err) {
      pushToast(t("brain.toasts.deleteError"), "error");
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleClearSessionMemory = async () => {
    if (!memorySessionFilter.trim()) {
      pushToast(t("brain.toasts.missingSessionId"), "warning");
      return;
    }
    try {
      setMemoryWipePending(true);
      const resp = await clearSessionMemory(memorySessionFilter.trim());
      pushToast(t("brain.toasts.clearSessionSuccess", { id: resp.session_id, num: resp.deleted_vectors }), "success");
      setMemoryGraphOverride({ elements: { nodes: [], edges: [] }, stats: { nodes: 0, edges: 0 } });
      await refreshMemoryGraph();
      setMemoryGraphOverride(null);
    } catch (err) {
      pushToast(t("brain.toasts.clearSessionError"), "error");
    } finally {
      setMemoryWipePending(false);
    }
  };

  const handleFileFetch = async (mode: "info" | "impact") => {
    if (!filePath.trim()) {
      setFileMessage(t("brain.file.missingPath"));
      return;
    }
    setFileLoading(true);
    setFileMessage(null);
    try {
      if (mode === "info") {
        const res = await fetchGraphFileInfo(filePath.trim());
        setFileInfo(res.file_info || null);
      } else {
        const res = await fetchGraphImpact(filePath.trim());
        setImpactInfo(res.impact || null);
      }
    } catch (err) {
      setFileMessage(err instanceof Error ? err.message : t("brain.file.fetchError"));
    } finally {
      setFileLoading(false);
    }
  };

  const [scanning, setScanning] = useState(false);
  const handleScanGraph = async () => {
    setScanning(true);
    try {
      await triggerGraphScan();
      pushToast(t("brain.toasts.scanStarted"), "success");
    } catch (err) {
      pushToast(t("brain.toasts.scanError"), "error");
    } finally {
      setScanning(false);
    }
  };

  // Effect to load cytoscape and setup instance
  useEffect(() => {
    let cy: cytoscapeType.Core | null = null;
    const setup = async () => {
      if (!cyRef.current || !mergedGraph?.elements) return;
      const cytoscape = (await import("cytoscape")).default;
      cy = cytoscape({
        container: cyRef.current,
        elements: mergedGraph.elements as any,
        style: [
          { selector: "node", style: { label: "data(label)", "background-color": "#6366f1", color: "#fff", "font-size": 10 } },
          { selector: "node.highlighted", style: { "border-width": 4, "border-color": "#c084fc" } },
          { selector: "edge", style: { "curve-style": "bezier", "target-arrow-shape": "triangle", width: 2, "line-color": "#475569" } }
        ] as any,
        layout: { name: "preset" } as any
      });
      cy.on("tap", "node", (evt) => {
        const node = evt.target;
        setSelected(node.data());
        setDetailsSheetOpen(true);
        cy?.nodes().removeClass("highlighted");
        node.addClass("highlighted");
        setRelations(node.connectedEdges().map((e: any) => ({
          id: e.target().id() === node.id() ? e.source().id() : e.target().id(),
          label: e.target().id() === node.id() ? e.source().data("label") : e.target().data("label"),
          type: e.data("label") || e.data("type"),
          direction: e.source().id() === node.id() ? "out" : "in"
        })));
      });
      cy.on("tap", (evt) => { if (evt.target === cy) handleClearSelection(); });
      cyInstanceRef.current = cy;
    };
    setup();
    return () => cy?.destroy();
  }, [mergedGraph, handleClearSelection]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Brain / Knowledge Graph"
        title={t("brain.home.title")}
        description={t("brain.home.description")}
        as="h1"
        size="lg"
        rightSlot={<Brain className="page-heading-icon" />}
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/40 p-1.5">
          {["memory", "repo", "hygiene"].map((tab) => (
            <Button
              key={tab}
              size="sm"
              variant={activeTab === tab ? "secondary" : "ghost"}
              className="rounded-full px-4"
              onClick={() => setActiveTab(tab as any)}
            >
              {t(`brain.tabs.${tab}`)}
            </Button>
          ))}
        </div>
      </div>

      <GraphStats
        summaryNodes={summaryNodes}
        summaryEdges={summaryEdges}
        summaryUpdated={summary?.lastUpdated}
        activeTab={activeTab}
        memoryLimit={100}
        renderedNodes={renderedNodes}
        sourceTotalNodes={Number(summaryNodes) || renderedNodes}
        renderedEdges={renderedEdges}
        sourceTotalEdges={Number(summaryEdges) || renderedEdges}
      />

      {activeTab === "hygiene" ? (
        <HygienePanel />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-zinc-950/70 to-zinc-900/30 shadow-card">
            <div ref={cyRef} className="relative h-[70vh] w-full" />
            {isMemoryEmpty && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-black/70 text-center">
                <p className="text-sm text-zinc-400">{t("brain.file.noData")}</p>
                <Button onClick={handleScanGraph} disabled={scanning}>{t("brain.actions.scan")}</Button>
              </div>
            )}
            {graphLoading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/80">
                <Loader2 className="h-6 w-6 animate-spin text-emerald-300" />
              </div>
            )}
            <div className="absolute left-6 top-6"><GraphFilterButtons selectedFilters={filters} onToggleFilter={handleFilterToggle} /></div>
            <div className="absolute right-6 top-6"><GraphActionButtons onFit={() => cyInstanceRef.current?.fit()} onScan={handleScanGraph} scanning={scanning} /></div>
          </div>

          <GraphLegend activeTab={activeTab} showEdgeLabels={showEdgeLabels} />

          <div className="grid gap-4 lg:grid-cols-3">
            <BrainSelectionSummary selected={selected} relations={relations} onOpenDetails={() => setDetailsSheetOpen(true)} />
            <RelationList selectedId={String(selected?.id || "")} relations={relations} />
            <RecentOperations operations={recentOperations} />
          </div>
        </>
      )}

      {activeTab !== "hygiene" && (
        <>
          <Panel title={t("brain.lessons.panelTitle")} description={t("brain.lessons.panelDescription")} action={<Button size="sm" onClick={() => refreshLessons()}>{t("brain.lessons.refresh")}</Button>}>
            <div className="space-y-4">
              <LessonStats entries={[]} />
              <LessonActions tags={lessonTags} activeTag={highlightTag} onSelect={setHighlightTag} />
              <LessonList lessons={lessons?.lessons || []} />
            </div>
          </Panel>

          <Panel title={t("brain.file.title")} description={t("brain.file.description")}>
            <FileAnalysisForm filePath={filePath} onPathChange={setFilePath} loading={fileLoading} onFileInfo={() => handleFileFetch("info")} onImpact={() => handleFileFetch("impact")} message={fileMessage} />
            <div className="grid gap-4 md:grid-cols-2">
              <FileAnalysisPanel label="File info" payload={fileInfo} />
              <FileAnalysisPanel label="Impact" payload={impactInfo} />
            </div>
          </Panel>

          <Sheet open={detailsSheetOpen} onOpenChange={setDetailsSheetOpen}>
            <BrainDetailsSheetContent selected={selected} relations={relations} memoryActionPending={memoryActionPending} onPin={handlePinMemory} onDelete={handleDeleteMemory} />
          </Sheet>
        </>
      )}
    </div>
  );
}

export default BrainHome;

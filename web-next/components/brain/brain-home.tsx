"use client";

import { Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type cytoscapeType from "cytoscape";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import {
  fetchGraphFileInfo,
  fetchGraphImpact,
  triggerGraphScan,
  pinMemoryEntry,
  deleteMemoryEntry,
  clearSessionMemory,
  useLessons,
  useGraphSummary,
} from "@/hooks/use-api";
import { useProjectionTrigger } from "@/hooks/use-projection";
import { useTranslation } from "@/lib/i18n";
import type { BrainInitialData } from "@/lib/server-data";
import type { BrainGraphViewMode } from "@/lib/types";

import { GraphFilterButtons, GraphFilterType } from "@/components/brain/graph-filters";
import { GraphActionButtons } from "@/components/brain/graph-actions";
import { HygienePanel } from "@/components/brain/hygiene-panel";
import { BrainHeader } from "@/components/brain/brain-header";
import { BrainInsightsPanel } from "@/components/brain/brain-insights-panel";
import { BrainLessonsPanel } from "@/components/brain/brain-lessons-panel";
import { BrainFilePanel } from "@/components/brain/brain-file-panel";
import { BrainViewControls, type BrainViewPreset } from "@/components/brain/brain-view-controls";

import { useBrainGraphLogic } from "./hooks/use-brain-graph-logic";
import { useTopicColors } from "./hooks/use-topic-colors";
import { GraphStats } from "./graph-stats";
import { GraphLegend } from "./graph-legend";
import type { RelationEntry } from "./relation-list";
import { BrainDetailsSheetContent } from "./details-sheet-content";
import { emitBrainMetric } from "@/lib/brain-telemetry";

const BRAIN2_FOCUS_ENABLED = process.env.NEXT_PUBLIC_BRAIN2_FOCUS_ENABLED !== "false";

export function BrainHome({ initialData }: Readonly<{ initialData: BrainInitialData }>) {
  const t = useTranslation();
  const { pushToast } = useToast();
  useProjectionTrigger();

  const shellStartedAtRef = useRef<number>(Date.now());
  const graphReadyReportedRef = useRef(false);

  const [activeTab, setActiveTab] = useState<"repo" | "memory" | "hygiene">("memory");
  const [showMemoryLayer, setShowMemoryLayer] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [includeLessons, setIncludeLessons] = useState(false);
  const [memorySessionFilter, setMemorySessionFilter] = useState<string>("");
  const [memoryOnlyPinned, setMemoryOnlyPinned] = useState(false);
  const [layoutName, setLayoutName] = useState<"preset" | "cola" | "cose">("preset");
  const [flowMode, setFlowMode] = useState<"flow" | "default">("flow");
  const [topicFilter, setTopicFilter] = useState("");
  const [filters, setFilters] = useState<GraphFilterType[]>(["all"]);
  const [highlightTag, setHighlightTag] = useState<string | null>(null);

  const [graphViewMode, setGraphViewMode] = useState<BrainGraphViewMode>(
    BRAIN2_FOCUS_ENABLED ? "overview" : "full",
  );
  const [focusSeedId, setFocusSeedId] = useState<string | undefined>(undefined);
  const [includeIsolates, setIncludeIsolates] = useState(false);

  const {
    mergedGraph,
    loading: graphLoading,
    refreshMemoryGraph,
    setMemoryGraphOverride,
    memoryGraphStats,
  } = useBrainGraphLogic({
    initialKnowledge: initialData.knowledgeGraph,
    activeTab,
    showMemoryLayer,
    memorySessionFilter,
    memoryOnlyPinned,
    includeLessons,
    flowMode,
    topicFilter,
    graphViewMode,
    focusSeedId,
    maxHops: graphViewMode === "focus" ? 2 : 1,
    includeIsolates,
    limitNodes: graphViewMode === "overview" ? 220 : undefined,
  });

  const isMemoryEmpty =
    activeTab === "memory" &&
    showMemoryLayer &&
    !graphLoading &&
    ((memoryGraphStats?.nodes ?? 0) <= 1);

  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);
  const [detailsSheetOpen, setDetailsSheetOpen] = useState(false);
  const [relations, setRelations] = useState<RelationEntry[]>([]);
  const [memoryActionPending, setMemoryActionPending] = useState<string | null>(null);
  const [memoryWipePending, setMemoryWipePending] = useState(false);

  const [filePath, setFilePath] = useState("");
  const [fileInfo, setFileInfo] = useState<Record<string, unknown> | null>(null);
  const [impactInfo, setImpactInfo] = useState<Record<string, unknown> | null>(null);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(false);

  const { data: liveLessons, loading: lessonsLoading, refresh: refreshLessons } = useLessons(5);
  const { data: liveSummary, loading: summaryLoading } = useGraphSummary(0);
  const lessons = liveLessons ?? initialData.lessons ?? null;
  const summary = liveSummary ?? initialData.summary;
  const { colorFromTopic } = useTopicColors();

  const lessonStatsEntries = useMemo(() => {
    if (!lessons) return [];
    const total = lessons.count || 0;
    const tags = new Set<string>();
    lessons.lessons.forEach((lesson) => lesson.tags?.forEach((tag) => tags.add(tag)));
    return [
      { label: t("brain.stats.total"), value: total },
      { label: t("brain.stats.tags"), value: tags.size },
    ];
  }, [lessons, t]);

  const filteredLessons = useMemo(() => {
    if (!lessons) return [];
    if (!highlightTag) return lessons.lessons;
    return lessons.lessons.filter((lesson) => lesson.tags?.includes(highlightTag));
  }, [lessons, highlightTag]);

  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstanceRef = useRef<cytoscapeType.Core | null>(null);
  const colaWarningShownRef = useRef(false);

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

  const recentOperations = useMemo(
    () =>
      (lessons?.lessons || []).slice(0, 6).map((lesson, index) => ({
        id: lesson.id ?? `${lesson.title ?? "lesson"}-${index}`,
        title: lesson.title ?? t("brain.recentOperations.defaultTitle"),
        summary: lesson.summary || t("brain.recentOperations.defaultSummary"),
        timestamp: lesson.created_at || null,
        tags: lesson.tags ?? [],
      })),
    [lessons?.lessons, t],
  );

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

  const handleViewModeChange = useCallback((mode: BrainGraphViewMode) => {
    setGraphViewMode(mode);
    if (mode === "focus") {
      emitBrainMetric("brain_focus_mode_usage", 1);
    }
    if (mode === "full") {
      emitBrainMetric("brain_full_mode_usage", 1);
    }
  }, []);

  const applyPreset = useCallback(
    (preset: BrainViewPreset) => {
      if (preset === "session") {
        if (memorySessionFilter.trim()) {
          setFocusSeedId(`session:${memorySessionFilter.trim()}`);
        }
        setGraphViewMode("focus");
        return;
      }
      if (preset === "topic") {
        setGraphViewMode("focus");
        setFocusSeedId(undefined);
        return;
      }
      if (preset === "pinned") {
        setMemoryOnlyPinned(true);
        setGraphViewMode("overview");
        return;
      }
      setIncludeLessons(true);
      setGraphViewMode("overview");
    },
    [memorySessionFilter],
  );

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
    } catch {
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
    } catch {
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
    } catch {
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
    } catch {
      pushToast(t("brain.toasts.scanError"), "error");
    } finally {
      setScanning(false);
    }
  };

  const mapRelationsForNode = useCallback((node: cytoscapeType.NodeSingular): RelationEntry[] => {
    return node.connectedEdges().map((edge: cytoscapeType.EdgeSingular) => {
      const targetIsNode = edge.target().id() === node.id();
      return {
        id: targetIsNode ? edge.source().id() : edge.target().id(),
        label: (targetIsNode ? edge.source().data("label") : edge.target().data("label")) as string,
        type: (edge.data("label") || edge.data("type")) as string,
        direction: edge.source().id() === node.id() ? "out" : "in",
      };
    });
  }, []);

  useEffect(() => {
    emitBrainMetric("brain_first_shell_ms", Date.now() - shellStartedAtRef.current);
  }, []);

  useEffect(() => {
    if (!graphLoading && mergedGraph?.elements && !graphReadyReportedRef.current) {
      graphReadyReportedRef.current = true;
      emitBrainMetric("brain_graph_ready_ms", Date.now() - shellStartedAtRef.current);
    }
  }, [graphLoading, mergedGraph]);

  useEffect(() => {
    let cy: cytoscapeType.Core | null = null;
    const setup = async () => {
      if (!cyRef.current || !mergedGraph?.elements) return;
      const cytoscape = (await import("cytoscape")).default;
      let resolvedLayoutName = layoutName;
      const hasPresetPositions = (
        mergedGraph.elements.nodes as Array<{ position?: { x?: number; y?: number } }>
      ).some((node) => {
        const x = node.position?.x;
        const y = node.position?.y;
        return Number.isFinite(x) && Number.isFinite(y);
      });

      if (layoutName === "preset" && !hasPresetPositions) {
        resolvedLayoutName = "cose";
      }

      if (layoutName === "cola") {
        resolvedLayoutName = "cose";
        if (!colaWarningShownRef.current) {
          pushToast(t("brain.toasts.layoutColaUnavailable"), "warning");
          colaWarningShownRef.current = true;
        }
      }

      cy = cytoscape({
        container: cyRef.current,
        elements: mergedGraph.elements as unknown as cytoscapeType.ElementDefinition[],
        style: [
          {
            selector: "node",
            style: {
              label: "data(label)",
              "background-color":
                (ele: cytoscapeType.NodeSingular) => colorFromTopic(ele.data("topic")) || "#6366f1",
              color: "#fff",
              "font-size": 10,
              "text-opacity": 0.8,
              "text-valign": "center",
              "text-halign": "center",
            },
          },
          { selector: "node.highlighted", style: { "border-width": 4, "border-color": "#c084fc" } },
          {
            selector: "edge",
            style: {
              label: showEdgeLabels ? "data(label)" : "",
              "font-size": 9,
              color: "#cbd5e1",
              "text-background-color": "#09090b",
              "text-background-opacity": 0.8,
              "text-background-padding": "2px",
              "curve-style": "bezier",
              "target-arrow-shape": "triangle",
              width: 2,
              "line-color": "#475569",
            },
          },
        ],
        layout:
          resolvedLayoutName === "cose"
            ? {
                name: "cose",
                animate: true,
                fit: true,
                padding: 30,
                nodeRepulsion: 7000,
                idealEdgeLength: 90,
              }
            : { name: "preset", fit: true, padding: 30 },
      });

      cy.on("tap", "node", (evt: cytoscapeType.EventObject) => {
        const node = evt.target;
        const nodeData = node.data();
        const nodeId = String(nodeData.id || "");
        if (nodeId) {
          setFocusSeedId(nodeId);
        }
        setSelected(nodeData);
        setDetailsSheetOpen(true);
        cy?.nodes().removeClass("highlighted");
        node.addClass("highlighted");
        setRelations(mapRelationsForNode(node));
      });

      cy.on("tap", (evt) => {
        if (evt.target === cy) handleClearSelection();
      });

      cyInstanceRef.current = cy;
    };

    setup();
    return () => {
      if (cy) cy.destroy();
    };
  }, [mergedGraph, handleClearSelection, showEdgeLabels, layoutName, colorFromTopic, mapRelationsForNode, pushToast, t]);

  const modeLabels: Record<BrainGraphViewMode, string> = {
    overview: t("brain.viewMode.overview"),
    focus: t("brain.viewMode.focus"),
    full: t("brain.viewMode.full"),
  };

  return (
    <div className="space-y-6 pb-10">
      <BrainHeader
        eyebrow={t("brain.home.eyebrow")}
        title={t("brain.home.title")}
        description={t("brain.home.description")}
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-full border border-white/10 bg-black/40 p-1.5">
          {(["memory", "repo", "hygiene"] as const).map((tab) => (
            <Button
              key={tab}
              size="sm"
              variant={activeTab === tab ? "secondary" : "ghost"}
              className="rounded-full px-4"
              data-testid={`${tab}-tab`}
              onClick={() => setActiveTab(tab)}
            >
              {t(`brain.tabs.${tab}`)}
            </Button>
          ))}
        </div>
      </div>

      {BRAIN2_FOCUS_ENABLED && activeTab !== "hygiene" ? (
        <BrainViewControls
          title={t("brain.viewMode.title")}
          mode={graphViewMode}
          modeLabels={modeLabels}
          presetLabels={{
            session: t("brain.presets.session"),
            topic: t("brain.presets.topic"),
            pinned: t("brain.presets.pinned"),
            recent: t("brain.presets.recent"),
          }}
          onModeChange={handleViewModeChange}
          onPresetApply={applyPreset}
        />
      ) : null}

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
        loading={summaryLoading || graphLoading}
      />

      {activeTab === "hygiene" ? (
        <HygienePanel />
      ) : (
        <>
          <div
            className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-zinc-950/70 to-zinc-900/30 shadow-card"
            data-testid="brain-graph-panel"
          >
            <div ref={cyRef} data-testid="graph-container" className="relative h-[70vh] w-full" />
            {isMemoryEmpty && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-black/70 text-center">
                <p className="text-sm text-zinc-400">{t("brain.file.noData")}</p>
                <Button onClick={handleScanGraph} disabled={scanning}>
                  {t("brain.actions.scan")}
                </Button>
              </div>
            )}
            {graphLoading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/70" data-testid="brain-graph-loading">
                <Loader2 className="h-6 w-6 animate-spin text-emerald-300" />
              </div>
            )}
            <div className="absolute left-6 top-6 flex flex-col gap-3">
              <GraphFilterButtons selectedFilters={filters} onToggleFilter={handleFilterToggle} />

              <div className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-black/70 p-3 backdrop-blur lg:w-[260px]" data-testid="brain-filter-panel">
                <div className="flex items-center justify-between">
                  <Label htmlFor="show-memory" className="text-xs text-zinc-300">{t("brain.filters.memoryLayer")}</Label>
                  <Switch id="show-memory" checked={showMemoryLayer} onCheckedChange={setShowMemoryLayer} />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="show-labels" className="text-xs text-zinc-300">{t("brain.filters.edgeLabels")}</Label>
                  <Switch id="show-labels" checked={showEdgeLabels} onCheckedChange={setShowEdgeLabels} />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="include-isolates" className="text-xs text-zinc-300">{t("brain.filters.includeIsolates")}</Label>
                  <Switch id="include-isolates" checked={includeIsolates} onCheckedChange={setIncludeIsolates} />
                </div>
                <div className="flex items-center justify-between">
                  <Label htmlFor="layout-name" className="text-xs text-zinc-300">{t("brain.filters.layout")}</Label>
                  <select
                    id="layout-name"
                    value={layoutName}
                    onChange={(e) => setLayoutName(e.target.value as "preset" | "cola" | "cose")}
                    className="h-6 rounded bg-black/50 px-1 text-[10px] text-zinc-300 border-white/10"
                    data-testid="brain-layout-select"
                  >
                    <option value="preset">{t("brain.filters.layoutPreset")}</option>
                    <option value="cola">{t("brain.filters.layoutCola")}</option>
                    <option value="cose">{t("brain.filters.layoutCose")}</option>
                  </select>
                </div>
                {showMemoryLayer && (
                  <>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="only-pinned" className="text-xs text-zinc-300">{t("brain.filters.pinnedOnly")}</Label>
                      <Switch id="only-pinned" checked={memoryOnlyPinned} onCheckedChange={setMemoryOnlyPinned} />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="include-lessons" className="text-xs text-zinc-300">{t("brain.filters.includeLessons")}</Label>
                      <Switch id="include-lessons" checked={includeLessons} onCheckedChange={setIncludeLessons} />
                    </div>
                    <div className="flex items-center justify-between">
                      <Label htmlFor="flow-mode" className="text-xs text-zinc-300">{t("brain.filters.flowMode")}</Label>
                      <Switch id="flow-mode" checked={flowMode === "flow"} onCheckedChange={(val) => setFlowMode(val ? "flow" : "default")} />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="session-filter" className="text-xs text-zinc-300">{t("brain.filters.sessionId")}</Label>
                      <Input
                        id="session-filter"
                        value={memorySessionFilter}
                        onChange={(e) => setMemorySessionFilter(e.target.value)}
                        className="h-7 text-xs bg-black/50 border-white/10"
                        placeholder={t("brain.filters.sessionPlaceholder")}
                        data-testid="brain-session-filter"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="topic-filter" className="text-xs text-zinc-300">{t("brain.filters.topic")}</Label>
                      <Input
                        id="topic-filter"
                        value={topicFilter}
                        onChange={(e) => setTopicFilter(e.target.value)}
                        className="h-7 text-xs bg-black/50 border-white/10"
                        placeholder={t("brain.filters.topicPlaceholder")}
                        data-testid="brain-topic-filter"
                      />
                    </div>
                  </>
                )}
              </div>
            </div>
            <div className="absolute right-6 top-6">
              <GraphActionButtons onFit={() => cyInstanceRef.current?.fit()} onScan={handleScanGraph} scanning={scanning} />
            </div>
          </div>

          <GraphLegend activeTab={activeTab} showEdgeLabels={showEdgeLabels} />

          <BrainInsightsPanel
            selected={selected}
            relations={relations}
            recentOperations={recentOperations}
            onOpenDetails={() => setDetailsSheetOpen(true)}
          />
        </>
      )}

      {activeTab !== "hygiene" && (
        <>
          <BrainLessonsPanel
            title={t("brain.lessons.panelTitle")}
            description={t("brain.lessons.panelDescription")}
            refreshLabel={t("brain.lessons.refresh")}
            lessonStatsEntries={lessonStatsEntries}
            lessonTags={lessonTags}
            highlightTag={highlightTag}
            lessons={filteredLessons || []}
            loading={lessonsLoading}
            onRefresh={() => refreshLessons()}
            onSelectTag={setHighlightTag}
          />

          <BrainFilePanel
            title={t("brain.file.title")}
            description={t("brain.file.description")}
            filePath={filePath}
            loading={fileLoading}
            message={fileMessage}
            fileInfo={fileInfo}
            impactInfo={impactInfo}
            onPathChange={setFilePath}
            onFileInfo={() => handleFileFetch("info")}
            onImpact={() => handleFileFetch("impact")}
          />

          <Sheet
            open={detailsSheetOpen}
            onOpenChange={(open) => {
              setDetailsSheetOpen(open);
              if (!open) handleClearSelection();
            }}
          >
            <BrainDetailsSheetContent
              selected={selected}
              relations={relations}
              memoryActionPending={memoryActionPending}
              onPin={handlePinMemory}
              onDelete={handleDeleteMemory}
              memoryWipePending={memoryWipePending}
              onClearSession={handleClearSessionMemory}
            />
          </Sheet>
        </>
      )}
    </div>
  );
}

export default BrainHome;

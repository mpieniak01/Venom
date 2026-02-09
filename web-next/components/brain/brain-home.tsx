"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  useMemoryGraph,
  useGraphSummary,
  useKnowledgeGraph,
  useLessons,
  useLessonsStats,
} from "@/hooks/use-api";
import type { KnowledgeGraph, Lesson } from "@/lib/types";
import type { BrainInitialData } from "@/lib/server-data";
import type { TagEntry } from "@/components/brain/types";
import type cytoscapeType from "cytoscape";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Brain, Loader2, Radar, AlertTriangle } from "lucide-react";
import { LessonList } from "@/components/tasks/lesson-list";
import { LessonActions } from "@/components/brain/lesson-actions";
import { LessonStats } from "@/components/brain/lesson-stats";
import { FileAnalysisForm, FileAnalysisPanel } from "@/components/brain/file-analytics";
import { GraphFilterButtons, GraphFilterType } from "@/components/brain/graph-filters";
import { clearSessionMemory, deleteMemoryEntry, pinMemoryEntry } from "@/hooks/use-api";
import { useToast } from "@/components/ui/toast";
import { KNOWLEDGE_GRAPH_LIMIT, MEMORY_GRAPH_LIMIT } from "@/hooks/use-api";
import { useProjectionTrigger } from "@/hooks/use-projection";
import { useTranslation } from "@/lib/i18n";

type SpecificFilter = Exclude<GraphFilterType, "all">;
import { GraphActionButtons } from "@/components/brain/graph-actions";

import { HygienePanel } from "@/components/brain/hygiene-panel";

type GraphNode = { data?: Record<string, unknown>; position?: { x?: number; y?: number } };
type GraphEdge = { data?: Record<string, unknown> };
type PreparedGraphElements = { nodes: GraphNode[]; edges: GraphEdge[] };

function getNodeData(node: unknown): Record<string, unknown> {
  const data = (node as { data?: unknown }).data;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    return data as Record<string, unknown>;
  }
  return {};
}

function getStringField(data: Record<string, unknown>, key: string): string {
  const value = data[key];
  return typeof value === "string" ? value : "";
}

function getNodeId(node: unknown): string {
  return getStringField(getNodeData(node), "id");
}

function sortByTimestamp(a: unknown, b: unknown): number {
  const aMeta = getNodeData(a).meta as Record<string, unknown> | undefined;
  const bMeta = getNodeData(b).meta as Record<string, unknown> | undefined;
  const aTs = typeof aMeta?.timestamp === "string" ? Date.parse(aMeta.timestamp) : Number.NaN;
  const bTs = typeof bMeta?.timestamp === "string" ? Date.parse(bMeta.timestamp) : Number.NaN;
  if (!Number.isNaN(aTs) && !Number.isNaN(bTs)) return aTs - bTs;
  return getStringField(getNodeData(a), "label").localeCompare(getStringField(getNodeData(b), "label"));
}

function isAssistantEntry(node: unknown): boolean {
  const data = getNodeData(node);
  const label = typeof data.label === "string" ? data.label : "";
  const meta = (data.meta as Record<string, unknown> | undefined) || {};
  let roleHint = "";
  if (typeof meta.role === "string") {
    roleHint = meta.role;
  } else if (typeof meta.author === "string") {
    roleHint = meta.author;
  } else if (typeof meta.speaker === "string") {
    roleHint = meta.speaker;
  }
  return /assistant|asystent|venom/i.test(roleHint) || /^(assistant|asystent|venom)\b/i.test(label);
}

function collectEntrySessions(edgesSource: GraphEdge[]): Map<string, Set<string>> {
  const entrySessions = new Map<string, Set<string>>();
  edgesSource.forEach((edge) => {
    const data = getNodeData(edge);
    const source = getStringField(data, "source");
    const target = getStringField(data, "target");
    if (source.startsWith("session:")) {
      const sessionId = source.slice("session:".length);
      if (target) {
        const bucket = entrySessions.get(target) || new Set<string>();
        bucket.add(sessionId);
        entrySessions.set(target, bucket);
      }
    }
    if (target.startsWith("session:")) {
      const sessionId = target.slice("session:".length);
      if (source) {
        const bucket = entrySessions.get(source) || new Set<string>();
        bucket.add(sessionId);
        entrySessions.set(source, bucket);
      }
    }
  });
  return entrySessions;
}

function computeMemoryPositions(
  filteredNodesSource: GraphNode[],
  entrySessions: Map<string, Set<string>>,
): Map<string, { x: number; y: number }> {
  const positionMap = new Map<string, { x: number; y: number }>();
  const sessionNodes = filteredNodesSource.filter((node) => getNodeData(node).memory_kind === "session");
  const entryNodes = filteredNodesSource.filter((node) => {
    const kind = getNodeData(node).memory_kind;
    return kind !== "session" && kind !== "user" && kind !== "lesson";
  });
  const lessonNodes = filteredNodesSource.filter((node) => getNodeData(node).memory_kind === "lesson");
  const sessionCenters = new Map<string, number>();
  const sharedEntries: typeof entryNodes = [];
  const sharedBuckets = new Map<string, typeof entryNodes>();
  const entriesBySession = new Map<string, typeof entryNodes>();
  const orphanEntries: typeof entryNodes = [];
  entryNodes.forEach((node) => {
    const data = getNodeData(node);
    const sessionId = typeof data.session_id === "string" ? data.session_id : "";
    if (sessionId) {
      const bucket = entriesBySession.get(sessionId) || [];
      bucket.push(node);
      entriesBySession.set(sessionId, bucket);
    } else {
      orphanEntries.push(node);
    }
  });

  const sessionSpacing = 260;
  const entrySpacing = 90;
  const sessionStartY = -((sessionNodes.length - 1) * sessionSpacing) / 2;
  sessionNodes.forEach((node, index) => {
    const data = getNodeData(node);
    const id = String(data.id ?? "");
    const sessionId = typeof data.session_id === "string" ? data.session_id : "";
    const centerY = sessionStartY + index * sessionSpacing;
    if (id) positionMap.set(id, { x: -160, y: centerY });
    if (sessionId) sessionCenters.set(sessionId, centerY);
    const entries = (entriesBySession.get(sessionId) || []).slice().sort(sortByTimestamp);
    const entryStartY = centerY - ((entries.length - 1) * entrySpacing) / 2;
    entries.forEach((entry, entryIndex) => {
      const entryId = getNodeId(entry);
      if (!entryId) return;
      const sessions = entrySessions.get(entryId);
      if (sessions && sessions.size > 1) {
        sharedEntries.push(entry);
        const signature = Array.from(sessions)
          .sort((a, b) => a.localeCompare(b))
          .join("|");
        const bucket = sharedBuckets.get(signature) || [];
        bucket.push(entry);
        sharedBuckets.set(signature, bucket);
        return;
      }
      const baseX = 60;
      const stepX = 40;
      const assistantBump = isAssistantEntry(entry) ? 20 : 0;
      positionMap.set(entryId, {
        x: baseX + entryIndex * stepX + assistantBump,
        y: entryStartY + entryIndex * entrySpacing,
      });
    });
  });

  if (sharedEntries.length > 0) {
    sharedBuckets.forEach((bucket, signature) => {
      const sessions = signature.split("|").filter(Boolean);
      const centers = sessions
        .map((id) => sessionCenters.get(id))
        .filter((val): val is number => typeof val === "number");
      const baseY =
        centers.length > 0
          ? centers.reduce((acc, val) => acc + val, 0) / centers.length
          : sessionStartY;
      const sortedShared = bucket.slice().sort(sortByTimestamp);
      const sharedStartY = baseY - ((sortedShared.length - 1) * entrySpacing) / 2;
      sortedShared.forEach((entry, index) => {
        const entryId = getNodeId(entry);
        if (!entryId) return;
        positionMap.set(entryId, { x: 10, y: sharedStartY + index * entrySpacing });
      });
    });
  }

  if (orphanEntries.length > 0) {
    const baseY = sessionStartY + sessionNodes.length * sessionSpacing + 80;
    const sortedOrphans = orphanEntries.slice().sort(sortByTimestamp);
    const startY = baseY - ((sortedOrphans.length - 1) * entrySpacing) / 2;
    sortedOrphans.forEach((node, index) => {
      const id = getNodeId(node);
      if (!id) return;
      positionMap.set(id, { x: isAssistantEntry(node) ? 180 : 60, y: startY + index * entrySpacing });
    });
  }

  if (lessonNodes.length > 0) {
    const lessonStartY =
      sessionStartY +
      sessionNodes.length * sessionSpacing +
      (orphanEntries.length > 0 ? orphanEntries.length * entrySpacing + 160 : 120);
    lessonNodes.forEach((node, index) => {
      const id = getNodeId(node);
      if (id) positionMap.set(id, { x: 220, y: lessonStartY + index * 140 });
    });
  }

  return positionMap;
}

function prepareGraphElements(
  mergedGraph: KnowledgeGraph | null,
  colorFromTopic: (topic?: string) => string | undefined,
  hasPresetPositions: boolean,
  isMemoryLayout: boolean,
): PreparedGraphElements | null {
  if (!mergedGraph?.elements) return null;
  const nodesSource = mergedGraph.elements.nodes || [];
  const edgesSource = mergedGraph.elements.edges || [];
  const filteredNodesSource = nodesSource.filter((node) => getNodeData(node).memory_kind !== "user");
  const removedNodeIds = new Set(
    nodesSource.filter((node) => getNodeData(node).memory_kind === "user").map((node) => getNodeId(node)),
  );
  const entrySessions = collectEntrySessions(edgesSource as GraphEdge[]);
  const positionMap =
    isMemoryLayout && !hasPresetPositions
      ? computeMemoryPositions(filteredNodesSource as GraphNode[], entrySessions)
      : new Map<string, { x: number; y: number }>();

  const buildShortLabel = (label: string) => (label.length > 40 ? `${label.slice(0, 40)}…` : label);

  const nodes = filteredNodesSource.map(
    (node: { data: Record<string, unknown>; position?: { x?: number; y?: number } }) => {
      const data = { ...(node.data || {}) };
      const label = typeof data.label === "string" ? data.label : "";
      data.label_short = buildShortLabel(label);
      const topic = typeof data.topic === "string" ? data.topic : "";
      if (topic) {
        const topicColor = colorFromTopic(topic);
        if (topicColor) data.node_color = topicColor;
      }
      const ts = (data.meta as Record<string, unknown> | undefined)?.timestamp;
      if (ts && typeof ts === "string") {
        const timeVal = Date.parse(ts);
        if (!Number.isNaN(timeVal)) data._ts = timeVal;
      }
      const id = typeof data.id === "string" ? data.id : "";
      if (!node.position && id && positionMap.has(id)) {
        return { ...node, data, position: positionMap.get(id) };
      }
      return { ...node, data };
    },
  );

  const edges = (mergedGraph.elements.edges || [])
    .filter((edge) => {
      const data = getNodeData(edge);
      const source = String(data.source ?? "");
      const target = String(data.target ?? "");
      if (removedNodeIds.has(source) || removedNodeIds.has(target)) return false;
      if (source.startsWith("user:") || target.startsWith("user:")) return false;
      return true;
    })
    .map((edge: { data: Record<string, unknown> }) => {
      const data = { ...(edge.data || {}) };
      const label = typeof data.label === "string" ? data.label : "";
      data.label_short = label.length > 30 ? `${label.slice(0, 30)}…` : label;
      return { ...edge, data };
    });

  return { nodes, edges };
}

function resolveBrainNodeColor(ele: cytoscapeType.NodeSingular): string {
  const topicColor = ele.data("node_color");
  if (topicColor) return topicColor;
  const type = ele.data("type");
  if (type === "agent") return "#22c55e";
  if (type === "memory") return "#f59e0b";
  if (type === "memory_session") return "#38bdf8";
  if (type === "memory_user") return "#0ea5e9";
  if (type === "lesson") return "#a855f7";
  return "#6366f1";
}

function resolveBrainNodeOpacity(ele: cytoscapeType.NodeSingular): number {
  const ts = ele.data("_ts");
  if (!ts) return 1;
  const now = Date.now();
  const diffHours = Math.max(0, (now - Number(ts)) / (1000 * 60 * 60));
  if (diffHours <= 1) return 1;
  if (diffHours >= 48) return 0.35;
  const interpolation = Math.min(1, Math.max(0, (diffHours - 1) / 47));
  return 1 - 0.65 * interpolation;
}

function buildGraphStyles(showEdgeLabels: boolean): cytoscapeType.StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        "background-color": resolveBrainNodeColor,
        label: "data(label_short)",
        color: "#e5e7eb",
        "font-size": 10,
        "text-wrap": "wrap",
        "text-max-width": 100,
        "border-width": 1,
        "border-color": "#1f2937",
        opacity: resolveBrainNodeOpacity,
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
        label: showEdgeLabels ? "data(label_short)" : "",
        "font-size": 9,
        color: "#94a3b8",
        "text-background-opacity": 0.4,
        "text-background-color": "#0f172a",
        "text-background-padding": 2,
        "text-overflow": "ellipsis",
      },
    },
  ] as unknown as cytoscapeType.StylesheetJson;
}

function buildRelationEntries(
  node: cytoscapeType.NodeSingular,
  edges: cytoscapeType.EdgeCollection,
): RelationEntry[] {
  return edges.map((edge: cytoscapeType.EdgeSingular) => {
    const edgeData = edge.data();
    const source = edge.source();
    const target = edge.target();
    const isOutgoing = source.id() === node.id();
    const neighbor = isOutgoing ? target : source;
    return {
      id: neighbor.id(),
      label: neighbor.data("label") || neighbor.id(),
      type: edgeData.label || edgeData.type,
      direction: isOutgoing ? "out" : "in",
    };
  });
}

function buildLessonStatsEntries(
  raw:
    | {
      total_lessons?: number;
      total?: number;
      unique_tags?: number;
      tags_count?: number;
      tag_distribution?: Record<string, number>;
    }
    | null
    | undefined,
  t: (key: string, vars?: Record<string, string | number>) => string,
): { label: string; value: string | number; hint?: string }[] {
  if (!raw) return [];
  const entries: { label: string; value: string | number; hint?: string }[] = [];
  const total = raw.total_lessons ?? raw.total;
  if (typeof total === "number") {
    entries.push({ label: t("brain.stats.lessons"), value: total, hint: t("brain.stats.totalHint") });
  }
  const uniqueTags = raw.unique_tags ?? raw.tags_count;
  if (typeof uniqueTags === "number") {
    entries.push({ label: t("brain.stats.uniqueTags"), value: uniqueTags, hint: t("brain.stats.totalHint") });
  }
  if (raw.tag_distribution && typeof raw.tag_distribution === "object") {
    const topTags = Object.entries(raw.tag_distribution)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([tag, count]) => `${tag} (${count})`)
      .join(", ");
    entries.push({
      label: t("brain.stats.topTags"),
      value: topTags || "—",
      hint: t("brain.stats.topTagsHint"),
    });
  }
  return entries;
}

export function BrainHome({ initialData }: Readonly<{ initialData: BrainInitialData }>) {
  const t = useTranslation();
  const { data: liveSummary, refresh: refreshSummary } = useGraphSummary();
  const summary = liveSummary ?? initialData.summary ?? null;
  const initialKnowledge = initialData.knowledgeGraph;
  const [activeTab, setActiveTab] = useState<"repo" | "memory" | "hygiene">("memory");
  const {
    data: liveGraph,
    loading: liveGraphLoading,
    error: graphError,
    refresh: refreshGraph,
  } = useKnowledgeGraph(KNOWLEDGE_GRAPH_LIMIT, 0);
  const [showMemoryLayer, setShowMemoryLayer] = useState(true);
  const [showEdgeLabels, setShowEdgeLabels] = useState(false);
  const [includeLessons, setIncludeLessons] = useState(false);
  const [memorySessionFilter, setMemorySessionFilter] = useState<string>("");
  const [memoryOnlyPinned, setMemoryOnlyPinned] = useState(false);
  const [topicFilter, setTopicFilter] = useState("");
  const [flowMode, setFlowMode] = useState<"default" | "flow">("flow");
  const memoryLimit = MEMORY_GRAPH_LIMIT;
  const memoryGraphPoll = useMemoryGraph(
    memoryLimit,
    memorySessionFilter || undefined,
    memoryOnlyPinned,
    includeLessons,
    0,
    "flow",
  );
  const refreshMemoryGraph = memoryGraphPoll.refresh;
  const memoryGraphLoading = memoryGraphPoll.loading;
  const memoryGraphError = memoryGraphPoll.error;
  const graph = liveGraph ?? initialKnowledge ?? null;
  const [memoryGraphOverride, setMemoryGraphOverride] = useState<KnowledgeGraph | null>(null);
  const memoryGraph = showMemoryLayer ? memoryGraphOverride ?? memoryGraphPoll.data : null;
  const isMemoryEmpty =
    activeTab === "memory" &&
    showMemoryLayer &&
    !memoryGraphLoading &&
    ((memoryGraph?.stats?.nodes ?? memoryGraph?.elements?.nodes?.length ?? 0) <= 1);
  const colorFromTopic = useCallback((topic?: string) => {
    if (!topic) return undefined;
    const palette = ["#fbbf24", "#22c55e", "#0ea5e9", "#a855f7", "#f97316", "#38bdf8", "#f43f5e"];
    let hash = 0;
    for (const char of topic) {
      hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 9973;
    }
    return palette[hash % palette.length];
  }, []);
  const mergedGraph = useMemo(() => {
    if (activeTab === "memory" && showMemoryLayer && memoryGraph?.elements) {
      return memoryGraph;
    }
    if (activeTab === "repo" && graph?.elements) {
      return graph;
    }
    return null;
  }, [activeTab, graph, memoryGraph, showMemoryLayer]);
  const hasPresetPositions =
    (mergedGraph?.elements?.nodes || []).some((n) => {
      const pos = (n as { position?: { x?: number; y?: number } }).position;
      return pos && typeof pos.x === "number" && typeof pos.y === "number";
    }) || false;
  const isMemoryLayout = activeTab === "memory" && showMemoryLayer;
  const layoutName = (() => {
    if (hasPresetPositions || isMemoryLayout) return "preset";
    if (activeTab === "repo") return "cose";
    return "concentric";
  })();
  const preparedElements = useMemo(
    () => prepareGraphElements(mergedGraph, colorFromTopic, hasPresetPositions, isMemoryLayout),
    [mergedGraph, colorFromTopic, hasPresetPositions, isMemoryLayout],
  );
  const graphLoading =
    (activeTab === "repo" && liveGraphLoading && !graph) ||
    (activeTab === "memory" && memoryGraphLoading && !memoryGraph);
  const memoryLoading = activeTab === "memory" && showMemoryLayer && memoryGraphLoading && !memoryGraph;
  useEffect(() => {
    refreshSummary();
    refreshGraph();
    if (showMemoryLayer) {
      refreshMemoryGraph();
    }
  }, [refreshGraph, refreshMemoryGraph, refreshSummary, showMemoryLayer]);
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState !== "visible") return;
      refreshSummary();
      refreshGraph();
      if (showMemoryLayer) {
        refreshMemoryGraph();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    globalThis.window.addEventListener("focus", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      globalThis.window.removeEventListener("focus", handleVisibility);
    };
  }, [refreshGraph, refreshMemoryGraph, refreshSummary, showMemoryLayer]);
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
  const [memoryActionPending, setMemoryActionPending] = useState<string | null>(null);
  const [memoryWipePending, setMemoryWipePending] = useState(false);
  const { pushToast } = useToast();
  const projection = useProjectionTrigger();
  const cyRef = useRef<HTMLDivElement | null>(null);
  const cyInstanceRef = useRef<cytoscapeType.Core | null>(null);
  const recentOperations = useMemo(() => {
    const source = lessons?.lessons ?? [];
    return source.slice(0, 6).map((lesson, index) => ({
      id: lesson.id ?? `${lesson.title ?? "lesson"}-${lesson.created_at ?? index}`,
      title: lesson.title ?? t("brain.recentOperations.defaultTitle"),
      summary: lesson.summary || t("brain.recentOperations.defaultSummary"),
      timestamp: lesson.created_at || null,
      tags: lesson.tags ?? [],
    }));
  }, [lessons?.lessons, t]);
  const lessonTags = useMemo(() => aggregateTags(lessons?.lessons || []), [lessons]);
  const filteredLessons = useMemo(() => {
    if (!activeTag) return lessons?.lessons || [];
    return (lessons?.lessons || []).filter((lesson) => lesson.tags?.includes(activeTag));
  }, [lessons, activeTag]);
  const summaryStats = summary?.summary || summary;
  const legacySummaryStats = summaryStats as { last_updated?: string } | undefined;
  const legacySummary = summary as { last_updated?: string } | undefined;
  const summaryNodes =
    mergedGraph?.elements?.nodes?.length ??
    (activeTab === "repo" ? summaryStats?.nodes ?? summary?.nodes : memoryGraph?.stats?.nodes) ??
    "—";
  const summaryEdges =
    mergedGraph?.elements?.edges?.length ??
    (activeTab === "repo" ? summaryStats?.edges ?? summary?.edges : memoryGraph?.stats?.edges) ??
    "—";
  const renderedNodes = mergedGraph?.elements?.nodes?.length ?? 0;
  const renderedEdges = mergedGraph?.elements?.edges?.length ?? 0;
  const sourceTotalNodes =
    activeTab === "repo"
      ? (summaryStats?.nodes ?? summary?.nodes ?? renderedNodes)
      : memoryGraph?.stats?.nodes ?? renderedNodes;
  const sourceTotalEdges =
    activeTab === "repo"
      ? (summaryStats?.edges ?? summary?.edges ?? renderedEdges)
      : memoryGraph?.stats?.edges ?? renderedEdges;
  const summaryUpdated =
    summary?.lastUpdated || legacySummaryStats?.last_updated || legacySummary?.last_updated;
  const lessonStatsEntries = useMemo(() => {
    return buildLessonStatsEntries(lessonsStats?.stats, t);
  }, [lessonsStats?.stats, t]);
  const applyFiltersToGraph = useCallback(
    (nextFilters: GraphFilterType[]) => {
      const cy = cyInstanceRef.current;
      if (!cy || cy.destroyed() || !cy.container()) return;
      const activeFilters = nextFilters.filter(
        (item): item is SpecificFilter => item !== "all",
      );
      cy.batch(() => {
        cy.nodes().style("display", "element");
        cy.nodes().forEach((node) => {
          const nodeType = node.data("type") as SpecificFilter | undefined;
          const nodeTopic = (node.data("topic") as string | undefined) || "";
          const matchesType =
            activeFilters.length === 0 || (nodeType && activeFilters.includes(nodeType));
          const matchesTopic =
            activeTab === "memory"
              ? !topicFilter ||
              nodeTopic.toLowerCase().includes(topicFilter.trim().toLowerCase())
              : true;
          if (!(matchesType && matchesTopic)) {
            node.style("display", "none");
          }
        });
      });
    },
    [activeTab, topicFilter],
  );

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
        const meta = (node.data("meta") || {}) as Record<string, unknown>;
        const tagField = meta.tags || props.tags || [];
        const tags =
          typeof tagField === "string"
            ? tagField.split(",").map((t) => t.trim()).filter(Boolean)
            : (tagField as string[]);
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

  const handlePinMemory = async (entryId: string, pinned: boolean) => {
    try {
      setMemoryActionPending(entryId);
      await pinMemoryEntry(entryId, pinned);
      pushToast(pinned ? t("brain.toasts.pinSuccess") : t("brain.toasts.unpinSuccess"), "success");
      memoryGraphPoll.refresh();
    } catch (err) {
      pushToast(t("brain.toasts.pinError"), "error");
      console.error("Nie udało się zmienić stanu pinned:", err);
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleDeleteMemory = async (entryId: string) => {
    const confirmed = globalThis.window.confirm(t("brain.toasts.deleteConfirm"));
    if (!confirmed) return;
    try {
      setMemoryActionPending(entryId);
      await deleteMemoryEntry(entryId);
      clearSelection();
      memoryGraphPoll.refresh();
      pushToast(t("brain.toasts.deleteSuccess"), "success");
    } catch (err) {
      pushToast(t("brain.toasts.deleteError"), "error");
      console.error("Nie udało się usunąć wpisu pamięci:", err);
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
      await memoryGraphPoll.refresh();
      await refreshSummary();
      setMemoryGraphOverride(null);
    } catch (err) {
      pushToast(t("brain.toasts.clearSessionError"), "error");
      console.error(err);
    } finally {
      setMemoryWipePending(false);
    }
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
      setScanMessage(res.message || t("brain.toasts.scanStarted"));
      refreshSummary();
    } catch (err) {
      setScanMessage(
        err instanceof Error ? err.message : t("brain.toasts.scanError"),
      );
    } finally {
      setScanning(false);
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
        if (!res.file_info) {
          setFileMessage(t("brain.file.noInfo"));
        }
      } else {
        const res = await fetchGraphImpact(filePath.trim());
        setImpactInfo(res.impact || null);
        if (!res.impact) {
          setFileMessage(t("brain.file.noImpact"));
        }
      }
    } catch (err) {
      setFileMessage(
        err instanceof Error ? err.message : t("brain.file.fetchError"),
      );
    } finally {
      setFileLoading(false);
    }
  };

  useEffect(() => {
    let cyInstance: cytoscapeType.Core | null = null;
    const mount = async () => {
      if (!cyRef.current || !mergedGraph?.elements) return;
      if (!preparedElements) return;
      const cytoscape = (await import("cytoscape")).default as typeof cytoscapeType;
      if (!cyRef.current) return;
      const elements = preparedElements as unknown as cytoscapeType.ElementsDefinition;
      const styles = buildGraphStyles(showEdgeLabels);
      cyInstance = cytoscape({
        container: cyRef.current,
        elements,
        layout: { name: layoutName, padding: 30, animate: false },
        style: styles,
      });
      cyInstance.on("tap", "node", (evt: cytoscapeType.EventObject) => {
        const data = evt.target.data() || {};
        setSelected(data);
        setDetailsSheetOpen(true);
        setHighlightTag(null);
        const edges = evt.target.connectedEdges();
        const relEntries = buildRelationEntries(evt.target, edges);
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
  }, [mergedGraph, clearSelection, focusNodeWithNeighbors, showEdgeLabels, layoutName, preparedElements]);

  useEffect(() => {
    if (mergedGraph) {
      applyFiltersToGraph(filters);
    }
  }, [mergedGraph, filters, applyFiltersToGraph]);

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
          <Button
            size="sm"
            variant={activeTab === "memory" ? "secondary" : "ghost"}
            className="rounded-full px-4"
            onClick={() => setActiveTab("memory")}
          >
            {t("brain.tabs.memory")}
          </Button>
          <Button
            size="sm"
            variant={activeTab === "repo" ? "secondary" : "ghost"}
            className="rounded-full px-4"
            onClick={() => setActiveTab("repo")}
          >
            {t("brain.tabs.repo")}
          </Button>
          <Button
            size="sm"
            variant={activeTab === "hygiene" ? "secondary" : "ghost"}
            className="rounded-full px-4"
            onClick={() => setActiveTab("hygiene")}
            data-testid="hygiene-tab"
          >
            {t("brain.tabs.hygiene")}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">{t("brain.stats.nodes")}: {summaryNodes}</Badge>
        <Badge tone="neutral">{t("brain.stats.edges")}: {summaryEdges}</Badge>
        <Badge tone="warning">{t("brain.home.updated")}: {summaryUpdated ?? "—"}</Badge>
        <Badge tone="neutral">{t("brain.home.source")}: {activeTab === "repo" ? t("brain.home.knowledge") : t("brain.home.memory")}</Badge>
        {activeTab === "memory" ? <Badge tone="neutral">Limit: {memoryLimit}</Badge> : null}
        <Badge tone="neutral">
          Render: {renderedNodes}/{sourceTotalNodes} • {renderedEdges}/{sourceTotalEdges}
        </Badge>
      </div>


      {activeTab === "hygiene" ? (
        <HygienePanel />
      ) : (
        <>
          <div className="relative overflow-hidden rounded-[32px] border border-white/10 bg-gradient-to-br from-zinc-950/70 to-zinc-900/30 shadow-card">
            <div className="pointer-events-none absolute inset-0 grid-overlay" />
            <div
              ref={cyRef}
              data-testid="graph-container"
              className="relative h-[70vh] w-full"
            />
            {isMemoryEmpty && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-gradient-to-b from-black/70 via-black/60 to-black/70 text-center text-white">
                <p className="text-sm uppercase tracking-[0.35em] text-zinc-400">{t("brain.file.noData")}</p>
                <p className="max-w-md text-lg font-semibold text-white">
                  {t("brain.lessons.emptyDescription")}
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <Button asChild size="sm" variant="secondary">
                    <a href="/chat">{t("cockpit.newChat")}</a>
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="border-white/30 text-white"
                    onClick={() => refreshSummary()}
                  >
                    Odśwież status
                  </Button>
                  <Button size="sm" onClick={handleScanGraph} disabled={scanning}>
                    {scanning ? t("brain.actions.scanning") : t("brain.actions.scan")}
                  </Button>
                </div>
              </div>
            )}
            {(graphLoading || memoryLoading || graphError || memoryGraphError) && (
              <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 bg-black/80 text-center text-sm text-white">
                {graphLoading || memoryLoading ? (
                  <Loader2 className="h-6 w-6 animate-spin text-emerald-300" />
                ) : (
                  <AlertTriangle className="h-6 w-6 text-amber-300" />
                )}
                <p>
                  {graphLoading || memoryLoading
                    ? t("brain.graph.scanning")
                    : t("brain.file.noData")}
                </p>
                {(graphError || memoryGraphError) && (
                  <Button
                    type="button"
                    variant="outline"
                    size="xs"
                    className="pointer-events-auto border-white/20 px-4 py-2 text-xs uppercase tracking-wider text-white hover:border-white/50"
                    onClick={() => {
                      refreshGraph();
                      if (showMemoryLayer) memoryGraphPoll.refresh();
                    }}
                  >
                    Odśwież
                  </Button>
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
            {activeTab === "memory" ? (
              <div className="pointer-events-auto absolute left-6 right-6 bottom-6 flex flex-col gap-2 rounded-2xl border border-white/10 bg-black/70 px-4 py-3 text-xs text-white backdrop-blur">
                <div className="flex flex-wrap items-center gap-2">
                  {lessonTags.slice(0, 6).map((tag) => (
                    <Button
                      key={tag.name}
                      variant="ghost"
                      size="xs"
                      className={`rounded-full border px-3 py-1 ${highlightTag === tag.name
                        ? "border-amber-400/50 bg-amber-500/20"
                        : "border-white/10 bg-white/5 text-zinc-200"
                        }`}
                      onClick={() => handleTagToggle(tag.name)}
                    >
                      #{tag.name}
                    </Button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={showMemoryLayer}
                      onChange={(e) => setShowMemoryLayer(e.target.checked)}
                    />
                    <span>{t("brain.controls.memoryLayer")}</span>
                  </label>
                  {memoryGraph?.stats?.nodes ? (
                    <Badge tone="neutral">{t("brain.controls.memoryNodes", { count: memoryGraph.stats.nodes })}</Badge>
                  ) : null}
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={memoryOnlyPinned}
                      onChange={(e) => setMemoryOnlyPinned(e.target.checked)}
                    />
                    <span>{t("brain.controls.onlyPinned")}</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={includeLessons}
                      onChange={(e) => setIncludeLessons(e.target.checked)}
                    />
                    <span>{t("brain.controls.includeLessons")}</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={showEdgeLabels}
                      onChange={(e) => setShowEdgeLabels(e.target.checked)}
                    />
                    <span>{t("brain.controls.edgeLabels")}</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={flowMode === "flow"}
                      onChange={(e) => setFlowMode(e.target.checked ? "flow" : "default")}
                    />
                    <span>{t("brain.controls.flowMode")}</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <span>{t("brain.controls.legendSession")}</span>
                    <input
                      type="text"
                      value={memorySessionFilter}
                      onChange={(e) => setMemorySessionFilter(e.target.value)}
                      placeholder={t("brain.controls.sessionIdPlaceholder")}
                      className="min-w-[140px] rounded border border-white/20 bg-black/40 px-2 py-1 text-[11px] text-white outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <span>Topic</span>
                    <input
                      type="text"
                      value={topicFilter}
                      onChange={(e) => {
                        setTopicFilter(e.target.value);
                        applyFiltersToGraph(filters);
                      }}
                      placeholder="np. ui / infra"
                      className="min-w-[140px] rounded border border-white/20 bg-black/40 px-2 py-1 text-[11px] text-white outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      size="xs"
                      variant="outline"
                      className="border-white/20 text-white"
                      disabled={memoryWipePending}
                      onClick={handleClearSessionMemory}
                    >
                      {t("brain.controls.clearSession")}
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      className="border-white/20 text-white"
                      onClick={() => {
                        memoryGraphPoll.refresh();
                      }}
                    >
                      {t("brain.controls.refreshMemory")}
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      className="border-white/20 text-white"
                      disabled={projection.pending}
                      onClick={async () => {
                        try {
                          const res = await projection.trigger(memoryLimit);
                          pushToast(`Zaktualizowano projekcję (records: ${res.updated})`, "success");
                          memoryGraphPoll.refresh();
                        } catch {
                          pushToast("Nie udało się zaktualizować projekcji embeddingów.", "error");
                        }
                      }}
                    >
                      {t("brain.controls.refreshProjection")}
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>


          <div className="flex flex-wrap gap-3 text-xs text-white">
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
              <span className="text-zinc-400">{t("brain.controls.legend")}</span>
              {activeTab === "repo" ? (
                <>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-indigo-400" />
                    <span>file / function</span>
                  </span>
                </>
              ) : (
                <>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-400" />
                    {t("brain.controls.legendMemory")}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-sky-400" />
                    {t("brain.controls.legendSession")}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    {t("brain.controls.legendUser")}
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-purple-500" />
                    {t("brain.controls.legendLesson")}
                  </span>
                </>
              )}
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-fuchsia-500" />
                {t("brain.controls.legendSelected")}
              </span>
            </div>
            {activeTab === "memory" ? (
              <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
                <span className="text-zinc-400">{t("brain.controls.edgeLabels")}:</span>
                <span className="text-zinc-200">
                  {showEdgeLabels ? t("brain.controls.edgeLabels") : t("brain.controls.defaultHidden")}
                </span>
              </div>
            ) : null}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">{t("brain.selection.title")}</h4>
              {selected ? (
                <div className="mt-3 space-y-2 text-xs text-zinc-300">
                  <p>
                    <span className="text-zinc-400">{t("brain.selection.node")}:</span>{" "}
                    <span className="font-semibold text-white">
                      {String(selected.label || selected.id || "n/a")}
                    </span>
                  </p>
                  <p>
                    <span className="text-zinc-400">{t("brain.selection.type")}:</span>{" "}
                    <span className="font-semibold text-emerald-300">
                      {String((selected as Record<string, unknown>)?.type || "n/a")}
                    </span>
                  </p>
                  <p>
                    <span className="text-zinc-400">{t("brain.selection.relations")}:</span>{" "}
                    <span className="font-semibold">{relations.length}</span>
                  </p>
                  <p className="text-hint">
                    {t("brain.selection.hint")}
                  </p>
                  <Button
                    size="xs"
                    variant="outline"
                    className="text-caption"
                    onClick={() => {
                      if (!selected) return;
                      setDetailsSheetOpen(true);
                    }}
                  >
                    {t("brain.selection.details")}
                  </Button>
                </div>
              ) : (
                <p className="mt-3 text-hint">
                  {t("brain.selection.empty")}
                </p>
              )}
            </div>
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">{t("brain.relations.title")}</h4>
              {selected && relations.length > 0 ? (
                <ul className="mt-3 space-y-2 text-xs">
                  {relations.slice(0, 5).map((rel) => (
                    <li key={`${selected.id}-${rel.id}-${rel.direction}`} className="rounded-2xl box-muted px-3 py-2">
                      <span className="font-semibold text-white">{rel.label}</span>{" "}
                      <span className="text-zinc-400">
                        ({rel.direction === "out" ? "→" : "←"} {rel.type || "link"})
                      </span>
                    </li>
                  ))}
                  {relations.length > 5 && (
                    <p className="text-caption">
                      {t("brain.relations.more", { count: relations.length - 5 })}
                    </p>
                  )}
                </ul>
              ) : (
                <p className="mt-3 text-hint">
                  {t("brain.relations.empty")}
                </p>
              )}
            </div>
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">{t("brain.recentOperations.title")}</h4>
              {recentOperations.length === 0 ? (
                <p className="mt-3 text-hint">
                  {t("brain.recentOperations.empty")}
                </p>
              ) : (
                <ul className="mt-3 space-y-2 text-xs text-zinc-300">
                  {recentOperations.map((op) => (
                    <li
                      key={op.id}
                      className="rounded-2xl box-subtle px-3 py-2 shadow-inner"
                    >
                      <p className="font-semibold text-white">{op.title}</p>
                      <p className="text-caption">
                        {formatOperationTimestamp(op.timestamp)}
                      </p>
                      <p className="text-hint">{op.summary}</p>
                      {op.tags.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {op.tags.slice(0, 3).map((tag) => (
                            <span
                              key={`${op.id}-${tag}`}
                              className="pill-badge text-emerald-200"
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
        </>
      )}

      {/* Panels rendered outside of graph container */}
      {activeTab !== "hygiene" && (
        <>
          <Panel
            title={t("brain.lessons.panelTitle")}
            description={t("brain.lessons.panelDescription")}
            action={
              <Button size="sm" variant="secondary" onClick={() => refreshLessons()}>
                {t("brain.lessons.refresh")}
              </Button>
            }
          >
            <div className="space-y-4">
              <div className="rounded-2xl box-base p-4 text-sm text-white">
                <h4 className="heading-h4">{t("brain.stats.title") || "Statystyki Lessons"}</h4>
                {lessonStatsEntries.length > 0 ? (
                  <div className="mt-3">
                    <LessonStats entries={lessonStatsEntries} />
                  </div>
                ) : (
                  <EmptyState
                    icon={<Radar className="h-4 w-4" />}
                    title={t("brain.lessons.noStats")}
                    description={t("brain.lessons.emptyDescription")}
                    className="mt-3 text-xs"
                  />
                )}
              </div>
              <div>
                <h4 className="heading-h4">{t("brain.lessons.listTitle")}</h4>
                <LessonActions tags={lessonTags} activeTag={activeTag} onSelect={setActiveTag} />
                <div className="mt-3">
                  <LessonList lessons={filteredLessons} emptyMessage={t("brain.lessons.emptyDescription")} />
                </div>
              </div>
            </div>
          </Panel>

          <Panel title={t("brain.file.title")} description={t("brain.file.description")}>
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
                    <pre className="mt-2 max-h-60 overflow-auto rounded-xl box-muted p-3 text-xs text-zinc-100">
                      {JSON.stringify(selected, null, 2)}
                    </pre>
                  </div>
                  {selected.type === "memory" && selected.id ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={memoryActionPending === selected.id}
                        onClick={() =>
                          handlePinMemory(
                            String(selected.id),
                            !(selected as Record<string, unknown>)?.pinned,
                          )
                        }
                      >
                        {selected.pinned ? t("brain.actions.unpin") : t("brain.actions.pin")}
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={memoryActionPending === selected.id}
                        onClick={() => handleDeleteMemory(String(selected.id))}
                      >
                        {t("brain.actions.delete")}
                      </Button>
                    </div>
                  ) : null}
                  <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">Relacje</p>
                    {relations.length === 0 ? (
                      <p className="text-hint">Brak relacji.</p>
                    ) : (
                      <ul className="mt-2 space-y-2 text-xs">
                        {relations.map((rel) => (
                          <li
                            key={`${selected.id}-${rel.id}-${rel.direction}`}
                            className="rounded-xl box-base px-3 py-2"
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
                <p className="text-hint">Kliknij węzeł, by zobaczyć szczegóły.</p>
              )}
            </SheetContent>
          </Sheet>
        </>
      )}
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

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
import { clearGlobalMemory, clearSessionMemory, deleteMemoryEntry, pinMemoryEntry } from "@/hooks/use-api";
import { useToast } from "@/components/ui/toast";
import { KNOWLEDGE_GRAPH_LIMIT, MEMORY_GRAPH_LIMIT } from "@/hooks/use-api";
import { useProjectionTrigger } from "@/hooks/use-projection";

type SpecificFilter = Exclude<GraphFilterType, "all">;
import { GraphActionButtons } from "@/components/brain/graph-actions";

import { HygienePanel } from "@/components/brain/hygiene-panel";

export function BrainHome({ initialData }: { initialData: BrainInitialData }) {
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
    for (let i = 0; i < topic.length; i += 1) {
      hash = (hash * 31 + topic.charCodeAt(i)) % 9973;
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
  const layoutName = hasPresetPositions || isMemoryLayout
    ? "preset"
    : activeTab === "repo"
      ? "cose"
      : "concentric";
  const preparedElements = useMemo(() => {
    if (!mergedGraph?.elements) return null;
    const nodesSource = mergedGraph.elements.nodes || [];
    const edgesSource = mergedGraph.elements.edges || [];
    const filteredNodesSource = nodesSource.filter((node) => {
      const data = (node as { data?: Record<string, unknown> }).data || {};
      return data.memory_kind !== "user";
    });
    const removedNodeIds = new Set(
      nodesSource
        .filter((node) => {
          const data = (node as { data?: Record<string, unknown> }).data || {};
          return data.memory_kind === "user";
        })
        .map((node) => String((node as { data?: Record<string, unknown> }).data?.id ?? "")),
    );
    const entrySessions = new Map<string, Set<string>>();
    edgesSource.forEach((edge) => {
      const data = (edge as { data?: Record<string, unknown> }).data || {};
      const source = String(data.source ?? "");
      const target = String(data.target ?? "");
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
    const positionMap = new Map<string, { x: number; y: number }>();
    if (isMemoryLayout && !hasPresetPositions) {
      const sessionNodes = filteredNodesSource.filter((node) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        return data.memory_kind === "session";
      });
      const entryNodes = filteredNodesSource.filter((node) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        return data.memory_kind !== "session" && data.memory_kind !== "user" && data.memory_kind !== "lesson";
      });
      const lessonNodes = filteredNodesSource.filter((node) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        return data.memory_kind === "lesson";
      });
      const sessionCenters = new Map<string, number>();
      const sharedEntries: typeof entryNodes = [];
      const sharedBuckets = new Map<string, typeof entryNodes>();

      const entriesBySession = new Map<string, typeof entryNodes>();
      const orphanEntries: typeof entryNodes = [];
      entryNodes.forEach((node) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        const sessionId = typeof data.session_id === "string" ? data.session_id : "";
        if (sessionId) {
          const bucket = entriesBySession.get(sessionId) || [];
          bucket.push(node);
          entriesBySession.set(sessionId, bucket);
        } else {
          orphanEntries.push(node);
        }
      });

      const sortByTimestamp = (a: unknown, b: unknown) => {
        const aMeta = ((a as { data?: Record<string, unknown> }).data || {}).meta as
          | Record<string, unknown>
          | undefined;
        const bMeta = ((b as { data?: Record<string, unknown> }).data || {}).meta as
          | Record<string, unknown>
          | undefined;
        const aTs = typeof aMeta?.timestamp === "string" ? Date.parse(aMeta.timestamp) : NaN;
        const bTs = typeof bMeta?.timestamp === "string" ? Date.parse(bMeta.timestamp) : NaN;
        if (!Number.isNaN(aTs) && !Number.isNaN(bTs)) return aTs - bTs;
        return String((a as { data?: Record<string, unknown> }).data?.label ?? "").localeCompare(
          String((b as { data?: Record<string, unknown> }).data?.label ?? ""),
        );
      };
      const isAssistantEntry = (node: unknown) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        const label = typeof data.label === "string" ? data.label : "";
        const meta = (data.meta as Record<string, unknown> | undefined) || {};
        const roleHint =
          typeof meta.role === "string"
            ? meta.role
            : typeof meta.author === "string"
              ? meta.author
              : typeof meta.speaker === "string"
                ? meta.speaker
                : "";
        return (
          /assistant|asystent|venom/i.test(roleHint) ||
          /^(assistant|asystent|venom)\b/i.test(label)
        );
      };

      const sessionSpacing = 260;
      const entrySpacing = 90;
      const sessionStartY = -((sessionNodes.length - 1) * sessionSpacing) / 2;
      sessionNodes.forEach((node, index) => {
        const data = (node as { data?: Record<string, unknown> }).data || {};
        const id = String(data.id ?? "");
        const sessionId = typeof data.session_id === "string" ? data.session_id : "";
        const centerY = sessionStartY + index * sessionSpacing;
        if (id) {
          positionMap.set(id, { x: -160, y: centerY });
        }
        if (sessionId) {
          sessionCenters.set(sessionId, centerY);
        }
        const entries = (entriesBySession.get(sessionId) || []).slice().sort(sortByTimestamp);
        const entryStartY = centerY - ((entries.length - 1) * entrySpacing) / 2;
        entries.forEach((entry, entryIndex) => {
          const entryId = String((entry as { data?: Record<string, unknown> }).data?.id ?? "");
          if (!entryId) return;
          const sessions = entrySessions.get(entryId);
          if (sessions && sessions.size > 1) {
            sharedEntries.push(entry);
            const signature = Array.from(sessions).sort().join("|");
            const bucket = sharedBuckets.get(signature) || [];
            bucket.push(entry);
            sharedBuckets.set(signature, bucket);
            return;
          }
          const isAssistant = isAssistantEntry(entry);
          const baseX = 60;
          const stepX = 40;
          const assistantBump = isAssistant ? 20 : 0;
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
            const entryId = String((entry as { data?: Record<string, unknown> }).data?.id ?? "");
            if (!entryId) return;
            positionMap.set(entryId, {
              x: 10,
              y: sharedStartY + index * entrySpacing,
            });
          });
        });
      }

      if (orphanEntries.length > 0) {
        const baseY = sessionStartY + sessionNodes.length * sessionSpacing + 80;
        const sortedOrphans = orphanEntries.slice().sort(sortByTimestamp);
        const startY = baseY - ((sortedOrphans.length - 1) * entrySpacing) / 2;
        sortedOrphans.forEach((node, index) => {
          const id = String((node as { data?: Record<string, unknown> }).data?.id ?? "");
          if (id) {
            const isAssistant = isAssistantEntry(node);
            positionMap.set(id, { x: isAssistant ? 180 : 60, y: startY + index * entrySpacing });
          }
        });
      }

      if (lessonNodes.length > 0) {
        const lessonStartY =
          sessionStartY +
          sessionNodes.length * sessionSpacing +
          (orphanEntries.length > 0 ? orphanEntries.length * entrySpacing + 160 : 120);
        lessonNodes.forEach((node, index) => {
          const id = String((node as { data?: Record<string, unknown> }).data?.id ?? "");
          if (id) {
            positionMap.set(id, { x: 220, y: lessonStartY + index * 140 });
          }
        });
      }
    }

    const nodes = filteredNodesSource.map(
      (node: { data: Record<string, unknown>; position?: { x?: number; y?: number } }) => {
        const data = { ...(node.data || {}) };
        const label = typeof data.label === "string" ? data.label : "";
        data.label_short = label.length > 40 ? `${label.slice(0, 40)}…` : label;
        const topic = typeof data.topic === "string" ? data.topic : "";
        if (topic) {
          const topicColor = colorFromTopic(topic);
          if (topicColor) data.node_color = topicColor;
        }
        const ts = (data.meta as Record<string, unknown> | undefined)?.timestamp;
        if (ts && typeof ts === "string") {
          const timeVal = Date.parse(ts);
          if (!Number.isNaN(timeVal)) {
            data._ts = timeVal;
          }
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
        const data = (edge as { data?: Record<string, unknown> }).data || {};
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
  }, [mergedGraph, colorFromTopic, hasPresetPositions, isMemoryLayout]);
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
    window.addEventListener("focus", handleVisibility);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleVisibility);
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
    const raw = lessonsStats?.stats;
    if (!raw) return [];
    const entries: { label: string; value: string | number; hint?: string }[] = [];
    const total = raw.total_lessons ?? raw.total;
    const uniqueTags = raw.unique_tags ?? raw.tags_count;
    if (typeof total === "number") {
      entries.push({ label: "Lekcje", value: total, hint: "LessonsStore" });
    }
    if (typeof uniqueTags === "number") {
      entries.push({ label: "Unikalne tagi", value: uniqueTags, hint: "LessonsStore" });
    }
    const tagDistribution = raw.tag_distribution as Record<string, number> | undefined;
    if (tagDistribution && typeof tagDistribution === "object") {
      const topTags = Object.entries(tagDistribution)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([tag, count]) => `${tag} (${count})`)
        .join(", ");
      entries.push({
        label: "Top tagi",
        value: topTags || "—",
        hint: "Najczęstsze tagi LessonsStore",
      });
    }
    return entries;
  }, [lessonsStats?.stats]);
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
      pushToast(pinned ? "Przypięto wpis pamięci." : "Odepnieto wpis pamięci.", "success");
      memoryGraphPoll.refresh();
    } catch (err) {
      pushToast("Nie udało się zmienić stanu pinned.", "error");
      console.error("Nie udało się zmienić stanu pinned:", err);
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleDeleteMemory = async (entryId: string) => {
    const confirmed = window.confirm("Czy na pewno usunąć ten wpis pamięci?");
    if (!confirmed) return;
    try {
      setMemoryActionPending(entryId);
      await deleteMemoryEntry(entryId);
      clearSelection();
      memoryGraphPoll.refresh();
      pushToast("Usunięto wpis pamięci.", "success");
    } catch (err) {
      pushToast("Nie udało się usunąć wpisu pamięci.", "error");
      console.error("Nie udało się usunąć wpisu pamięci:", err);
    } finally {
      setMemoryActionPending(null);
    }
  };

  const handleClearSessionMemory = async () => {
    if (!memorySessionFilter.trim()) {
      pushToast("Podaj session_id do wyczyszczenia.", "warning");
      return;
    }
    try {
      setMemoryWipePending(true);
      const resp = await clearSessionMemory(memorySessionFilter.trim());
      pushToast(`Wyczyszczono sesję ${resp.session_id} (wektorów: ${resp.deleted_vectors}).`, "success");
      setMemoryGraphOverride({ elements: { nodes: [], edges: [] }, stats: { nodes: 0, edges: 0 } });
      await memoryGraphPoll.refresh();
      await refreshSummary();
      setMemoryGraphOverride(null);
    } catch (err) {
      pushToast("Nie udało się wyczyścić pamięci sesji.", "error");
      console.error(err);
    } finally {
      setMemoryWipePending(false);
    }
  };

  const handleClearGlobalMemory = async () => {
    const confirmed = window.confirm("Wyczyścić całą pamięć globalną? Tej operacji nie można cofnąć.");
    if (!confirmed) return;
    try {
      setMemoryWipePending(true);
      const resp = await clearGlobalMemory();
      pushToast(`Wyczyszczono pamięć globalną (wektorów: ${resp.deleted_vectors ?? 0}).`, "success");
      setMemoryGraphOverride({ elements: { nodes: [], edges: [] }, stats: { nodes: 0, edges: 0 } });
      await memoryGraphPoll.refresh();
      await refreshSummary();
      setMemoryGraphOverride(null);
    } catch (err) {
      pushToast("Nie udało się wyczyścić pamięci globalnej.", "error");
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
      if (!cyRef.current || !mergedGraph?.elements) return;
      if (!preparedElements) return;
      const cytoscape = (await import("cytoscape")).default as typeof cytoscapeType;
      const elements = preparedElements as unknown as cytoscapeType.ElementsDefinition;
      const styles = [
        {
          selector: "node",
          style: {
            "background-color": (ele: cytoscapeType.NodeSingular) => {
              const topicColor = ele.data("node_color");
              if (topicColor) return topicColor;
              return ele.data("type") === "agent"
                ? "#22c55e"
                : ele.data("type") === "memory"
                  ? "#f59e0b"
                  : ele.data("type") === "memory_session"
                    ? "#38bdf8"
                    : ele.data("type") === "memory_user"
                      ? "#0ea5e9"
                      : ele.data("type") === "lesson"
                        ? "#a855f7"
                        : "#6366f1";
            },
            label: "data(label_short)",
            color: "#e5e7eb",
            "font-size": 10,
            "text-wrap": "wrap",
            "text-max-width": 100,
            "border-width": 1,
            "border-color": "#1f2937",
            opacity: (ele: cytoscapeType.NodeSingular) => {
              const ts = ele.data("_ts");
              if (!ts) return 1;
              const now = Date.now();
              const diffHours = Math.max(0, (now - Number(ts)) / (1000 * 60 * 60));
              if (diffHours <= 1) return 1;
              if (diffHours >= 48) return 0.35;
              const t = Math.min(1, Math.max(0, (diffHours - 1) / (48 - 1)));
              return 1 - 0.65 * t;
            },
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
  }, [mergedGraph, clearSelection, focusNodeWithNeighbors, showEdgeLabels, layoutName, preparedElements]);

  useEffect(() => {
    if (mergedGraph) {
      applyFiltersToGraph(filters);
    }
  }, [mergedGraph, filters, applyFiltersToGraph]);

  return (
    <div className="space-y-6 pb-10">
      <SectionHeading
        eyebrow="Brain / Graf wiedzy"
        title="Siatka wiedzy"
        description="Pełnoekranowy podgląd pamięci Venoma z filtrami agentów i lekcji."
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
            Pamięć / Lessons
          </Button>
          <Button
            size="sm"
            variant={activeTab === "repo" ? "secondary" : "ghost"}
            className="rounded-full px-4"
            onClick={() => setActiveTab("repo")}
          >
            Repo / Knowledge
          </Button>
          <Button
            size="sm"
            variant={activeTab === "hygiene" ? "secondary" : "ghost"}
            className="rounded-full px-4"
            onClick={() => setActiveTab("hygiene")}
            data-testid="hygiene-tab"
          >
            Hygiene / Clean
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="neutral">Węzły: {summaryNodes}</Badge>
        <Badge tone="neutral">Krawędzie: {summaryEdges}</Badge>
        <Badge tone="warning">Aktualizacja: {summaryUpdated ?? "—"}</Badge>
        <Badge tone="neutral">Źródło: {activeTab === "repo" ? "Knowledge" : "Pamięć"}</Badge>
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
                <p className="text-sm uppercase tracking-[0.35em] text-zinc-400">Brak danych</p>
                <p className="max-w-md text-lg font-semibold text-white">
                  Pamięć jest pusta. Rozpocznij rozmowę lub skanuj graf, aby wczytać węzły.
                </p>
                <div className="flex flex-wrap items-center justify-center gap-3">
                  <Button asChild size="sm" variant="secondary">
                    <a href="/chat">Rozpocznij chat</a>
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
                    {scanning ? "Skanuję..." : "Skanuj graf"}
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
                    ? "Ładuję graf..."
                    : "Brak danych z API grafu."}
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
                    <span>Warstwa pamięci (LanceDB)</span>
                  </label>
                  {memoryGraph?.stats?.nodes ? (
                    <Badge tone="neutral">Pamięć: {memoryGraph.stats.nodes} węzłów</Badge>
                  ) : null}
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={memoryOnlyPinned}
                      onChange={(e) => setMemoryOnlyPinned(e.target.checked)}
                    />
                    <span>Tylko pinned</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={includeLessons}
                      onChange={(e) => setIncludeLessons(e.target.checked)}
                    />
                    <span>Dołącz lekcje</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={showEdgeLabels}
                      onChange={(e) => setShowEdgeLabels(e.target.checked)}
                    />
                    <span>Etykiety krawędzi</span>
                  </label>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={flowMode === "flow"}
                      onChange={(e) => setFlowMode(e.target.checked ? "flow" : "default")}
                    />
                    <span>Tryb flow (sekwencja)</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <span>Session</span>
                    <input
                      type="text"
                      value={memorySessionFilter}
                      onChange={(e) => setMemorySessionFilter(e.target.value)}
                      placeholder="session-id"
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
                      Wyczyść tok sesji
                    </Button>
                    <Button
                      size="xs"
                      variant="outline"
                      className="border-white/20 text-white"
                      onClick={() => {
                        memoryGraphPoll.refresh();
                      }}
                    >
                      Odśwież pamięć
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
                      Odśwież projekcję
                    </Button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>


          <div className="flex flex-wrap gap-3 text-xs text-white">
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
              <span className="text-zinc-400">Legenda:</span>
              {activeTab === "repo" ? (
                <>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-indigo-400" />
                    file / function
                  </span>
                </>
              ) : (
                <>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-amber-400" />
                    memory / fact
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-sky-400" />
                    session
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    user
                  </span>
                  <span className="flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-purple-500" />
                    lesson
                  </span>
                </>
              )}
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-fuchsia-500" />
                zaznaczony / sąsiedzi
              </span>
            </div>
            {activeTab === "memory" ? (
              <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
                <span className="text-zinc-400">Etykiety krawędzi:</span>
                <span className="text-zinc-200">
                  {showEdgeLabels ? "włączone (może spowolnić)" : "domyślnie ukryte"}
                </span>
              </div>
            ) : null}
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">Podsumowanie zaznaczenia</h4>
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
                  <p className="text-hint">
                    Kliknij „Szczegóły”, by zobaczyć pełne dane JSON oraz kierunki relacji.
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
                    Szczegóły
                  </Button>
                </div>
              ) : (
                <p className="mt-3 text-hint">
                  Wybierz węzeł w grafie, aby zobaczyć jego podstawowe dane.
                </p>
              )}
            </div>
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">Relacje (podgląd)</h4>
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
                      +{relations.length - 5} kolejnych relacji w panelu szczegółów.
                    </p>
                  )}
                </ul>
              ) : (
                <p className="mt-3 text-hint">
                  Brak relacji (lub nie wybrano węzła).
                </p>
              )}
            </div>
            <div className="card-shell card-base p-4 text-sm">
              <h4 className="heading-h4">Ostatnie operacje grafu</h4>
              {recentOperations.length === 0 ? (
                <p className="mt-3 text-hint">
                  Brak zarejestrowanych operacji. Uruchom skan lub odśwież lekcje.
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
            title="Lekcje i operacje grafu"
            description="LessonsStore + akcje skanowania grafu."
            action={
              <Button size="sm" variant="secondary" onClick={() => refreshLessons()}>
                Odśwież lekcje
              </Button>
            }
          >
            <div className="space-y-4">
              <div className="rounded-2xl box-base p-4 text-sm text-white">
                <h4 className="heading-h4">Statystyki Lessons</h4>
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
                <h4 className="heading-h4">Ostatnie lekcje</h4>
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
                        {selected.pinned ? "Odepnij" : "Przypnij"}
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={memoryActionPending === selected.id}
                        onClick={() => handleDeleteMemory(String(selected.id))}
                      >
                        Usuń wpis
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

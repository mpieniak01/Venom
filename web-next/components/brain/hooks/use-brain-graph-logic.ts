import { KnowledgeGraph } from "@/lib/types";
import { useMemo, useState } from "react";
import { useKnowledgeGraph, useMemoryGraph, KNOWLEDGE_GRAPH_LIMIT, MEMORY_GRAPH_LIMIT } from "@/hooks/use-api";

type UseBrainGraphLogicParams = {
    initialKnowledge: KnowledgeGraph | null;
    activeTab: "repo" | "memory" | "hygiene";
    showMemoryLayer: boolean;
    memorySessionFilter: string;
    memoryOnlyPinned: boolean;
    includeLessons: boolean;
    flowMode?: "flow" | "default";
    topicFilter?: string;
};

export function useBrainGraphLogic({
    initialKnowledge,
    activeTab,
    showMemoryLayer,
    memorySessionFilter,
    memoryOnlyPinned,
    includeLessons,
    flowMode = "flow",
    topicFilter = "",
}: UseBrainGraphLogicParams) {
    const {
        data: liveGraph,
        loading: liveGraphLoading,
        error: graphError,
        refresh: refreshGraph,
    } = useKnowledgeGraph(KNOWLEDGE_GRAPH_LIMIT, 0);

    const memoryGraphPoll = useMemoryGraph(
        MEMORY_GRAPH_LIMIT,
        memorySessionFilter || undefined,
        memoryOnlyPinned,
        includeLessons,
        0,
        flowMode,
    );

    const [memoryGraphOverride, setMemoryGraphOverride] = useState<KnowledgeGraph | null>(null);

    const graph = liveGraph ?? initialKnowledge ?? null;
    let memoryGraph = showMemoryLayer ? memoryGraphOverride ?? memoryGraphPoll.data : null;

    // Local filtering for topic
    if (topicFilter.trim() && memoryGraph?.elements?.nodes) {
        const lower = topicFilter.toLowerCase();
        interface GraphNode { data: { topic?: string; label?: string; id?: string } }
        interface GraphEdge { data: { source?: string; target?: string } }

        const filteredNodes = (memoryGraph.elements.nodes as unknown as GraphNode[]).filter(n => {
            const topic = n.data?.topic?.toLowerCase() || "";
            const label = n.data?.label?.toLowerCase() || "";
            return topic.includes(lower) || label.includes(lower);
        });
        const nodeIds = new Set(filteredNodes.map(n => n.data.id).filter(Boolean));
        const filteredEdges = (memoryGraph.elements.edges as unknown as GraphEdge[]).filter(e =>
            nodeIds.has(e.data.source || "") && nodeIds.has(e.data.target || "")
        );

        memoryGraph = {
            ...memoryGraph,
            elements: {
                nodes: filteredNodes as unknown as Array<{ data: Record<string, unknown> }>,
                edges: filteredEdges as unknown as Array<{ data: Record<string, unknown> }>
            }
        };
    }

    const mergedGraph = useMemo(() => {
        if (activeTab === "memory" && showMemoryLayer && memoryGraph?.elements) {
            return memoryGraph;
        }
        if (activeTab === "repo" && graph?.elements) {
            return graph;
        }
        return null;
    }, [activeTab, graph, memoryGraph, showMemoryLayer]);

    const loading =
        (activeTab === "repo" && liveGraphLoading && !graph) ||
        (activeTab === "memory" && memoryGraphPoll.loading && !memoryGraph);

    const error = activeTab === "repo" ? graphError : memoryGraphPoll.error;

    return {
        mergedGraph,
        loading,
        error,
        refreshGraph,
        refreshMemoryGraph: memoryGraphPoll.refresh,
        setMemoryGraphOverride,
        memoryGraphStats: memoryGraph?.stats,
        memoryElements: memoryGraph?.elements,
    };
}

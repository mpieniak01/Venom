import { KnowledgeGraph } from "@/lib/types";
import { useMemo, useState } from "react";
import { useKnowledgeGraph, useMemoryGraph, KNOWLEDGE_GRAPH_LIMIT, MEMORY_GRAPH_LIMIT } from "@/hooks/use-api";

export function useBrainGraphLogic(
    initialKnowledge: KnowledgeGraph | null,
    activeTab: "repo" | "memory" | "hygiene",
    showMemoryLayer: boolean,
    memorySessionFilter: string,
    memoryOnlyPinned: boolean,
    includeLessons: boolean
) {
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
        "flow",
    );

    const [memoryGraphOverride, setMemoryGraphOverride] = useState<KnowledgeGraph | null>(null);

    const graph = liveGraph ?? initialKnowledge ?? null;
    const memoryGraph = showMemoryLayer ? memoryGraphOverride ?? memoryGraphPoll.data : null;

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

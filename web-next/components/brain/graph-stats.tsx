import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";

interface GraphStatsProps {
    summaryNodes: string | number;
    summaryEdges: string | number;
    summaryUpdated?: string;
    activeTab: "repo" | "memory" | "hygiene";
    memoryLimit: number;
    renderedNodes: number;
    sourceTotalNodes: number;
    renderedEdges: number;
    sourceTotalEdges: number;
}

export function GraphStats({
    summaryNodes,
    summaryEdges,
    summaryUpdated,
    activeTab,
    memoryLimit,
    renderedNodes,
    sourceTotalNodes,
    renderedEdges,
    sourceTotalEdges,
}: GraphStatsProps) {
    const t = useTranslation();
    return (
        <div className="flex flex-wrap items-center gap-2">
            <Badge tone="neutral">{t("brain.stats.nodes")}: {summaryNodes}</Badge>
            <Badge tone="neutral">{t("brain.stats.edges")}: {summaryEdges}</Badge>
            <Badge tone="warning">{t("brain.home.updated")}: {summaryUpdated ?? "—"}</Badge>
            <Badge tone="neutral">
                {t("brain.home.source")}: {activeTab === "repo" ? t("brain.home.knowledge") : t("brain.home.memory")}
            </Badge>
            {activeTab === "memory" ? <Badge tone="neutral">Limit: {memoryLimit}</Badge> : null}
            <Badge tone="neutral">
                Render: {renderedNodes}/{sourceTotalNodes} • {renderedEdges}/{sourceTotalEdges}
            </Badge>
        </div>
    );
}

import { Badge } from "@/components/ui/badge";
import { useTranslation } from "@/lib/i18n";

interface GraphStatsProps {
    readonly summaryNodes: string | number;
    readonly summaryEdges: string | number;
    readonly summaryUpdated?: string;
    readonly activeTab: "repo" | "memory" | "hygiene";
    readonly memoryLimit: number;
    readonly renderedNodes: number;
    readonly sourceTotalNodes: number;
    readonly renderedEdges: number;
    readonly sourceTotalEdges: number;
    readonly loading?: boolean;
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
    loading = false,
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
            {activeTab === "memory" ? <Badge tone="neutral">{t("brain.stats.limit")}: {memoryLimit}</Badge> : null}
            <Badge tone="neutral">
                {t("brain.stats.render")}: {loading ? "…" : `${renderedNodes}/${sourceTotalNodes} • ${renderedEdges}/${sourceTotalEdges}`}
            </Badge>
        </div>
    );
}

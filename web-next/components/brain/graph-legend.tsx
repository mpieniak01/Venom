import { useTranslation } from "@/lib/i18n";

interface GraphLegendProps {
    readonly activeTab: "repo" | "memory" | "hygiene";
    readonly showEdgeLabels: boolean;
}

export function GraphLegend({ activeTab, showEdgeLabels }: GraphLegendProps) {
    const t = useTranslation();
    return (
        <div className="flex flex-wrap gap-3 text-xs text-white">
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
                <span className="text-zinc-400">{t("brain.controls.legend")}</span>
                {activeTab === "repo" ? (
                    <span className="flex items-center gap-1">
                        <span className="h-2 w-2 rounded-full bg-indigo-400" />
                        <span>file / function</span>
                    </span>
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
            {activeTab === "memory" && (
                <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-black/60 px-3 py-2">
                    <span className="text-zinc-400">{t("brain.controls.edgeLabels")}:</span>
                    <span className="text-zinc-200">
                        {showEdgeLabels ? t("brain.controls.edgeLabels") : t("brain.controls.defaultHidden")}
                    </span>
                </div>
            )}
        </div>
    );
}

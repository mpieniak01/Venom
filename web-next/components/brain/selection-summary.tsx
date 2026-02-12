import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { RelationEntry } from "./relation-list";

interface BrainSelectionSummaryProps {
    readonly selected: Record<string, unknown> | null;
    readonly relations: RelationEntry[];
    readonly onOpenDetails: () => void;
}

export function BrainSelectionSummary({ selected, relations, onOpenDetails }: Readonly<BrainSelectionSummaryProps>) {
    const t = useTranslation();

    if (!selected) {
        return (
            <div className="card-shell card-base p-4 text-sm">
                <h4 className="heading-h4">{t("brain.selection.title")}</h4>
                <p className="mt-3 text-hint">{t("brain.selection.empty")}</p>
            </div>
        );
    }

    return (
        <div className="card-shell card-base p-4 text-sm">
            <h4 className="heading-h4">{t("brain.selection.title")}</h4>
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
                        {String(selected.type || "n/a")}
                    </span>
                </p>
                <p>
                    <span className="text-zinc-400">{t("brain.selection.relations")}:</span>{" "}
                    <span className="font-semibold">{relations.length}</span>
                </p>
                <p className="text-hint">{t("brain.selection.hint")}</p>
                <Button
                    size="xs"
                    variant="outline"
                    className="text-caption"
                    onClick={onOpenDetails}
                >
                    {t("brain.selection.details")}
                </Button>
            </div>
        </div>
    );
}

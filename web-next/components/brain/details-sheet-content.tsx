import { Button } from "@/components/ui/button";
import { SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useTranslation } from "@/lib/i18n";
import { RelationEntry } from "./relation-list";

interface BrainDetailsSheetContentProps {
    readonly selected: Record<string, unknown> | null;
    readonly relations: RelationEntry[];
    readonly memoryActionPending: string | null;
    readonly onPin: (id: string, pinned: boolean) => void;
    readonly onDelete: (id: string) => void;
    readonly memoryWipePending?: boolean;
    readonly onClearSession?: () => void;
}

export function BrainDetailsSheetContent({
    selected,
    relations,
    memoryActionPending,
    onPin,
    onDelete,
    memoryWipePending,
    onClearSession,
}: Readonly<BrainDetailsSheetContentProps>) {
    const t = useTranslation();

    if (!selected) {
        return <p className="text-hint p-6">{t("brain.details.selectNode")}</p>;
    }

    return (
        <SheetContent className="bg-zinc-950/95 text-white">
            <SheetHeader>
                <SheetTitle>{String(selected.label || selected.id || "Node")}</SheetTitle>
                <SheetDescription>
                    {t("brain.details.type")}: {String(selected.type || "n/a")}
                </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 text-sm text-zinc-300 mt-6">
                <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">{t("brain.details.properties")}</p>
                    <pre className="mt-2 max-h-60 overflow-auto rounded-xl box-muted p-3 text-xs text-zinc-100">
                        {JSON.stringify(selected, null, 2)}
                    </pre>
                </div>

                {String(selected.type) === "memory" && !!selected.id && (
                    <div className="flex flex-col gap-2">
                        <div className="flex flex-wrap gap-2">
                            <Button
                                size="sm"
                                variant="outline"
                                disabled={memoryActionPending === selected.id}
                                onClick={() => onPin(String(selected.id), !selected.pinned)}
                            >
                                {selected.pinned ? t("brain.actions.unpin") : t("brain.actions.pin")}
                            </Button>
                            <Button
                                size="sm"
                                variant="danger"
                                disabled={memoryActionPending === selected.id}
                                onClick={() => onDelete(String(selected.id))}
                            >
                                {t("brain.actions.delete")}
                            </Button>
                        </div>
                        {onClearSession && (
                            <Button
                                size="sm"
                                variant="ghost"
                                className="text-zinc-500 hover:text-red-400 justify-start px-0"
                                disabled={memoryWipePending}
                                onClick={onClearSession}
                            >
                                {memoryWipePending ? t("brain.details.clearing") : t("brain.details.clearSession")}
                            </Button>
                        )}
                    </div>
                )}

                <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">{t("brain.details.relations")}</p>
                    {relations.length === 0 ? (
                        <p className="text-hint">{t("brain.details.noRelations")}</p>
                    ) : (
                        <ul className="mt-2 space-y-2 text-xs">
                            {relations.map((rel) => (
                                <li key={`${selected.id}-${rel.id}-${rel.direction}`} className="rounded-xl box-base px-3 py-2">
                                    <span className="font-semibold text-white">{rel.label || rel.id}</span>
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
        </SheetContent>
    );
}

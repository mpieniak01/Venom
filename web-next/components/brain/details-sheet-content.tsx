import { Button } from "@/components/ui/button";
import { SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useTranslation } from "@/lib/i18n";
import { RelationEntry } from "./relation-list";

interface BrainDetailsSheetContentProps {
    selected: Record<string, unknown> | null;
    relations: RelationEntry[];
    memoryActionPending: string | null;
    onPin: (id: string, pinned: boolean) => void;
    onDelete: (id: string) => void;
}

export function BrainDetailsSheetContent({
    selected,
    relations,
    memoryActionPending,
    onPin,
    onDelete,
}: BrainDetailsSheetContentProps) {
    const t = useTranslation();

    if (!selected) {
        return <p className="text-hint p-6">Kliknij węzeł, by zobaczyć szczegóły.</p>;
    }

    return (
        <SheetContent className="bg-zinc-950/95 text-white">
            <SheetHeader>
                <SheetTitle>{String(selected.label || selected.id || "Node")}</SheetTitle>
                <SheetDescription>
                    Typ: {String(selected.type || "n/a")}
                </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 text-sm text-zinc-300 mt-6">
                <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">Właściwości</p>
                    <pre className="mt-2 max-h-60 overflow-auto rounded-xl box-muted p-3 text-xs text-zinc-100">
                        {JSON.stringify(selected, null, 2)}
                    </pre>
                </div>

                {selected.type === "memory" && selected.id && (
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
                )}

                <div>
                    <p className="text-xs uppercase tracking-wide text-zinc-500">Relacje</p>
                    {relations.length === 0 ? (
                        <p className="text-hint">Brak relacji.</p>
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

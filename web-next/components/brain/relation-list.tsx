import { useTranslation } from "@/lib/i18n";

export interface RelationEntry {
    id: string;
    label?: string;
    type?: string;
    direction: "in" | "out";
}

interface RelationListProps {
    readonly selectedId: string;
    readonly relations: RelationEntry[];
}

export function RelationList({ selectedId, relations }: Readonly<RelationListProps>) {
    const t = useTranslation();
    return (
        <div className="card-shell card-base p-4 text-sm">
            <h4 className="heading-h4">{t("brain.relations.title")}</h4>
            {relations.length > 0 ? (
                <ul className="mt-3 space-y-2 text-xs">
                    {relations.slice(0, 5).map((rel) => (
                        <li key={`${selectedId}-${rel.id}-${rel.direction}`} className="rounded-2xl box-muted px-3 py-2">
                            <span className="font-semibold text-white">{rel.label || rel.id}</span>{" "}
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
                <p className="mt-3 text-hint">{t("brain.relations.empty")}</p>
            )}
        </div>
    );
}

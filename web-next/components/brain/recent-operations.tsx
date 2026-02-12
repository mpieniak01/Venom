import { useTranslation } from "@/lib/i18n";

interface RecentOperation {
    id: string;
    title: string;
    summary: string;
    timestamp: string | null;
    tags: string[];
}

interface RecentOperationsProps {
    readonly operations: RecentOperation[];
}

export function RecentOperations({ operations }: RecentOperationsProps) {
    const t = useTranslation();
    return (
        <div className="card-shell card-base p-4 text-sm">
            <h4 className="heading-h4">{t("brain.recentOperations.title")}</h4>
            {operations.length === 0 ? (
                <p className="mt-3 text-hint">{t("brain.recentOperations.empty")}</p>
            ) : (
                <ul className="mt-3 space-y-2 text-xs text-zinc-300">
                    {operations.map((op) => (
                        <li key={op.id} className="rounded-2xl box-subtle px-3 py-2 shadow-inner">
                            <p className="font-semibold text-white">{op.title}</p>
                            <p className="text-caption">{op.timestamp ? new Date(op.timestamp).toLocaleString() : "brak daty"}</p>
                            <p className="text-hint">{op.summary}</p>
                            {op.tags.length > 0 && (
                                <div className="mt-1 flex flex-wrap gap-1">
                                    {op.tags.slice(0, 3).map((tag) => (
                                        <span key={`${op.id}-${tag}`} className="pill-badge text-emerald-200">
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
    );
}

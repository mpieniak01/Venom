"use client";

import { useLessonPruning, useLessonsStats } from "@/hooks/use-api";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Loader2, Trash2, Calendar, Tag, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";

export function LessonPruningPanel() {
    const { pruneByTTL, pruneByTag, dedupeLessons, purgeLessons, pruneLatest } = useLessonPruning();
    const { data: stats, refresh: refreshStats } = useLessonsStats();
    const { pushToast } = useToast();
    const [loading, setLoading] = useState(false);

    // Form states
    const [ttlDays, setTtlDays] = useState("30");
    const [tagToPrune, setTagToPrune] = useState("");
    const [countToPrune, setCountToPrune] = useState("10");

    const handleAction = async (
        actionName: string,
        actionFn: () => Promise<{ deleted: number; remaining: number }>
    ) => {
        if (!window.confirm(`Czy na pewno chcesz wykonać operację: ${actionName}?`)) return;

        setLoading(true);
        try {
            const result = await actionFn();
            pushToast(
                `Sukces: usunięto ${result.deleted}, pozostało: ${result.remaining}`,
                "success"
            );
            refreshStats();
        } catch (err) {
            pushToast(`Błąd podczas ${actionName}`, "error");
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Statistics Card */}
                <div className="bg-black/20 border border-white/10 rounded-2xl p-4">
                    <div className="mb-4">
                        <h3 className="text-sm font-medium text-zinc-400">Statystyki Lekcji</h3>
                    </div>
                    <div>
                        <div className="text-2xl font-bold text-white mb-2">
                            {stats?.stats?.total_lessons ?? "—"}
                        </div>
                        <p className="text-xs text-zinc-500 mb-4">Wszystkich lekcji w bazie</p>
                        <div className="flex flex-wrap gap-2">
                            {stats?.stats?.tag_distribution ? (
                                Object.entries(stats.stats.tag_distribution)
                                    .sort(([, a], [, b]) => (b as number) - (a as number))
                                    .slice(0, 5)
                                    .map(([tag, count]) => (
                                        <Badge key={tag} tone="neutral">
                                            {tag} ({String(count)})
                                        </Badge>
                                    ))
                            ) : (
                                <span className="text-xs text-zinc-600">Brak tagów</span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Maintenance Card */}
                <div className="bg-black/20 border border-white/10 rounded-2xl p-4 col-span-2">
                    <div className="mb-4">
                        <h3 className="text-sm font-medium text-zinc-400">Automatyczna Higiena</h3>
                        <p className="text-xs text-zinc-500">Operacje porządkowe dla bazy wiedzy</p>
                    </div>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 border border-white/5 rounded-lg bg-white/5">
                            <div className="flex items-center gap-3">
                                <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-400">
                                    <RefreshCw className="h-4 w-4" />
                                </div>
                                <div>
                                    <div className="text-sm font-medium text-white">Deduplikacja</div>
                                    <div className="text-xs text-zinc-500">Usuwa identyczne lekcje (tytuł + treść)</div>
                                </div>
                            </div>
                            <Button
                                size="sm" variant="outline"
                                disabled={loading}
                                onClick={() => handleAction("Deduplikacja", dedupeLessons)}
                            >
                                Uruchom
                            </Button>
                        </div>

                        <div className="flex items-center justify-between p-3 border border-red-500/10 rounded-lg bg-red-500/5">
                            <div className="flex items-center gap-3">
                                <div className="h-8 w-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-400">
                                    <Trash2 className="h-4 w-4" />
                                </div>
                                <div>
                                    <div className="text-sm font-medium text-white">Nuke All (Purge)</div>
                                    <div className="text-xs text-zinc-500">Usuwa WSZYSTKIE lekcje bezpowrotnie</div>
                                </div>
                            </div>
                            <Button
                                size="sm" variant="danger"
                                disabled={loading}
                                onClick={() => handleAction("Purge All", purgeLessons)}
                            >
                                Wyczyść
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {/* Prune by TTL */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Calendar className="h-4 w-4" /> Według Wieku
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder="Dni (np. 30)"
                            value={ttlDays}
                            onChange={e => setTtlDays(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={loading || !ttlDays}
                            onClick={() => handleAction(`Usuń starsze niż ${ttlDays} dni`, () => pruneByTTL(Number(ttlDays)))}
                        >
                            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Usuń"}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        Usuwa lekcje starsze niż podana liczba dni.
                    </p>
                </div>

                {/* Prune by Tag */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Tag className="h-4 w-4" /> Według Tagu
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder="Nazwa tagu"
                            value={tagToPrune}
                            onChange={e => setTagToPrune(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={loading || !tagToPrune}
                            onClick={() => handleAction(`Usuń tag #${tagToPrune}`, () => pruneByTag(tagToPrune))}
                        >
                            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Usuń"}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        Usuwa wszystkie lekcje oznaczone danym tagiem.
                    </p>
                </div>

                {/* Prune Latest */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Trash2 className="h-4 w-4" /> Ostatnie Wpisy
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder="Liczba (np. 5)"
                            value={countToPrune}
                            onChange={e => setCountToPrune(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={loading || !countToPrune}
                            onClick={() => handleAction(`Usuń ${countToPrune} ostatnich`, () => pruneLatest(Number(countToPrune)))}
                        >
                            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Usuń"}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        Usuwa N ostatnio dodanych lekcji (cofanie zmian).
                    </p>
                </div>
            </div>
        </div>
    );
}

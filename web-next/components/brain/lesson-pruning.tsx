"use client";

import { useLessonPruning, useLessonsStats } from "@/hooks/use-api";
import { useTranslation } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { Loader2, Trash2, Calendar, Tag, RefreshCw } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import {
    ConfirmDialog,
    ConfirmDialogContent,
    ConfirmDialogTitle,
    ConfirmDialogDescription,
    ConfirmDialogActions,
} from "@/components/ui/confirm-dialog";

export function LessonPruningPanel() {
    const t = useTranslation();
    const { pruneByTTL, pruneByTag, dedupeLessons, purgeLessons, pruneLatest } = useLessonPruning();
    const { data: stats, refresh: refreshStats } = useLessonsStats();
    const { pushToast } = useToast();
    const [loadingActions, setLoadingActions] = useState<Set<string>>(new Set());
    const [confirmDialog, setConfirmDialog] = useState<{
        open: boolean;
        actionName: string;
        actionFn: (() => Promise<{ deleted: number; remaining: number }>) | null;
    }>({ open: false, actionName: "", actionFn: null });

    // Form states
    const [ttlDays, setTtlDays] = useState("30");
    const [tagToPrune, setTagToPrune] = useState("");
    const [countToPrune, setCountToPrune] = useState("10");

    const handleAction = async (
        actionName: string,
        actionFn: () => Promise<{ deleted: number; remaining: number }>
    ) => {
        setConfirmDialog({ open: true, actionName, actionFn });
    };

    const executeAction = async () => {
        if (!confirmDialog.actionFn) return;

        const { actionName, actionFn } = confirmDialog;
        setConfirmDialog({ open: false, actionName: "", actionFn: null });

        setLoadingActions(prev => new Set(prev).add(actionName));
        try {
            const result = await actionFn();
            pushToast(
                `${t("brain.hygiene.opSuccess")} (${result.deleted}, ${result.remaining})`,
                "success"
            );
            refreshStats();
        } catch (err) {
            pushToast(`${t("brain.hygiene.opError")} (${actionName})`, "error");
            console.error(err);
        } finally {
            setLoadingActions(prev => {
                const next = new Set(prev);
                next.delete(actionName);
                return next;
            });
        }
    };

    const isActionLoading = (actionName: string) => loadingActions.has(actionName);

    return (
        <div className="space-y-6 animate-in fade-in">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Statistics Card */}
                <div className="bg-black/20 border border-white/10 rounded-2xl p-4">
                    <div className="mb-4">
                        <h3 className="text-sm font-medium text-zinc-400">{t("brain.hygiene.lessonStats")}</h3>
                    </div>
                    <div>
                        <div className="text-2xl font-bold text-white mb-2">
                            {stats?.stats?.total_lessons ?? "—"}
                        </div>
                        <p className="text-xs text-zinc-500 mb-4">{t("brain.hygiene.totalLessons")}</p>
                        <div className="flex flex-wrap gap-2">
                            {stats?.stats?.tag_distribution ? (
                                Object.entries(stats.stats.tag_distribution)
                                    .sort(([, a], [, b]) => {
                                        const numA = typeof a === "number" ? a : 0;
                                        const numB = typeof b === "number" ? b : 0;
                                        return numB - numA;
                                    })
                                    .slice(0, 5)
                                    .map(([tag, count]) => (
                                        <Badge key={tag} tone="neutral">
                                            {tag} ({String(count)})
                                        </Badge>
                                    ))
                            ) : (
                                <span className="text-xs text-zinc-600">{t("brain.hygiene.noTags")}</span>
                            )}
                        </div>
                    </div>
                </div>

                {/* Maintenance Card */}
                <div className="bg-black/20 border border-white/10 rounded-2xl p-4 col-span-2">
                    <div className="mb-4">
                        <h3 className="text-sm font-medium text-zinc-400">{t("brain.hygiene.autoHygiene")}</h3>
                        <p className="text-xs text-zinc-500">{t("brain.hygiene.autoHygieneDesc")}</p>
                    </div>
                    <div className="space-y-4">
                        <div className="flex items-center justify-between p-3 border border-white/5 rounded-lg bg-white/5">
                            <div className="flex items-center gap-3">
                                <div className="h-8 w-8 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-400">
                                    <RefreshCw className="h-4 w-4" />
                                </div>
                                <div>
                                    <div className="text-sm font-medium text-white">{t("brain.hygiene.deduplication")}</div>
                                    <div className="text-xs text-zinc-500">{t("brain.hygiene.deduplicationDesc")}</div>
                                </div>
                            </div>
                            <Button
                                size="sm" variant="outline"
                                disabled={isActionLoading(t("brain.hygiene.deduplication"))}
                                onClick={() => handleAction(t("brain.hygiene.deduplication"), dedupeLessons)}
                            >
                                {isActionLoading(t("brain.hygiene.deduplication")) ? <Loader2 className="h-4 w-4 animate-spin" /> : t("brain.hygiene.run")}
                            </Button>
                        </div>

                        <div className="flex items-center justify-between p-3 border border-red-500/10 rounded-lg bg-red-500/5">
                            <div className="flex items-center gap-3">
                                <div className="h-8 w-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-400">
                                    <Trash2 className="h-4 w-4" />
                                </div>
                                <div>
                                    <div className="text-sm font-medium text-white">{t("brain.hygiene.nuke")}</div>
                                    <div className="text-xs text-zinc-500">{t("brain.hygiene.nukeDesc")}</div>
                                </div>
                            </div>
                            <Button
                                size="sm" variant="danger"
                                disabled={isActionLoading(t("brain.hygiene.nuke"))}
                                onClick={() => handleAction(t("brain.hygiene.nuke"), purgeLessons)}
                            >
                                {isActionLoading(t("brain.hygiene.nuke")) ? <Loader2 className="h-4 w-4 animate-spin" /> : t("brain.hygiene.clear")}
                            </Button>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {/* Prune by TTL */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Calendar className="h-4 w-4" /> {t("brain.hygiene.byAge")}
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder={t("brain.hygiene.daysPlaceholder")}
                            value={ttlDays}
                            onChange={e => setTtlDays(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={isActionLoading(`${t("brain.hygiene.remove")} > ${ttlDays}d`) || !ttlDays}
                            onClick={() => handleAction(`${t("brain.hygiene.remove")} > ${ttlDays}d`, () => pruneByTTL(Number(ttlDays)))}
                        >
                            {isActionLoading(`${t("brain.hygiene.remove")} > ${ttlDays}d`) ? <Loader2 className="h-4 w-4 animate-spin" /> : t("brain.hygiene.remove")}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        {t("brain.hygiene.byAgeDesc")}
                    </p>
                </div>

                {/* Prune by Tag */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Tag className="h-4 w-4" /> {t("brain.hygiene.byTag")}
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder={t("brain.hygiene.tagName")}
                            value={tagToPrune}
                            onChange={e => setTagToPrune(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={isActionLoading(`${t("brain.hygiene.remove")} #${tagToPrune}`) || !tagToPrune}
                            onClick={() => handleAction(`${t("brain.hygiene.remove")} #${tagToPrune}`, () => pruneByTag(tagToPrune))}
                        >
                            {isActionLoading(`${t("brain.hygiene.remove")} #${tagToPrune}`) ? <Loader2 className="h-4 w-4 animate-spin" /> : t("brain.hygiene.remove")}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        {t("brain.hygiene.byTagDesc")}
                    </p>
                </div>

                {/* Prune Latest */}
                <div className="space-y-3">
                    <h3 className="text-sm font-medium text-zinc-400 flex items-center gap-2">
                        <Trash2 className="h-4 w-4" /> {t("brain.hygiene.recentEntries")}
                    </h3>
                    <div className="flex gap-2">
                        <input
                            placeholder={t("brain.hygiene.countPlaceholder")}
                            value={countToPrune}
                            onChange={e => setCountToPrune(e.target.value)}
                            className="flex-1 bg-black/20 border border-white/10 rounded-md px-3 py-1 text-sm text-white focus:outline-none focus:border-white/30"
                        />
                        <Button
                            variant="secondary"
                            disabled={isActionLoading(`${t("brain.hygiene.remove")} ${countToPrune}`) || !countToPrune}
                            onClick={() => handleAction(`${t("brain.hygiene.remove")} ${countToPrune}`, () => pruneLatest(Number(countToPrune)))}
                        >
                            {isActionLoading(`${t("brain.hygiene.remove")} ${countToPrune}`) ? <Loader2 className="h-4 w-4 animate-spin" /> : t("brain.hygiene.remove")}
                        </Button>
                    </div>
                    <p className="text-xs text-zinc-500">
                        {t("brain.hygiene.recentEntriesDesc")}
                    </p>
                </div>
            </div>

            {/* Confirmation Dialog */}
            <ConfirmDialog open={confirmDialog.open} onOpenChange={(open) => setConfirmDialog(prev => ({ ...prev, open }))}>
                <ConfirmDialogContent>
                    <ConfirmDialogTitle>{t("brain.hygiene.confirmTitle")}</ConfirmDialogTitle>
                    <ConfirmDialogDescription>
                        {t("brain.hygiene.confirmAction", { action: confirmDialog.actionName })}
                        <br />
                        <strong>{t("brain.hygiene.irreversible")}</strong>
                    </ConfirmDialogDescription>
                    <ConfirmDialogActions
                        onConfirm={executeAction}
                        onCancel={() => setConfirmDialog({ open: false, actionName: "", actionFn: null })}
                        confirmLabel={t("brain.hygiene.confirmYes")}
                        cancelLabel={t("brain.hygiene.confirmNo")}
                        confirmVariant="danger"
                    />
                </ConfirmDialogContent>
            </ConfirmDialog>
        </div>
    );
}

"use client";

import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Loader2, Database, Eraser } from "lucide-react";
import { useState } from "react";
import { flushSemanticCache, clearGlobalMemory } from "@/hooks/use-api";
import {
    ConfirmDialog,
    ConfirmDialogContent,
    ConfirmDialogTitle,
    ConfirmDialogDescription,
    ConfirmDialogActions,
} from "@/components/ui/confirm-dialog";

export function CacheManagement() {
    const { pushToast } = useToast();
    const [loading, setLoading] = useState<string | null>(null);
    const [confirmDialog, setConfirmDialog] = useState<{
        open: boolean;
        title: string;
        desc: string;
        action: () => Promise<void>;
    }>({ open: false, title: "", desc: "", action: async () => { } });

    const handleFlushCache = async () => {
        setLoading("cache");
        try {
            const res = await flushSemanticCache();
            pushToast(`Wyczyszczono cache: ${res.deleted} wpisów.`, "success");
        } catch {
            pushToast("Błąd podczas czyszczenia cache.", "error");
        } finally {
            setLoading(null);
        }
    };

    const handleWipeGlobal = async () => {
        setLoading("global");
        try {
            const res = await clearGlobalMemory();
            pushToast(`Wyczyszczono pamięć globalną: ${res.deleted_vectors} wektorów.`, "success");
        } catch {
            pushToast("Błąd podczas czyszczenia pamięci globalnej.", "error");
        } finally {
            setLoading(null);
        }
    };

    const confirmWipeGlobal = () => {
        setConfirmDialog({
            open: true,
            title: "Wyczyścić pamięć globalną?",
            desc: "Ta operacja usunie wszystkie fakty globalne przypisane do użytkownika. Jest nieodwracalna.",
            action: handleWipeGlobal,
        });
    };

    const confirmFlushCache = () => {
        setConfirmDialog({
            open: true,
            title: "Wyczyścić Semantic Cache?",
            desc: "Usunie to wszystkie zapamiętane pary prompt-odpowiedź. Modele będą musiały generować odpowiedzi od nowa.",
            action: handleFlushCache,
        });
    };

    return (
        <div className="bg-black/20 border border-white/10 rounded-2xl p-4">
            <div className="mb-4">
                <h3 className="text-sm font-medium text-zinc-400">Pamięć i Cache</h3>
                <p className="text-xs text-zinc-500">Zarządzanie pamięcią operacyjną i długoterminową</p>
            </div>

            <div className="space-y-4">
                {/* Semantic Cache */}
                <div className="flex items-center justify-between p-3 border border-indigo-500/10 rounded-lg bg-indigo-500/5">
                    <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-indigo-500/10 flex items-center justify-center text-indigo-400">
                            <Database className="h-4 w-4" />
                        </div>
                        <div>
                            <div className="text-sm font-medium text-white">Semantic Cache</div>
                            <div className="text-xs text-zinc-500">Ukryte prompty i odpowiedzi</div>
                        </div>
                    </div>
                    <Button
                        size="sm" variant="outline"
                        disabled={loading === "cache"}
                        onClick={confirmFlushCache}
                    >
                        {loading === "cache" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Flush"}
                    </Button>
                </div>

                {/* Global Memory */}
                <div className="flex items-center justify-between p-3 border border-red-500/10 rounded-lg bg-red-500/5">
                    <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-red-500/10 flex items-center justify-center text-red-400">
                            <Eraser className="h-4 w-4" />
                        </div>
                        <div>
                            <div className="text-sm font-medium text-white">Global Memory</div>
                            <div className="text-xs text-zinc-500">Fakty i preferencje użytkownika</div>
                        </div>
                    </div>
                    <Button
                        size="sm" variant="danger"
                        disabled={loading === "global"}
                        onClick={confirmWipeGlobal}
                    >
                        {loading === "global" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Wipe"}
                    </Button>
                </div>
            </div>

            <ConfirmDialog
                open={confirmDialog.open}
                onOpenChange={(open) => setConfirmDialog(prev => ({ ...prev, open }))}
            >
                <ConfirmDialogContent>
                    <ConfirmDialogTitle>{confirmDialog.title}</ConfirmDialogTitle>
                    <ConfirmDialogDescription>{confirmDialog.desc}</ConfirmDialogDescription>
                    <ConfirmDialogActions
                        onConfirm={async () => {
                            setConfirmDialog(prev => ({ ...prev, open: false }));
                            await confirmDialog.action();
                        }}
                        onCancel={() => setConfirmDialog(prev => ({ ...prev, open: false }))}
                        confirmLabel="Wykonaj"
                        cancelLabel="Anuluj"
                        confirmVariant="danger"
                    />
                </ConfirmDialogContent>
            </ConfirmDialog>
        </div>
    );
}

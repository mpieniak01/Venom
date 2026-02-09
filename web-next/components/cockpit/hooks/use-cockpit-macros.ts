import { useState, useEffect, useMemo, useCallback } from "react";
import { useToast } from "@/components/ui/toast";

export type MacroAction = {
    id: string;
    label: string;
    description: string;
    content: string;
    icon?: string;
    type?: "system" | "user";
};

const MACRO_STORAGE_KEY = "venom-cockpit-macros";

export function useCockpitMacros(
    onSend: (message: string) => Promise<boolean>
) {
    const { pushToast } = useToast();
    const [macroSending, setMacroSending] = useState<string | null>(null);
    const [customMacros, setCustomMacros] = useState<MacroAction[]>([]);
    const [newMacro, setNewMacro] = useState({
        label: "",
        description: "",
        content: "",
    });

    // Load from local storage
    useEffect(() => {
        try {
            const raw = globalThis.window.localStorage.getItem(MACRO_STORAGE_KEY);
            if (raw) {
                const parsed = JSON.parse(raw) as MacroAction[];
                if (Array.isArray(parsed)) {
                    setCustomMacros(parsed);
                }
            }
        } catch (e) {
            console.error("Failed to load macros", e);
        }
    }, []);

    // Save to local storage
    useEffect(() => {
        try {
            globalThis.window.localStorage.setItem(MACRO_STORAGE_KEY, JSON.stringify(customMacros));
        } catch (e) {
            console.error("Failed to save macros", e);
        }
    }, [customMacros]);

    const systemMacros = useMemo<MacroAction[]>(
        () => [
            {
                id: "macro-scan-graph",
                label: "Skanuj graf wiedzy",
                description: "Wywołaj /api/v1/graph/scan i odśwież podgląd Brain.",
                content: "Zeskanuj graf wiedzy i zaktualizuj indeks",
                type: "system",
            },
            {
                id: "macro-check-services",
                label: "Status usług",
                description: "Sprawdź /api/v1/system/services i zgłoś anomalie.",
                content: "Sprawdź status wszystkich usług systemowych i raportuj błędy",
                type: "system",
            },
            {
                id: "macro-roadmap-sync",
                label: "Roadmap sync",
                description: "Poproś Strategy agenta o aktualizację roadmapy.",
                content: "Zaktualizuj roadmapę projektu na podstawie ostatnich zmian",
                type: "system",
            },
            {
                id: "macro-git-audit",
                label: "Git audit",
                description:
                    "Analiza repo: zmiany, konflikty, propozycje comnitów.",
                content: "Przeprowadź audyt repozytorium git, sprawdź status i zaproponuj commity",
                type: "system",
            },
        ],
        []
    );

    const allMacros = useMemo(
        () => [...systemMacros, ...customMacros],
        [systemMacros, customMacros]
    );

    const handleRunMacro = useCallback(
        async (macro: MacroAction) => {
            setMacroSending(macro.id);
            try {
                await onSend(macro.content);
                pushToast(`Uruchomiono makro: ${macro.label}`, "info");
            } catch {
                pushToast("Błąd uruchamiania makra", "error");
            } finally {
                setMacroSending(null);
            }
        },
        [onSend, pushToast]
    );

    const handleAddMacro = useCallback(() => {
        if (!newMacro.label.trim() || !newMacro.content.trim()) {
            pushToast("Nazwa i treść makra są wymagane", "warning");
            return;
        }

        setCustomMacros((prev) => [
            ...prev,
            {
                id: `user-macro-${Date.now()}`,
                label: newMacro.label.trim(),
                description: newMacro.description.trim() || "Makro użytkownika",
                content: newMacro.content.trim(),
                type: "user",
            },
        ]);
        setNewMacro({ label: "", description: "", content: "" });
        pushToast("Dodano nowe makro", "success");
    }, [newMacro, pushToast]);

    const handleDeleteMacro = useCallback((id: string) => {
        setCustomMacros(prev => prev.filter(m => m.id !== id));
        pushToast("Usunięto makro", "info");
    }, [pushToast]);

    const handleClearMacros = useCallback(() => {
        setCustomMacros([]);
        pushToast("Wyczyszczono makra użytkownika", "info");
    }, [pushToast]);

    return {
        allMacros,
        customMacros,
        newMacro,
        setNewMacro,
        macroSending,
        onRunMacro: handleRunMacro,
        onAddMacro: handleAddMacro,
        onDeleteMacro: handleDeleteMacro,
        onClearMacros: handleClearMacros,
        setCustomMacros
    };
}

import { useState, useEffect, useCallback } from "react";
import { apiFetch } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import type { ModelCatalogEntry, ModelCatalogResponse } from "@/lib/types";
import {
    installRegistryModel,
    useModelOperations,
    useModels
} from "@/hooks/use-api";
import {
    readStorageJson,
    writeStorageJson,
    CatalogCachePayload
} from "../models-helpers";

export function useModelCatalog() {
    const { pushToast } = useToast();
    const { t } = useLanguage();
    const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({});

    // Collapse states
    const [trendingCollapsed, setTrendingCollapsed] = useState(false);
    const [catalogCollapsed, setCatalogCollapsed] = useState(false);
    const [searchCollapsed, setSearchCollapsed] = useState(false);

    // Search state
    const [searchQuery, setSearchQuery] = useState("");
    const [searchProvider, setSearchProvider] = useState<"huggingface" | "ollama">("huggingface");
    const [searchResults, setSearchResults] = useState<{
        data: ModelCatalogEntry[];
        loading: boolean;
        error: string | null;
        performed: boolean;
    }>({ data: [], loading: false, error: null, performed: false });

    // Trending & Catalog
    const [trendingHf, setTrendingHf] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });
    const [trendingOllama, setTrendingOllama] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });
    const [catalogHf, setCatalogHf] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });
    const [catalogOllama, setCatalogOllama] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });

    const installed = useModels(0);
    const operations = useModelOperations(10, 0);

    // Inital load
    useEffect(() => {
        const cachedHf = readStorageJson<CatalogCachePayload>("models-trending-hf");
        const cachedOllama = readStorageJson<CatalogCachePayload>("models-trending-ollama");
        const cachedCatalogHf = readStorageJson<CatalogCachePayload>("models-catalog-hf");
        const cachedCatalogOllama = readStorageJson<CatalogCachePayload>("models-catalog-ollama");

        if (cachedHf) setTrendingHf(prev => ({ ...prev, ...cachedHf }));
        if (cachedOllama) setTrendingOllama(prev => ({ ...prev, ...cachedOllama }));
        if (cachedCatalogHf) setCatalogHf(prev => ({ ...prev, ...cachedCatalogHf }));
        if (cachedCatalogOllama) setCatalogOllama(prev => ({ ...prev, ...cachedCatalogOllama }));
    }, []);

    const setPending = useCallback((key: string, value: boolean) => {
        setPendingActions((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        setSearchResults((prev) => ({ ...prev, loading: true, error: null, performed: true }));
        try {
            const params = new URLSearchParams({ query: searchQuery, provider: searchProvider, limit: "12" });
            const response = await apiFetch<ModelCatalogResponse>(`/api/v1/models/search?${params.toString()}`);
            if (response && response.success) {
                setSearchResults({ data: response.models, loading: false, error: null, performed: true });
            } else {
                setSearchResults({ data: [], loading: false, error: response?.error || t("models.search.error"), performed: true });
            }
        } catch (error) {
            setSearchResults({ data: [], loading: false, error: error instanceof Error ? error.message : "Wystąpił błąd", performed: true });
        }
    };

    const handleInstall = async (entry: ModelCatalogEntry) => {
        const key = `install:${entry.provider}:${entry.model_name}`;
        try {
            setPending(key, true);
            await installRegistryModel({ name: entry.model_name, provider: entry.provider, runtime: entry.runtime });
            pushToast(`Instalacja rozpoczęta: ${entry.model_name}`, "info");
            await Promise.all([operations.refresh(), installed.refresh()]);
        } catch {
            pushToast("Nie udało się rozpocząć instalacji.", "error");
        } finally {
            setPending(key, false);
        }
    };

    const refreshTrending = async () => {
        setTrendingHf((prev) => ({ ...prev, loading: true, error: null }));
        setTrendingOllama((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const [hfResponse, ollamaResponse] = await Promise.all([
                apiFetch<ModelCatalogResponse>("/api/v1/models/trending?provider=huggingface"),
                apiFetch<ModelCatalogResponse>("/api/v1/models/trending?provider=ollama"),
            ]);
            const hfPayload = { data: hfResponse.models ?? [], stale: hfResponse.stale, error: hfResponse.error };
            const ollamaPayload = { data: ollamaResponse.models ?? [], stale: ollamaResponse.stale, error: ollamaResponse.error };
            setTrendingHf({ ...hfPayload, loading: false });
            setTrendingOllama({ ...ollamaPayload, loading: false });
            writeStorageJson("models-trending-hf", hfPayload);
            writeStorageJson("models-trending-ollama", ollamaPayload);
        } catch (error) {
            const msg = error instanceof Error ? error.message : "Błąd pobierania trendów";
            setTrendingHf((prev) => ({ ...prev, loading: false, error: msg }));
            setTrendingOllama((prev) => ({ ...prev, loading: false, error: msg }));
        }
    };

    const refreshCatalog = async () => {
        setCatalogHf((prev) => ({ ...prev, loading: true, error: null }));
        setCatalogOllama((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const [hfResponse, ollamaResponse] = await Promise.all([
                apiFetch<ModelCatalogResponse>("/api/v1/models/providers?provider=huggingface"),
                apiFetch<ModelCatalogResponse>("/api/v1/models/providers?provider=ollama"),
            ]);
            const hfPayload = { data: hfResponse.models ?? [], stale: hfResponse.stale, error: hfResponse.error };
            const ollamaPayload = { data: ollamaResponse.models ?? [], stale: ollamaResponse.stale, error: ollamaResponse.error };
            setCatalogHf({ ...hfPayload, loading: false });
            setCatalogOllama({ ...ollamaPayload, loading: false });
            writeStorageJson("models-catalog-hf", hfPayload);
            writeStorageJson("models-catalog-ollama", ollamaPayload);
        } catch (error) {
            const msg = error instanceof Error ? error.message : "Błąd pobierania katalogu";
            setCatalogHf((prev) => ({ ...prev, loading: false, error: msg }));
            setCatalogOllama((prev) => ({ ...prev, loading: false, error: msg }));
        }
    };

    return {
        trendingCollapsed, setTrendingCollapsed,
        catalogCollapsed, setCatalogCollapsed,
        searchCollapsed, setSearchCollapsed,
        searchQuery, setSearchQuery,
        searchProvider, setSearchProvider,
        searchResults, handleSearch,
        trendingHf, trendingOllama, refreshTrending,
        catalogHf, catalogOllama, refreshCatalog,
        handleInstall, pendingActions
    };
}

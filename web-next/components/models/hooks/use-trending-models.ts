import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api-client";
import type { ModelCatalogEntry, ModelCatalogResponse } from "@/lib/types";
import { readStorageJson, writeStorageJson, CatalogCachePayload } from "../models-helpers";

export function useTrendingModels() {
    const [trendingCollapsed, setTrendingCollapsed] = useState(false);
    const [trendingHf, setTrendingHf] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });
    const [trendingOllama, setTrendingOllama] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>({ data: [], loading: false });

    useEffect(() => {
        const cachedHf = readStorageJson<CatalogCachePayload>("models-trending-hf");
        const cachedOllama = readStorageJson<CatalogCachePayload>("models-trending-ollama");

        if (cachedHf) setTrendingHf(prev => ({ ...prev, ...cachedHf }));
        if (cachedOllama) setTrendingOllama(prev => ({ ...prev, ...cachedOllama }));
    }, []);

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

    return {
        trendingCollapsed, setTrendingCollapsed,
        trendingHf, trendingOllama, refreshTrending
    };
}

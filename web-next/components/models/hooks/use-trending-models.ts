import { useState } from "react";
import { apiFetch } from "@/lib/api-client";
import type { ModelCatalogEntry, ModelCatalogResponse } from "@/lib/types";
import { readStorageJson, writeStorageJson, CatalogCachePayload } from "../models-helpers";

const resolveInitialCatalogState = (storageKey: string) => {
    const cached = readStorageJson<CatalogCachePayload>(storageKey);
    if (!cached) return { data: [], loading: false };
    return { data: cached.data ?? [], stale: cached.stale, error: cached.error, loading: false };
};

export function useTrendingModels() {
    const [trendingCollapsed, setTrendingCollapsed] = useState(false);
    const [trendingHf, setTrendingHf] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>(() =>
        resolveInitialCatalogState("models-trending-hf"),
    );
    const [trendingOllama, setTrendingOllama] = useState<{ data: ModelCatalogEntry[]; stale?: boolean; error?: string | null; loading: boolean }>(() =>
        resolveInitialCatalogState("models-trending-ollama"),
    );

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

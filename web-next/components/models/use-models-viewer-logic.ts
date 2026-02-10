import { useState, useEffect, useMemo, useCallback } from "react";
import {
    installRegistryModel,
    removeRegistryModel,
    setActiveLlmServer,
    switchModel,
    useModelOperations,
    useModels,
    useActiveLlmServer,
    useLlmServers
} from "@/hooks/use-api";
import { apiFetch } from "@/lib/api-client";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import type {
    ModelCatalogEntry,
    ModelInfo,
    ModelCatalogResponse
} from "@/lib/types";
import {
    readStorageJson,
    writeStorageJson,
    readStorageItem,
    CatalogCachePayload,
    NewsCachePayload,
    normalizeProvider,
    inferProviderFromName,
    getRuntimeForProvider
} from "./models-helpers";

export function useModelsViewerLogic() {
    const { pushToast } = useToast();
    const { language, t } = useLanguage();
    const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({});

    // Collapse states
    const [newsCollapsed, setNewsCollapsed] = useState(false);
    const [papersCollapsed, setPapersCollapsed] = useState(false);
    const [trendingCollapsed, setTrendingCollapsed] = useState(false);
    const [catalogCollapsed, setCatalogCollapsed] = useState(false);
    const [installedCollapsed, setInstalledCollapsed] = useState(false);
    const [operationsCollapsed, setOperationsCollapsed] = useState(false);
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

    // News & Papers
    const [newsHf, setNewsHf] = useState<{ items: any[]; stale?: boolean; error?: string | null; loading: boolean }>({ items: [], loading: false });
    const [papersHf, setPapersHf] = useState<{ items: any[]; stale?: boolean; error?: string | null; loading: boolean }>({ items: [], loading: false });
    const [newsSort, setNewsSort] = useState<"newest" | "oldest">("newest");

    const installed = useModels(0);
    const operations = useModelOperations(10, 0);
    const llmServers = useLlmServers(0);
    const activeServer = useActiveLlmServer(0);

    const activeRuntime = installed.data?.active;
    const [selectedServer, setSelectedServer] = useState<string | null>(null);
    const [selectedModel, setSelectedModel] = useState<string | null>(null);

    const setPending = useCallback((key: string, value: boolean) => {
        setPendingActions((prev) => ({ ...prev, [key]: value }));
    }, []);

    const handleSearch = async () => {
        if (!searchQuery.trim()) return;
        setSearchResults((prev) => ({ ...prev, loading: true, error: null, performed: true }));
        try {
            const params = new URLSearchParams({ query: searchQuery, provider: searchProvider, limit: "12" });
            const response = await apiFetch<ModelCatalogResponse>(`/api/v1/models/search?${params.toString()}`);
            if (response && (response as any).success) {
                setSearchResults({ data: (response as any).models, loading: false, error: null, performed: true });
            } else {
                setSearchResults({ data: [], loading: false, error: (response as any)?.error || t("models.search.error"), performed: true });
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

    const handleActivate = async (model: ModelInfo) => {
        const key = `activate:${model.name}`;
        try {
            setPending(key, true);
            const runtime = getRuntimeForProvider(model.provider ?? model.source ?? undefined);
            if (runtime !== activeServer.data?.active_server) {
                await setActiveLlmServer(runtime);
            }
            await switchModel(model.name);
            pushToast(`Aktywowano: ${model.name}`, "success");
            await installed.refresh();
        } catch {
            pushToast("Nie udało się aktywować modelu.", "error");
        } finally {
            setPending(key, false);
        }
    };

    const handleRemove = async (model: ModelInfo) => {
        const key = `remove:${model.name}`;
        try {
            setPending(key, true);
            await removeRegistryModel(model.name);
            pushToast(`Usuwanie rozpoczęte: ${model.name}`, "warning");
            await Promise.all([installed.refresh(), operations.refresh()]);
        } catch {
            pushToast("Nie udało się usunąć modelu.", "error");
        } finally {
            setPending(key, false);
        }
    };

    const refreshTrending = async () => {
        setTrendingHf((prev) => ({ ...prev, loading: true, error: null }));
        setTrendingOllama((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const [hfResponse, ollamaResponse] = await Promise.all([
                apiFetch<any>("/api/v1/models/trending?provider=huggingface"),
                apiFetch<any>("/api/v1/models/trending?provider=ollama"),
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
                apiFetch<any>("/api/v1/models/providers?provider=huggingface"),
                apiFetch<any>("/api/v1/models/providers?provider=ollama"),
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

    const refreshNews = async () => {
        setNewsHf((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const response = await apiFetch<any>(`/api/v1/models/news?provider=huggingface&lang=${language}`);
            const payload = { items: response.items ?? [], stale: response.stale, error: response.error };
            setNewsHf({ ...payload, loading: false });
            writeStorageJson(`models-blog-hf-${language}`, payload);
        } catch (error) {
            setNewsHf((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : "Błąd newsów" }));
        }
    };

    const refreshPapers = async () => {
        setPapersHf((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const response = await apiFetch<any>(`/api/v1/models/news?provider=huggingface&type=papers&lang=${language}&limit=3`);
            const payload = { items: response.items ?? [], stale: response.stale, error: response.error };
            setPapersHf({ ...payload, loading: false });
            writeStorageJson(`models-papers-hf-${language}`, payload);
        } catch (error) {
            setPapersHf((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : "Błąd publikacji" }));
        }
    };

    // Memoized lists and options
    const installedBuckets = useMemo(() => {
        const data = installed.data;
        if (!data) return { vllm: [], ollama: [] };
        const providers = data.providers ?? {};
        const vllm = providers.vllm ?? [];
        const ollama = providers.ollama ?? [];
        if (vllm.length || ollama.length) return { vllm, ollama };
        const fallback = Array.isArray(data.models) ? data.models : [];
        return {
            vllm: fallback.filter((m: any) => normalizeProvider(m.provider) === "vllm"),
            ollama: fallback.filter((m: any) => normalizeProvider(m.provider) === "ollama"),
        };
    }, [installed.data]);

    const installedModels = useMemo(() => [...installedBuckets.vllm, ...installedBuckets.ollama], [installedBuckets]);

    const availableModelsForServer = useMemo(() => {
        if (!selectedServer || !installed.data) return installedModels;
        const server = (llmServers.data ?? []).find((s) => s.name === selectedServer);
        const targetProvider = normalizeProvider(server?.provider ?? selectedServer);
        const providersMap = installed.data.providers ?? {};

        let base = targetProvider in providersMap
            ? providersMap[targetProvider] ?? []
            : (installed.data.models ?? []).filter((m: any) => normalizeProvider(m.provider) === targetProvider);

        const lastModels = activeServer.data?.last_models ?? {};
        const lastForServer = targetProvider === "ollama"
            ? lastModels.ollama || lastModels.previous_ollama
            : targetProvider === "vllm" ? lastModels.vllm || lastModels.previous_vllm : null;

        if (!base.length && lastForServer) {
            if (inferProviderFromName(lastForServer) === targetProvider) {
                base = [{ name: lastForServer, provider: targetProvider, source: "cached" }];
            }
        }
        return base;
    }, [selectedServer, installed.data, installedModels, llmServers.data, activeServer.data]);

    const serverOptions = useMemo(() => (llmServers.data ?? []).map((s) => ({ value: s.name, label: s.name })), [llmServers.data]);
    const modelOptions = useMemo(() => availableModelsForServer.map((m: any) => ({ value: m.name, label: m.name })), [availableModelsForServer]);

    // Effects for initial state and syncing
    useEffect(() => {
        const cachedHf = readStorageJson<CatalogCachePayload>("models-trending-hf");
        const cachedOllama = readStorageJson<CatalogCachePayload>("models-trending-ollama");
        const cachedCatalogHf = readStorageJson<CatalogCachePayload>("models-catalog-hf");
        const cachedCatalogOllama = readStorageJson<CatalogCachePayload>("models-catalog-ollama");
        const cachedNewsSort = readStorageItem("models-news-sort");

        if (cachedHf) setTrendingHf(prev => ({ ...prev, ...cachedHf }));
        if (cachedOllama) setTrendingOllama(prev => ({ ...prev, ...cachedOllama }));
        if (cachedCatalogHf) setCatalogHf(prev => ({ ...prev, ...cachedCatalogHf }));
        if (cachedCatalogOllama) setCatalogOllama(prev => ({ ...prev, ...cachedCatalogOllama }));
        if (cachedNewsSort === "newest" || cachedNewsSort === "oldest") setNewsSort(cachedNewsSort);
    }, []);

    useEffect(() => {
        if (selectedServer) return;
        const active = activeServer.data?.active_server;
        if (active) setSelectedServer(active);
    }, [activeServer.data?.active_server, selectedServer]);

    useEffect(() => {
        if (selectedModel) return;
        const activeModel = activeRuntime?.model;
        if (activeModel) {
            setSelectedModel(activeModel);
        } else if (availableModelsForServer.length) {
            setSelectedModel(availableModelsForServer[0].name);
        }
    }, [activeRuntime?.model, selectedModel, availableModelsForServer]);

    return {
        t, language, pendingActions,
        newsCollapsed, setNewsCollapsed, papersCollapsed, setPapersCollapsed,
        trendingCollapsed, setTrendingCollapsed, catalogCollapsed, setCatalogCollapsed,
        installedCollapsed, setInstalledCollapsed, operationsCollapsed, setOperationsCollapsed,
        searchCollapsed, setSearchCollapsed,
        searchQuery, setSearchQuery, searchProvider, setSearchProvider, searchResults, handleSearch,
        trendingHf, trendingOllama, refreshTrending,
        catalogHf, catalogOllama, refreshCatalog,
        newsHf, refreshNews, papersHf, refreshPapers, newsSort, setNewsSort,
        installed, installedBuckets, installedModels, handleInstall, handleActivate, handleRemove,
        operations, activeServer, llmServers,
        selectedServer, setSelectedServer, selectedModel, setSelectedModel,
        serverOptions, modelOptions, activeRuntime
    };
}

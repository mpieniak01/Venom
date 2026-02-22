import { useState, useMemo, useEffect, useCallback } from "react";
import { useToast } from "@/components/ui/toast";
import type { ModelInfo, ModelsResponse } from "@/lib/types";
import {
    removeRegistryModel,
    setActiveLlmServer,
    switchModel,
    useModelOperations,
    useModels,
    useActiveLlmServer,
    useLlmServers
} from "@/hooks/use-api";
import {
    normalizeProvider,
    getRuntimeForProvider
} from "../models-helpers";

export function buildInstalledBuckets(
    data: ModelsResponse | null,
): Record<string, ModelInfo[]> {
    if (!data) return {};
    const buckets: Record<string, ModelInfo[]> = {};
    const providers = data.providers ?? {};

    Object.entries(providers).forEach(([provider, list]) => {
        const normalized = normalizeProvider(provider);
        if (!normalized) return;
        if (!buckets[normalized]) {
            buckets[normalized] = [];
        }
        if (Array.isArray(list)) {
            buckets[normalized].push(...list);
        }
    });

    const fallback = Array.isArray(data.models) ? data.models : [];
    fallback.forEach((model) => {
        const provider = normalizeProvider(model.provider ?? model.source);
        if (!provider) return;
        if (!buckets[provider]) {
            buckets[provider] = [];
        }
        const exists = buckets[provider].some((candidate) => candidate.name === model.name);
        if (!exists) {
            buckets[provider].push(model);
        }
    });

    return buckets;
}

export function resolveModelsForServer(input: {
    selectedServer: string | null;
    llmServers: Array<{ name: string; provider?: string | null }> | null;
    installedBuckets: Record<string, ModelInfo[]>;
    installedModels: ModelInfo[];
}) {
    const { selectedServer, llmServers, installedBuckets, installedModels } = input;
    if (!selectedServer) return installedModels;
    const server = (llmServers ?? []).find((item) => item.name === selectedServer);
    const targetProvider = normalizeProvider(server?.provider ?? selectedServer);
    if (!targetProvider) return installedModels;
    return installedBuckets[targetProvider] ?? [];
}

export function useRuntime() {
    const { pushToast } = useToast();
    const [installedCollapsed, setInstalledCollapsed] = useState(false);
    const [operationsCollapsed, setOperationsCollapsed] = useState(false);
    const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({});

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

    // Memoized lists and options
    const installedBuckets = useMemo(() => {
        return buildInstalledBuckets(installed.data);
    }, [installed.data]);

    const installedModels = useMemo(
        () => Object.values(installedBuckets).flat(),
        [installedBuckets],
    );

    const availableModelsForServer = useMemo(() => {
        return resolveModelsForServer({
            selectedServer,
            llmServers: (llmServers.data ?? []).map((server) => ({
                name: server.name,
                provider: server.provider,
            })),
            installedBuckets,
            installedModels,
        });
    }, [selectedServer, installedBuckets, installedModels, llmServers.data]);

    const serverOptions = useMemo(() => (llmServers.data ?? []).map((s) => ({ value: s.name, label: s.name })), [llmServers.data]);
    const modelOptions = useMemo(() => availableModelsForServer.map((m) => ({ value: m.name, label: m.name })), [availableModelsForServer]);

    // Effects
    useEffect(() => {
        if (selectedServer) return;
        const active = activeServer.data?.active_server;
        if (active) setSelectedServer(active);
    }, [activeServer.data?.active_server, selectedServer]);

    useEffect(() => {
        if (!selectedServer) return;
        const exists = (llmServers.data ?? []).some((server) => server.name === selectedServer);
        if (exists) return;
        const active = activeServer.data?.active_server;
        if (active && (llmServers.data ?? []).some((server) => server.name === active)) {
            setSelectedServer(active);
            return;
        }
        setSelectedServer((llmServers.data ?? [])[0]?.name ?? null);
    }, [activeServer.data?.active_server, llmServers.data, selectedServer]);

    useEffect(() => {
        if (availableModelsForServer.length === 0) {
            if (selectedModel !== null) {
                setSelectedModel(null);
            }
            return;
        }
        if (
            selectedModel &&
            availableModelsForServer.some((model) => model.name === selectedModel)
        ) {
            return;
        }
        const activeModel = activeRuntime?.model;
        if (
            activeModel &&
            availableModelsForServer.some((model) => model.name === activeModel)
        ) {
            setSelectedModel(activeModel);
            return;
        }
        setSelectedModel(availableModelsForServer[0].name);
    }, [activeRuntime?.model, selectedModel, availableModelsForServer]);

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

    return {
        installedCollapsed, setInstalledCollapsed,
        operationsCollapsed, setOperationsCollapsed,
        installed, operations, llmServers, activeServer,
        activeRuntime,
        selectedServer, setSelectedServer,
        selectedModel, setSelectedModel,
        serverOptions, modelOptions,
        installedBuckets, installedModels,
        handleActivate, handleRemove,
        pendingActions,
        setActiveLlmServer, switchModel,
        pushToast
    };
}

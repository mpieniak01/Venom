import { useState, useMemo, useEffect, useCallback } from "react";
import { useToast } from "@/components/ui/toast";
import type { ModelInfo } from "@/lib/types";
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
    inferProviderFromName,
    getRuntimeForProvider
} from "../models-helpers";

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
        const data = installed.data;
        if (!data) return { vllm: [], ollama: [] };
        const providers = data.providers ?? {};
        const vllm = providers.vllm ?? [];
        const ollama = providers.ollama ?? [];
        if (vllm.length || ollama.length) return { vllm, ollama };
        const fallback = Array.isArray(data.models) ? data.models : [];
        return {
            vllm: fallback.filter((m) => normalizeProvider(m.provider) === "vllm"),
            ollama: fallback.filter((m) => normalizeProvider(m.provider) === "ollama"),
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
            : (installed.data.models ?? []).filter((m) => normalizeProvider(m.provider) === targetProvider);

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
    const modelOptions = useMemo(() => availableModelsForServer.map((m) => ({ value: m.name, label: m.name })), [availableModelsForServer]);

    // Effects
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

import { useState, useMemo, useEffect, useCallback } from "react";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import type { LlmRuntimeModelOption, ModelInfo, ModelsResponse } from "@/lib/types";
import {
    removeRegistryModel,
    setActiveLlmRuntime,
    setActiveLlmServer,
    switchModel,
    useActiveLlmServer,
    useLlmRuntimeOptions,
    useModelOperations,
    useModels,
} from "@/hooks/use-api";
import { getRuntimeForProvider, normalizeProvider } from "../models-helpers";

const isCloudRuntime = (runtime: string): runtime is "openai" | "google" =>
    runtime === "openai" || runtime === "google";

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
    runtimeModels: LlmRuntimeModelOption[];
    installedBuckets: Record<string, ModelInfo[]>;
    installedModels: ModelInfo[];
}) {
    const { selectedServer, runtimeModels, installedBuckets, installedModels } = input;
    if (!selectedServer) return installedModels;
    if (runtimeModels.length > 0) {
        return runtimeModels.map((model) => ({
            name: model.name,
            provider: model.provider,
            source: model.source_type,
        }));
    }
    const targetProvider = normalizeProvider(selectedServer);
    if (!targetProvider) return installedModels;
    return installedBuckets[targetProvider] ?? [];
}

export function useRuntime() {
    const { pushToast } = useToast();
    const { t } = useLanguage();
    const [installedCollapsed, setInstalledCollapsed] = useState(false);
    const [operationsCollapsed, setOperationsCollapsed] = useState(false);
    const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({});

    const installed = useModels(0);
    const operations = useModelOperations(10, 0);
    const runtimeOptions = useLlmRuntimeOptions(0);
    const activeServer = useActiveLlmServer(0);

    const activeRuntime = installed.data?.active;
    const [selectedServer, setSelectedServer] = useState<string | null>(null);
    const [selectedModel, setSelectedModel] = useState<string | null>(null);

    const setPending = useCallback((key: string, value: boolean) => {
        setPendingActions((prev) => ({ ...prev, [key]: value }));
    }, []);

    const llmServers = useMemo(
        () =>
            (runtimeOptions.data?.runtimes ?? []).map((runtime) => ({
                name: runtime.runtime_id,
                provider: runtime.runtime_id,
                status: runtime.status,
            })),
        [runtimeOptions.data?.runtimes],
    );

    const installedBuckets = useMemo(() => buildInstalledBuckets(installed.data), [installed.data]);
    const installedModels = useMemo(() => Object.values(installedBuckets).flat(), [installedBuckets]);

    const runtimeModelsForServer = useMemo(() => {
        if (!selectedServer) return [];
        const runtime = (runtimeOptions.data?.runtimes ?? []).find(
            (item) => item.runtime_id === selectedServer,
        );
        return (runtime?.models ?? []).filter((model) => model.chat_compatible !== false);
    }, [runtimeOptions.data?.runtimes, selectedServer]);

    const availableModelsForServer = useMemo(
        () =>
            resolveModelsForServer({
                selectedServer,
                runtimeModels: runtimeModelsForServer,
                installedBuckets,
                installedModels,
            }),
        [installedBuckets, installedModels, runtimeModelsForServer, selectedServer],
    );

    const serverOptions = useMemo(
        () => llmServers.map((server) => ({ value: server.name, label: server.name })),
        [llmServers],
    );
    const modelOptions = useMemo(
        () => availableModelsForServer.map((model) => ({ value: model.name, label: model.name })),
        [availableModelsForServer],
    );

    useEffect(() => {
        if (selectedServer) return;
        const active = activeServer.data?.active_server;
        if (active) {
            setSelectedServer(active);
            return;
        }
        setSelectedServer(llmServers[0]?.name ?? null);
    }, [activeServer.data?.active_server, llmServers, selectedServer]);

    useEffect(() => {
        if (!selectedServer) return;
        if (llmServers.length === 0) return;
        const exists = llmServers.some((server) => server.name === selectedServer);
        if (exists) return;
        const active = activeServer.data?.active_server;
        if (active && llmServers.some((server) => server.name === active)) {
            setSelectedServer(active);
            return;
        }
        setSelectedServer(llmServers[0].name);
    }, [activeServer.data?.active_server, llmServers, selectedServer]);

    useEffect(() => {
        if (availableModelsForServer.length === 0) {
            if (selectedModel !== null) {
                setSelectedModel(null);
            }
            return;
        }
        if (selectedModel && availableModelsForServer.some((model) => model.name === selectedModel)) {
            return;
        }
        const activeModel = activeServer.data?.active_model || activeRuntime?.model;
        if (activeModel && availableModelsForServer.some((model) => model.name === activeModel)) {
            setSelectedModel(activeModel);
            return;
        }
        setSelectedModel(availableModelsForServer[0].name);
    }, [activeRuntime?.model, activeServer.data?.active_model, availableModelsForServer, selectedModel]);

    const activateRuntimeSelection = useCallback(
        async (server: string, model: string | null) => {
            if (!server) return;
            if (isCloudRuntime(server)) {
                await setActiveLlmRuntime(server, model ?? undefined);
            } else {
                if (server !== activeServer.data?.active_server) {
                    await setActiveLlmServer(server);
                }
                if (model) {
                    await switchModel(model);
                }
            }
            await Promise.all([
                activeServer.refresh(),
                installed.refresh(),
                runtimeOptions.refresh(),
            ]);
        },
        [activeServer, installed, runtimeOptions],
    );

    const handleActivateRuntimeModel = useCallback(async (server: string, model: string) => {
        const key = `activate:${server}:${model}`;
        try {
            setPending(key, true);
            await activateRuntimeSelection(server, model);
            pushToast(t("models.toasts.activateSuccess", { name: model }), "success");
        } catch {
            pushToast(t("models.toasts.activateError"), "error");
        } finally {
            setPending(key, false);
        }
    }, [activateRuntimeSelection, pushToast, setPending, t]);

    const handleActivateRuntimeSelection = useCallback(() => {
        if (!selectedServer || !selectedModel) return;
        handleActivateRuntimeModel(selectedServer, selectedModel).catch(() => {
            // Error toast is emitted inside handleActivateRuntimeModel.
        });
    }, [handleActivateRuntimeModel, selectedModel, selectedServer]);

    const handleActivate = async (model: ModelInfo) => {
        const runtime = getRuntimeForProvider(model.provider ?? model.source ?? undefined);
        await handleActivateRuntimeModel(runtime, model.name);
    };

    const handleRemove = async (model: ModelInfo) => {
        const key = `remove:${model.name}`;
        try {
            setPending(key, true);
            await removeRegistryModel(model.name);
            pushToast(t("models.toasts.removeStart", { name: model.name }), "warning");
            await Promise.all([installed.refresh(), operations.refresh()]);
        } catch {
            pushToast(t("models.toasts.removeError"), "error");
        } finally {
            setPending(key, false);
        }
    };

    return {
        installedCollapsed,
        setInstalledCollapsed,
        operationsCollapsed,
        setOperationsCollapsed,
        installed,
        operations,
        llmServers: { ...runtimeOptions, data: llmServers },
        activeServer,
        activeRuntime,
        selectedServer,
        setSelectedServer,
        selectedModel,
        setSelectedModel,
        serverOptions,
        modelOptions,
        installedBuckets,
        installedModels,
        availableModelsForServer,
        handleActivate,
        handleActivateRuntimeSelection,
        handleActivateRuntimeModel,
        activateRuntimeSelection,
        handleRemove,
        pendingActions,
    };
}

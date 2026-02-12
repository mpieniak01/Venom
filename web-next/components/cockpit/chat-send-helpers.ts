import { createParser } from "eventsource-parser";
import { type GenerationParams, type HistoryRequestDetail } from "@/lib/types";
import { parseSlashCommand } from "@/lib/slash-commands";
import { type SendTaskInput } from "@/hooks/use-api";

export type ActiveServerInfo = {
    active_server?: string | null;
    active_model?: string | null;
    active_endpoint?: string | null;
    config_hash?: string | null;
    runtime_id?: string | null;
} | null;

export type RuntimeOverride = {
    configHash?: string | null;
    runtimeId?: string | null
} | null;

export type LocalHistoryEntry = {
    role?: string;
    content?: string;
    session_id?: string;
    request_id?: string;
    timestamp?: string;
};

export type ChatSendParams = {
    labMode: boolean;
    chatMode: "normal" | "direct" | "complex";
    generationParams: GenerationParams | null;
    selectedLlmModel: string;
    activeServerInfo: ActiveServerInfo;
    sessionId: string | null;
    language: string;
    resetSession: () => string | null;
    refreshActiveServer: () => void;
    setActiveLlmRuntime: (runtime: "openai" | "google", model: string) => Promise<{
        config_hash?: string | null;
        runtime_id?: string | null;
    }>;
    sendSimpleChatStream: (payload: {
        content: string;
        model: string | null;
        maxTokens: number | null;
        temperature: number | null;
        sessionId: string | null;
    }) => Promise<Response>;
    sendTask: (payload: SendTaskInput) => Promise<{ task_id?: string | null }>;
    ingestMemoryEntry: (payload: {
        text: string;
        category: string;
        sessionId: string | null;
        userId: string;
        pinned: boolean;
        memoryType: string;
        scope: string;
        timestamp: string;
    }) => Promise<unknown>;
    refreshTasks: () => Promise<unknown>;
    refreshQueue: () => Promise<unknown>;
    refreshHistory: () => Promise<unknown>;
    refreshSessionHistory: () => Promise<unknown>;
    enqueueOptimisticRequest: (
        prompt: string,
        forced?: {
            tool?: string;
            provider?: string;
            intent?: string;
            simpleMode?: boolean;
        },
    ) => string;
    linkOptimisticRequest: (clientId: string, requestId: string | null) => void;
    dropOptimisticRequest: (clientId: string) => void;
    updateSimpleStream: (
        clientId: string,
        patch: { text?: string; status?: string; done?: boolean },
    ) => void;
    recordUiTiming: (key: string, patch: { historyMs?: number; ttftMs?: number }) => void;
    uiTimingsRef: React.MutableRefObject<Map<string, { t0: number; historyMs?: number; ttftMs?: number }>>;
    clearSimpleStream: (clientId: string) => void;
    setLocalSessionHistory: React.Dispatch<React.SetStateAction<Array<LocalHistoryEntry>>>;
    setSimpleRequestDetails: React.Dispatch<React.SetStateAction<Record<string, HistoryRequestDetail>>>;
    setMessage: (message: string | null) => void;
    setSending: (value: boolean) => void;
    setLastResponseDurationMs: React.Dispatch<React.SetStateAction<number | null>>;
    setResponseDurations: React.Dispatch<React.SetStateAction<number[]>>;
    scrollChatToBottom: () => void;
    autoScrollEnabled: React.MutableRefObject<boolean>;
};

export const resolveForcedRuntimeProvider = (
    provider: string | null | undefined,
): string | null => {
    if (provider === "gpt") return "openai";
    if (provider === "gem") return "google";
    return provider ?? null;
};

export const buildRuntimeMeta = (
    runtimeOverride: RuntimeOverride,
    activeServerInfo: ActiveServerInfo,
) => ({
    configHash: runtimeOverride?.configHash ?? activeServerInfo?.config_hash ?? null,
    runtimeId: runtimeOverride?.runtimeId ?? activeServerInfo?.runtime_id ?? null,
});

export const reconcileUserRequestId = (
    setLocalSessionHistory: ChatSendParams["setLocalSessionHistory"],
    fromId: string,
    toId: string,
) => {
    setLocalSessionHistory((prev) =>
        prev.map((entry) => {
            if (entry.request_id === fromId && entry.role === "user") {
                return { ...entry, request_id: toId };
            }
            return entry;
        }),
    );
};

export const upsertHistoryEntry = (
    entries: LocalHistoryEntry[],
    requestId: string,
    role: "user" | "assistant",
    content: string,
    timestamp: string,
    sessionId: string | null,
) => {
    const idx = entries.findIndex((entry) => entry.request_id === requestId && entry.role === role);
    if (idx >= 0) {
        entries[idx] = {
            ...entries[idx],
            content,
            timestamp: entries[idx].timestamp || timestamp,
        };
        return;
    }
    entries.push({
        role,
        content,
        request_id: requestId,
        timestamp,
        session_id: sessionId ?? undefined,
    });
};

export const buildSimpleRequestSteps = (
    timing: { historyMs?: number; ttftMs?: number } | undefined,
    timestamp: string,
): HistoryRequestDetail["steps"] | undefined => {
    const steps = [
        timing?.historyMs !== undefined
            ? {
                component: "UI",
                action: "submit_to_history",
                status: "OK",
                timestamp,
                details: `history_ms=${Math.round(timing.historyMs)}`,
            }
            : null,
        timing?.ttftMs !== undefined
            ? {
                component: "UI",
                action: "ttft",
                status: "OK",
                timestamp,
                details: `ttft_ms=${Math.round(timing.ttftMs)}`,
            }
            : null,
    ].filter(Boolean) as NonNullable<HistoryRequestDetail["steps"]>;
    return steps.length > 0 ? steps : undefined;
};

export const updateDurationMetrics = (params: {
    duration: number;
    setLastResponseDurationMs: ChatSendParams["setLastResponseDurationMs"];
    setResponseDurations: ChatSendParams["setResponseDurations"];
}) => {
    const { duration, setLastResponseDurationMs, setResponseDurations } = params;
    if (!Number.isFinite(duration)) return;
    setLastResponseDurationMs(duration);
    setResponseDurations((prev) => [...prev, duration].slice(-10));
};

export const addInitialSimpleUserHistoryEntry = (
    setLocalSessionHistory: ChatSendParams["setLocalSessionHistory"],
    clientId: string,
    trimmed: string,
    createdTimestamp: string,
    resolvedSession: string | null,
) => {
    setLocalSessionHistory((prev) => {
        const next = [...prev];
        const exists = next.some((entry) => entry.request_id === clientId && entry.role === "user");
        if (!exists) {
            next.push({
                role: "user",
                content: trimmed,
                request_id: clientId,
                timestamp: createdTimestamp,
                session_id: resolvedSession ?? undefined,
            });
        }
        return next;
    });
};

export const buildSimpleStreamRequestPayload = (
    trimmed: string,
    selectedLlmModel: string,
    generationParams: GenerationParams | null,
    resolvedSession: string | null,
) => ({
    content: trimmed,
    model: selectedLlmModel || null,
    maxTokens: typeof generationParams?.max_tokens === "number" ? generationParams.max_tokens : null,
    temperature: typeof generationParams?.temperature === "number" ? generationParams.temperature : null,
    sessionId: resolvedSession,
});

export async function handleSimpleTaskSend(params: {
    clientId: string;
    trimmed: string;
    resolvedSession: string | null;
    generationParams: GenerationParams | null;
    selectedLlmModel: string;
    activeServerInfo: ActiveServerInfo;
    sendSimpleChatStream: ChatSendParams["sendSimpleChatStream"];
    linkOptimisticRequest: ChatSendParams["linkOptimisticRequest"];
    setLocalSessionHistory: ChatSendParams["setLocalSessionHistory"];
    updateSimpleStream: ChatSendParams["updateSimpleStream"];
    recordUiTiming: ChatSendParams["recordUiTiming"];
    uiTimingsRef: ChatSendParams["uiTimingsRef"];
    setSimpleRequestDetails: ChatSendParams["setSimpleRequestDetails"];
    ingestMemoryEntry: ChatSendParams["ingestMemoryEntry"];
    setLastResponseDurationMs: ChatSendParams["setLastResponseDurationMs"];
    setResponseDurations: ChatSendParams["setResponseDurations"];
    dropOptimisticRequest: ChatSendParams["dropOptimisticRequest"];
    clearSimpleStream: ChatSendParams["clearSimpleStream"];
    setMessage: ChatSendParams["setMessage"];
    setSending: ChatSendParams["setSending"];
}) {
    const {
        clientId,
        trimmed,
        resolvedSession,
        generationParams,
        selectedLlmModel,
        activeServerInfo,
        sendSimpleChatStream,
        linkOptimisticRequest,
        setLocalSessionHistory,
        updateSimpleStream,
        recordUiTiming,
        uiTimingsRef,
        setSimpleRequestDetails,
        ingestMemoryEntry,
        setLastResponseDurationMs,
        setResponseDurations,
        dropOptimisticRequest,
        clearSimpleStream,
        setMessage,
        setSending,
    } = params;

    try {
        const createdTimestamp = new Date().toISOString();
        addInitialSimpleUserHistoryEntry(
            setLocalSessionHistory,
            clientId,
            trimmed,
            createdTimestamp,
            resolvedSession,
        );
        updateSimpleStream(clientId, { text: "", status: "W toku", done: false });
        const response = await sendSimpleChatStream(
            buildSimpleStreamRequestPayload(trimmed, selectedLlmModel, generationParams, resolvedSession),
        );
        const headerRequestId = response.headers.get("x-request-id");
        const simpleRequestId = headerRequestId || `simple-${clientId}`;
        linkOptimisticRequest(clientId, simpleRequestId);

        reconcileUserRequestId(setLocalSessionHistory, clientId, simpleRequestId);
        let lastHistoryUpdate = 0;
        const upsertLocalHistory = (role: "user" | "assistant", content: string) => {
            const now = Date.now();
            if (role === "assistant" && now - lastHistoryUpdate < 60) {
                return;
            }
            lastHistoryUpdate = now;
            setLocalSessionHistory((prev) => {
                const next = [...prev];
                upsertHistoryEntry(next, simpleRequestId, role, content, createdTimestamp, resolvedSession);
                return next;
            });
        };
        upsertLocalHistory("user", trimmed);
        const historyTiming = uiTimingsRef.current.get(clientId);
        if (historyTiming && historyTiming.historyMs === undefined) {
            recordUiTiming(clientId, { historyMs: Date.now() - historyTiming.t0 });
        }

        const reader = response.body?.getReader();
        if (!reader) {
            throw new Error("Brak strumienia odpowiedzi z API.");
        }

        const decoder = new TextDecoder();
        let buffer = "";
        const startedAt = Date.now();
        let firstChunkLogged = false;

        const parser = createParser({
            onEvent: (msg) => {
                if (msg.event === "content") {
                    const data = JSON.parse(msg.data);
                    if (data.text) {
                        buffer += data.text;
                        if (!firstChunkLogged) {
                            const ttftTiming = uiTimingsRef.current.get(simpleRequestId);
                            if (ttftTiming && ttftTiming.ttftMs === undefined) {
                                recordUiTiming(simpleRequestId, { ttftMs: Date.now() - ttftTiming.t0 });
                            }
                            firstChunkLogged = true;
                        }
                        updateSimpleStream(clientId, { text: buffer, status: "W toku" });
                        upsertLocalHistory("assistant", buffer);
                    }
                } else if (msg.event === "error") {
                    const data = JSON.parse(msg.data);
                    throw new Error(data.error || "Wystąpił błąd strumieniowania.");
                }
            },
        });

        try {
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                if (chunk) {
                    parser.feed(chunk);
                }
            }
        } finally {
            reader.releaseLock();
        }

        updateSimpleStream(clientId, { text: buffer, status: "COMPLETED", done: true });
        const duration = Date.now() - startedAt;
        const timestamp = new Date().toISOString();
        const simpleModelName = selectedLlmModel || activeServerInfo?.active_model || undefined;
        const simpleEndpoint = activeServerInfo?.active_endpoint ?? undefined;
        setLocalSessionHistory((prev) => {
            const next = [...prev];
            upsertHistoryEntry(next, simpleRequestId, "user", trimmed, timestamp, resolvedSession);
            upsertHistoryEntry(next, simpleRequestId, "assistant", buffer, timestamp, resolvedSession);
            return next;
        });
        const timing = uiTimingsRef.current.get(simpleRequestId);
        const steps = buildSimpleRequestSteps(timing, timestamp);
        const simpleProvider = activeServerInfo?.active_server ?? activeServerInfo?.runtime_id?.split("@")[0] ?? "local";
        setSimpleRequestDetails((prev) => ({
            ...prev,
            [simpleRequestId]: {
                request_id: simpleRequestId,
                prompt: trimmed,
                status: "COMPLETED",
                model: simpleModelName,
                llm_provider: simpleProvider,
                llm_model: simpleModelName ?? null,
                llm_model_name: simpleModelName ?? null,
                llm_endpoint: simpleEndpoint ?? null,
                llm_config_hash: activeServerInfo?.config_hash ?? null,
                llm_runtime_id: activeServerInfo?.runtime_id ?? null,
                forced_tool: null,
                forced_provider: null,
                session_id: resolvedSession ?? null,
                created_at: timestamp,
                finished_at: timestamp,
                duration_seconds: Number.isFinite(duration) ? Math.round((duration / 1000) * 100) / 100 : null,
                steps,
            },
        }));
        try {
            await ingestMemoryEntry({
                text: buffer,
                category: "assistant",
                sessionId: resolvedSession ?? null,
                userId: "user_default",
                pinned: true,
                memoryType: "fact",
                scope: "session",
                timestamp,
            });
        } catch (err) {
            console.warn("Nie udało się zapisać pamięci dla trybu prostego:", err);
        }
        updateDurationMetrics({ duration, setLastResponseDurationMs, setResponseDurations });
        globalThis.window.setTimeout(() => {
            dropOptimisticRequest(clientId);
            clearSimpleStream(clientId);
        }, 200);
    } catch (err) {
        updateSimpleStream(clientId, {
            text: err instanceof Error ? err.message : "Błąd trybu prostego.",
            status: "FAILED",
            done: true,
        });
        dropOptimisticRequest(clientId);
        setMessage(err instanceof Error ? err.message : "Nie udało się wysłać zadania");
        setLocalSessionHistory((prev) => {
            const next = [...prev];
            const exists = next.some((entry) => entry.request_id === clientId && entry.role === "assistant");
            if (!exists) {
                upsertHistoryEntry(
                    next,
                    clientId,
                    "assistant",
                    err instanceof Error ? err.message : "Błąd trybu prostego.",
                    new Date().toISOString(),
                    resolvedSession,
                );
            }
            return next;
        });
    } finally {
        setSending(false);
    }
}

export async function handleStandardTaskSend(params: {
    trimmed: string;
    labMode: boolean;
    generationParams: GenerationParams | null;
    runtimeOverride: RuntimeOverride;
    activeServerInfo: ActiveServerInfo;
    parsed: ReturnType<typeof parseSlashCommand>;
    forcedIntent: string | null;
    language: string;
    resolvedSession: string | null;
    clientId: string;
    sendTask: ChatSendParams["sendTask"];
    linkOptimisticRequest: ChatSendParams["linkOptimisticRequest"];
    setLocalSessionHistory: ChatSendParams["setLocalSessionHistory"];
    refreshTasks: ChatSendParams["refreshTasks"];
    refreshQueue: ChatSendParams["refreshQueue"];
    refreshHistory: ChatSendParams["refreshHistory"];
    refreshSessionHistory: ChatSendParams["refreshSessionHistory"];
    dropOptimisticRequest: ChatSendParams["dropOptimisticRequest"];
    setMessage: ChatSendParams["setMessage"];
    setSending: ChatSendParams["setSending"];
    t: (key: string, vars?: Record<string, string | number>) => string;
}) {
    const {
        trimmed,
        labMode,
        generationParams,
        runtimeOverride,
        activeServerInfo,
        parsed,
        forcedIntent,
        language,
        resolvedSession,
        clientId,
        sendTask,
        linkOptimisticRequest,
        setLocalSessionHistory,
        refreshTasks,
        refreshQueue,
        refreshHistory,
        refreshSessionHistory,
        dropOptimisticRequest,
        setMessage,
        setSending,
        t,
    } = params;
    try {
        const res = await sendTask({
            content: trimmed,
            storeKnowledge: !labMode,
            generationParams,
            runtimeMeta: buildRuntimeMeta(runtimeOverride, activeServerInfo),
            extraContext: null,
            forcedRoute: {
                tool: parsed.forcedTool,
                provider: parsed.forcedProvider,
            },
            forcedIntent,
            preferredLanguage: language as ("pl" | "en" | "de" | null),
            sessionId: resolvedSession,
            preferenceScope: "session",
        });
        const resolvedId = res.task_id ?? null;
        linkOptimisticRequest(clientId, resolvedId);
        if (resolvedId) {
            reconcileUserRequestId(setLocalSessionHistory, clientId, resolvedId);
        }
        const displayId = resolvedId ?? t("cockpit.chatMessages.taskPendingId");
        setMessage(t("cockpit.chatMessages.taskSent", { id: displayId }));
        await Promise.all([refreshTasks(), refreshQueue(), refreshHistory(), refreshSessionHistory()]);
    } catch (err) {
        dropOptimisticRequest(clientId);
        setMessage(err instanceof Error ? err.message : t("cockpit.chatMessages.taskSendError"));
    } finally {
        setSending(false);
    }
}

export async function handleRuntimeSwitch(params: {
    parsed: ReturnType<typeof parseSlashCommand>;
    activeServerInfo: ActiveServerInfo;
    selectedLlmModel: string;
    setActiveLlmRuntime: ChatSendParams["setActiveLlmRuntime"];
    refreshActiveServer: () => void;
    setMessage: (message: string | null) => void;
    confirm: (message: string) => boolean;
    t: (key: string, vars?: Record<string, string | number>) => string;
}) {
    const { parsed, activeServerInfo, selectedLlmModel, setActiveLlmRuntime, refreshActiveServer, setMessage, confirm, t } = params;

    const forcedRuntimeProvider = resolveForcedRuntimeProvider(parsed.forcedProvider);
    const activeRuntime = activeServerInfo?.active_server ?? null;

    if (forcedRuntimeProvider && activeRuntime !== forcedRuntimeProvider) {
        const label = forcedRuntimeProvider === "openai" ? "OpenAI" : "Gemini";
        const confirmed = confirm(
            t("cockpit.runtime.switchConfirm", { label })
        );
        if (!confirmed) {
            setMessage(t("cockpit.runtime.switchCancelled"));
            return { success: false, runtimeOverride: null };
        }
        try {
            const runtime = await setActiveLlmRuntime(forcedRuntimeProvider as "openai" | "google", selectedLlmModel);
            refreshActiveServer();
            return {
                success: true,
                runtimeOverride: {
                    configHash: runtime.config_hash ?? null,
                    runtimeId: runtime.runtime_id ?? null,
                }
            };
        } catch (err) {
            setMessage(err instanceof Error ? err.message : t("cockpit.runtime.switchError"));
            return { success: false, runtimeOverride: null };
        }
    }
    return { success: true, runtimeOverride: null };
}

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import { orderHistoryEntriesByRequestId } from "./history-order";
import {
    useSessionHistoryState,
    useHiddenPromptState,
    useTrackedRequestIds,
} from "@/components/cockpit/cockpit-hooks";
import { useTaskStream } from "@/hooks/use-task-stream";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useCockpitSessionActions } from "@/components/cockpit/cockpit-session-actions";
import { useCockpitRequestDetailActions } from "@/components/cockpit/cockpit-request-detail-actions";
import { useCockpitChatUi } from "@/components/cockpit/cockpit-chat-ui";
import {
    clearSessionMemory,
    clearGlobalMemory,
    fetchModelConfig,
    updateModelConfig,
    sendSimpleChatStream,
    sendTask,
    ingestMemoryEntry,
    sendFeedback,
    fetchTaskDetail,
    fetchHistoryDetail,
    toggleQueue,
    purgeQueue,
    emergencyStop,
    setActiveLlmRuntime,
    setActiveLlmServer,
    switchModel,
    useSessionHistory,
    useHiddenPrompts,
    useActiveHiddenPrompts,
    setActiveHiddenPrompt,
} from "@/hooks/use-api";

import { filterHistoryAfterReset, mergeHistoryFallbacks } from "@/components/cockpit/hooks/history-merge";

import { useCockpitData } from "./use-cockpit-data";
import { useCockpitInteractiveState } from "./use-cockpit-interactive-state";
import { useCockpitLayout } from "./use-cockpit-layout";
import { useCockpitMacros } from "./use-cockpit-macros";
import { useCockpitMetricsDisplay } from "./use-cockpit-metrics-display";

type Data = ReturnType<typeof useCockpitData>;
type Interactive = ReturnType<typeof useCockpitInteractiveState>;
type Layout = ReturnType<typeof useCockpitLayout>;


const mapRole = (role: string | undefined): "user" | "assistant" => {
    if (role === "assistant") return "assistant";
    return "user"; // Fallback for "user", "system", or unknown
};

type HistoryEntryLike = {
    role?: string;
    content?: string;
    request_id?: string;
    timestamp?: string;
    pending?: boolean;
    status?: string | null;
    contextUsed?: { lessons?: string[]; memory_entries?: string[] } | null;
    session_id?: string;
    policy_blocked?: boolean;
    reason_code?: string | null;
    user_message?: string | null;
};

type StreamLike = {
    result?: string;
    status?: string;
    contextUsed?: { lessons?: string[]; memory_entries?: string[] } | null;
};

type HistoryTaskLike = {
    request_id: string;
    status?: string | null;
    session_id?: string | null;
};

type TaskDetailLike = {
    result?: string | null;
    created_at?: string | null;
    context_history?: { session?: { session_id?: string } };
};

type FeedbackValue = { rating?: "up" | "down" | null; comment?: string };
type ContextPreviewMeta = {
    preview: string | null;
    truncated: boolean;
    hiddenPrompts: number | null;
    mode: string | null;
};
type TaskDetailStep = { component?: string; action?: string; details?: string | null };

const execPattern = (pattern: RegExp, value: string) => pattern.exec(value);

const resolvePreviewFromContext = (ctx: Record<string, unknown>) => {
    if (typeof ctx.preview === "string") return ctx.preview;
    if (typeof ctx.prompt_context_preview === "string") return ctx.prompt_context_preview;
    return null;
};

const parseContextStepDetails = (details: string): ContextPreviewMeta | null => {
    if (details.startsWith("{")) {
        try {
            const parsed = JSON.parse(details) as Record<string, unknown>;
            return {
                preview:
                    (parsed.preview as string) ||
                    (parsed.context as string) ||
                    (parsed.prompt as string) ||
                    (parsed.prompt_context_preview as string) ||
                    null,
                truncated: !!parsed.truncated || !!parsed.prompt_context_truncated,
                hiddenPrompts: typeof parsed.hidden_prompts_count === "number" ? parsed.hidden_prompts_count : null,
                mode: typeof parsed.mode === "string" ? parsed.mode : null,
            };
        } catch {
            return null;
        }
    }
    const previewMatch = execPattern(/(?:preview|prompt|context|prompt_context_preview)=([\s\S]*?)(?:$|\s\w+=)/, details);
    const hiddenMatch = execPattern(/hidden_prompts_count=(\d+)/, details);
    const modeMatch = execPattern(/mode=(\w+)/, details);
    if (!previewMatch && !hiddenMatch) return null;
    return {
        preview: previewMatch ? previewMatch[1].trim() : null,
        truncated: details.includes("truncated=true") || details.includes("truncated\":true"),
        hiddenPrompts: hiddenMatch ? Number.parseInt(hiddenMatch[1], 10) : null,
        mode: modeMatch ? modeMatch[1] : null,
    };
};

const parseLlmStepDetails = (details: string): ContextPreviewMeta | null => {
    if (details.startsWith("{")) {
        try {
            const parsed = JSON.parse(details) as Record<string, unknown>;
            return {
                preview:
                    (parsed.prompt as string) ||
                    (parsed.payload as string) ||
                    (parsed.input as string) ||
                    null,
                truncated: false,
                hiddenPrompts: null,
                mode: null,
            };
        } catch {
            return null;
        }
    }
    const promptMatch = execPattern(/(?:prompt|payload|input)=([\s\S]*?)(?:$|\s\w+=)/, details);
    if (!promptMatch) return null;
    return {
        preview: promptMatch[1].trim(),
        truncated: false,
        hiddenPrompts: null,
        mode: null,
    };
};

const isContextStep = (step: TaskDetailStep) =>
    step.component === "ContextBuilder" ||
    step.action === "context_preview" ||
    step.details?.includes("preview=") ||
    step.details?.includes("preview\"") ||
    step.details?.includes("prompt_context_preview");

const isHiddenPromptsStep = (step: TaskDetailStep) =>
    step.action === "hidden_prompts" ||
    step.details?.includes("hidden_prompts") ||
    step.details?.includes("hiddenPrompts");

const isLlmStep = (step: TaskDetailStep) =>
    (step.component === "LLM" && step.action === "start") ||
    (step.component === "ChatAgent" && step.action === "process_task") ||
    step.details?.includes("prompt=") ||
    step.details?.includes("payload=") ||
    step.details?.includes("input=");

const extractHiddenPrompts = (details: string) => {
    const hiddenMatch =
        execPattern(/hidden_prompts:?\s*(\d+)/i, details) ||
        execPattern(/hidden_prompts_count=(\d+)/, details);
    if (!hiddenMatch) return null;
    return Number.parseInt(hiddenMatch[1], 10);
};

const parseContextPreviewFromSteps = (steps: TaskDetailStep[]) => {
    const contextStep = steps.find(isContextStep);
    const hiddenStep = steps.find(isHiddenPromptsStep);
    let meta = contextStep?.details ? parseContextStepDetails(contextStep.details.trim()) : null;

    if (!meta && contextStep === undefined) {
        const llmStep = steps.find(isLlmStep);
        if (llmStep?.details) {
            meta = parseLlmStepDetails(llmStep.details.trim());
        }
    }

    if (!hiddenStep?.details) return meta;
    const hiddenPrompts = extractHiddenPrompts(hiddenStep.details);
    if (hiddenPrompts === null) return meta;

    return {
        ...(meta ?? { preview: null, truncated: false, mode: null, hiddenPrompts: null }),
        hiddenPrompts,
    };
};

function mergeStreamsIntoHistory(
    deduped: HistoryEntryLike[],
    taskStreams: Record<string, StreamLike>,
) {
    Object.entries(taskStreams).forEach(([taskId, stream]) => {
        const content = stream.result || "";
        const isPending = stream.status === "PROCESSING" || stream.status === "PENDING";
        const index = deduped.findIndex(
            (entry) => entry.request_id === taskId && entry.role === "assistant",
        );

        if (index !== -1) {
            if (content && content.length > (deduped[index].content?.length || 0)) {
                deduped[index] = {
                    ...deduped[index],
                    content,
                    pending: isPending,
                    status: stream.status,
                    contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
                };
            } else if (isPending && !deduped[index].pending) {
                deduped[index] = {
                    ...deduped[index],
                    pending: true,
                    status: stream.status,
                    contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
                };
            }
            return;
        }

        if (content || isPending) {
            deduped.push({
                role: "assistant",
                content,
                request_id: taskId,
                timestamp: new Date().toISOString(),
                pending: isPending,
                status: stream.status,
                contextUsed: stream.contextUsed ?? undefined,
            });
        }
    });
}

function toHistoryMessages(entries: HistoryEntryLike[]) {
    return entries.map((entry, index) => {
        const fallbackId = `msg-${index}-${entry.timestamp}`;
        const uniqueId = entry.request_id ? `${entry.request_id}-${entry.role}` : fallbackId;
        return {
            bubbleId: uniqueId,
            role: mapRole(entry.role),
            text: entry.content || "",
            requestId: entry.request_id ?? null,
            timestamp: entry.timestamp ?? "",
            pending: entry.pending || false,
            status: entry.status || null,
            contextUsed: entry.contextUsed ?? null,
            policyBlocked: entry.policy_blocked ?? false,
            reasonCode: entry.reason_code ?? null,
            userMessage: entry.user_message ?? null,
        };
    });
}

function parseContextPreviewMeta(
    selectedTask: { context_history?: Record<string, unknown> } | null,
    detail: { steps?: TaskDetailStep[] } | null,
) {
    const ctx = selectedTask?.context_history;
    const preview = ctx ? resolvePreviewFromContext(ctx) : null;
    if (preview) {
        return {
            preview,
            truncated: !!ctx?.truncated || !!ctx?.prompt_context_truncated,
            hiddenPrompts: typeof ctx?.hidden_prompts_count === "number" ? ctx.hidden_prompts_count : null,
            mode: typeof ctx?.mode === "string" ? ctx.mode : null,
        };
    }

    const steps = detail?.steps;
    if (!steps) return null;
    return parseContextPreviewFromSteps(steps);
}

function shouldHydrateCompletedTask(
    task: HistoryTaskLike,
    sessionId: string | null,
    hydratedIds: Set<string>,
    localSessionHistory: HistoryEntryLike[],
    taskStreams: Record<string, StreamLike>,
): boolean {
    if (task.status !== "COMPLETED") return false;
    if (!sessionId || task.session_id !== sessionId) return false;
    if (hydratedIds.has(task.request_id)) return false;
    const hasAssistantMessage = localSessionHistory.some(
        (msg) => msg.request_id === task.request_id && msg.role === "assistant" && msg.content,
    );
    if (hasAssistantMessage) return false;
    const stream = taskStreams[task.request_id];
    return !stream?.result;
}

function upsertHydratedAssistantMessage(
    prev: HistoryEntryLike[],
    requestId: string,
    content: string,
    timestamp: string,
): HistoryEntryLike[] {
    if (prev.some((entry) => entry.request_id === requestId && entry.role === "assistant")) {
        return prev;
    }
    return [...prev, {
        role: "assistant",
        content,
        request_id: requestId,
        timestamp,
    }].sort((a, b) => new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime());
}

async function hydrateCompletedTask(input: {
    requestId: string;
    sessionId: string;
    setLocalSessionHistory: (updater: (prev: HistoryEntryLike[]) => HistoryEntryLike[]) => void;
}) {
    const { requestId, sessionId, setLocalSessionHistory } = input;
    try {
        const taskDetail = await fetchTaskDetail(requestId);
        const detail = taskDetail as TaskDetailLike;
        const detailSession = detail.context_history?.session?.session_id ?? null;
        if (detailSession && detailSession !== sessionId) return;
        if (!detail.result) return;
        setLocalSessionHistory((prev) =>
            upsertHydratedAssistantMessage(
                prev,
                requestId,
                detail.result || "",
                detail.created_at || new Date().toISOString(),
            ),
        );
    } catch (err: unknown) {
        if ((err as { status?: number })?.status !== 404 && !(err as { message?: string })?.message?.includes("404")) {
            console.error("Failed to hydrate task", requestId, err);
        }
    }
}

function extractFeedbackUpdates(
    history: Array<{ request_id?: string; feedback?: { rating?: string; comment?: string | null } | null }> | null | undefined,
    detail: { request_id?: string; feedback?: { rating?: string; comment?: string | null } | null } | null | undefined,
): Record<string, FeedbackValue> {
    const updates: Record<string, FeedbackValue> = {};
    if (history) {
        history.forEach((item) => {
            if (item.feedback && item.request_id) {
                updates[item.request_id] = {
                    rating: item.feedback.rating as "up" | "down",
                    comment: item.feedback.comment ?? undefined,
                };
            }
        });
    }
    if (detail?.feedback && detail.request_id) {
        updates[detail.request_id] = {
            rating: detail.feedback.rating as "up" | "down",
            comment: detail.feedback.comment ?? undefined,
        };
    }
    return updates;
}

function mergeFeedbackUpdates(
    prev: Record<string, FeedbackValue>,
    updates: Record<string, FeedbackValue>,
): Record<string, FeedbackValue> {
    const copy = { ...prev };
    let changed = false;
    for (const [id, value] of Object.entries(updates)) {
        if (prev[id]?.rating !== value.rating || prev[id]?.comment !== value.comment) {
            copy[id] = value;
            changed = true;
        }
    }
    return changed ? copy : prev;
}

export function useCockpitLogic({
    data,
    interactive,
    layout,
    chatScrollRef,
}: {
    data: Data;
    interactive: Interactive;
    layout: Layout;
    chatScrollRef: React.RefObject<HTMLDivElement>;
}) {
    const { sessionId, resetSession } = useSession();
    const { pushToast } = useToast();
    const { connected: telemetryConnected, entries: telemetryEntries } =
        useTelemetryFeed();

    // Queue Mutations State
    const [queueAction, setQueueAction] = useState<string | null>(null);
    const [queueActionMessage, setQueueActionMessage] = useState<string | null>(null);

    const handleExecuteQueueMutation = async (action: "purge" | "emergency") => {
        if (queueAction) return;
        setQueueAction(action);
        setQueueActionMessage(null);
        try {
            if (action === "purge") {
                await purgeQueue();
                setQueueActionMessage("Kolejka została wyczyszczona.");
            } else {
                const res = await emergencyStop();
                setQueueActionMessage(
                    `Zatrzymano zadania: cancelled ${res.cancelled}, purged ${res.purged}.`
                );
            }
            data.refresh.queue();
            data.refresh.tasks();
        } catch (err) {
            setQueueActionMessage(
                err instanceof Error ? err.message : "Błąd podczas operacji na kolejce."
            );
        } finally {
            setQueueAction(null);
        }
    };

    const handleToggleQueue = async () => {
        if (queueAction) return;
        const isPaused = data.queue?.paused ?? false;
        const action = isPaused ? "resume" : "pause";
        setQueueAction(action);
        setQueueActionMessage(null);
        try {
            await toggleQueue(isPaused);
            setQueueActionMessage(isPaused ? "Wznowiono kolejkę." : "Wstrzymano kolejkę.");
            data.refresh.queue();
        } catch (err) {
            setQueueActionMessage(
                err instanceof Error ? err.message : "Błąd sterowania kolejką."
            );
        } finally {
            setQueueAction(null);
        }
    };

    // Session Actions
    const sessionActions = useCockpitSessionActions({
        sessionId,
        resetSession,
        clearSessionMemory,
        clearGlobalMemory,
        setMessage: interactive.setters.setMessage,
        setMemoryAction: interactive.setters.setMemoryAction,
        pushToast,
    });

    // Session History State (merged)
    const {
        data: sessionHistoryData,
        refresh: refreshSessionHistory,
    } = useSessionHistory(sessionId, 0);
    const refreshHistory = data.refresh.history;
    const refreshSessionHistoryVoid = useCallback(() => {
        void refreshSessionHistory();
    }, [refreshSessionHistory]);
    const refreshHistoryVoid = useCallback(() => {
        void refreshHistory();
    }, [refreshHistory]);

    const {
        sessionHistory,
        localSessionHistory,
        setLocalSessionHistory,
        sessionEntryKey,
    } = useSessionHistoryState({
        sessionId,
        sessionHistoryData,
        refreshSessionHistory: refreshSessionHistoryVoid,
        refreshHistory: refreshHistoryVoid,
    });

    const pendingResetSessionRef = useRef<string | null>(null);
    const resetAtRef = useRef<string | null>(null);
    const resetKey = sessionId ? `venom-session-reset-at:${sessionId}` : null;

    useEffect(() => {
        if (!resetKey) return;
        try {
            const stored = globalThis.window.sessionStorage.getItem(resetKey);
            resetAtRef.current = stored || null;
        } catch {
            resetAtRef.current = null;
        }
    }, [resetKey]);

    useEffect(() => {
        if (typeof globalThis.window === "undefined") return;
        const handleReset = (evt: Event) => {
            const detail = (evt as CustomEvent<{ sessionId?: string | null }>).detail;
            pendingResetSessionRef.current = detail?.sessionId ?? null;
            const resetAt = new Date().toISOString();
            resetAtRef.current = resetAt;
            if (detail?.sessionId) {
                try {
                    globalThis.window.sessionStorage.setItem(
                        `venom-session-reset-at:${detail.sessionId}`,
                        resetAt,
                    );
                } catch {
                    // ignore storage errors
                }
            }
            setLocalSessionHistory([]);
            if (interactive?.optimistic?.resetOptimisticState) {
                interactive.optimistic.resetOptimisticState();
            }
            interactive.setters.setSelectedRequestId(null);
            interactive.setters.setSelectedTask(null);
            interactive.setters.setHistoryDetail(null);
            interactive.setters.setHistoryError(null);
            hydratedRefs.current.clear();
            try {
                if (globalThis.window?.sessionStorage) {
                    const keys = Object.keys(globalThis.window.sessionStorage);
                    keys.forEach((key) => {
                        if (key.startsWith("venom-session-history:")) {
                            globalThis.window.sessionStorage.removeItem(key);
                        }
                    });
                }
            } catch {
                // ignore storage errors
            }
        };
        globalThis.window.addEventListener("venom-session-reset", handleReset);
        return () => globalThis.window.removeEventListener("venom-session-reset", handleReset);
    }, [interactive.optimistic, interactive.setters, setLocalSessionHistory]);

    // Hidden Prompts
    const [hiddenIntentFilter, setHiddenIntentFilter] = useState("all");
    const [hiddenScoreFilter, setHiddenScoreFilter] = useState(1);
    const hiddenIntentParam =
        hiddenIntentFilter === "all" ? undefined : hiddenIntentFilter;

    const {
        data: hiddenPrompts,
        refresh: refreshHiddenPrompts,
    } = useHiddenPrompts(6, 20000, hiddenIntentParam, hiddenScoreFilter);

    const {
        data: activeHiddenPrompts,
        refresh: refreshActiveHiddenPrompts,
    } = useActiveHiddenPrompts(hiddenIntentParam, 20000);

    const hiddenState = useHiddenPromptState({
        hiddenPrompts,
        activeHiddenPrompts,
        hiddenIntentFilter,
    });

    // Tracking & Streams
    const historyForTracking = useMemo(() => {
        if (!data.history) return data.history;
        if (!sessionId) return [];
        return data.history.filter((entry) => entry.session_id === sessionId);
    }, [data.history, sessionId]);
    const trackedRequestIds = useTrackedRequestIds({
        optimisticRequests: interactive.optimistic.optimisticRequests,
        history: historyForTracking,
        selectedRequestId: interactive.state.selectedRequestId,
    });

    const { streams: taskStreams } = useTaskStream(trackedRequestIds, {
        enabled: trackedRequestIds.length > 0,
        throttleMs: 250,
        onEvent: (event) => {
            if (!event.taskId || !event.result) return;
            const timing = interactive.optimistic.uiTimingsRef.current.get(
                event.taskId
            );
            if (!timing || timing.ttftMs !== undefined) return;
            const ttftMs = Date.now() - timing.t0;
            interactive.optimistic.recordUiTiming(event.taskId, { ttftMs });
            console.info(`[TTFT] ${event.taskId}: ${ttftMs}ms`);
        },
    });

    // Refresh Loop based on Streams
    const hadActiveStreamsRef = useRef(false);
    useEffect(() => {
        const activeStreams = Object.values(taskStreams) as { status: string }[];
        const hasActive = activeStreams.some(
            (s) => s.status === "PROCESSING" || s.status === "PENDING"
        );
        const shouldRefreshOnFinish =
            hadActiveStreamsRef.current && !hasActive && activeStreams.length > 0;
        hadActiveStreamsRef.current = hasActive;

        if (shouldRefreshOnFinish) {
            data.refresh.history();
            data.refresh.tasks();
            refreshSessionHistory();
            data.refresh.metrics();
            data.refresh.tokenMetrics();
            data.refresh.modelsUsage();
            data.refresh.services();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [taskStreams, interactive.optimistic.optimisticRequests]);

    // Hydration for completed tasks with missing content (perf tests etc)
    const hydratedRefs = useRef<Set<string>>(new Set());
    useEffect(() => {
        if (!data.history) return;
        if (!sessionId) return;
        data.history.forEach((task) => {
            const normalized = task as HistoryTaskLike;
            if (
                !shouldHydrateCompletedTask(
                    normalized,
                    sessionId,
                    hydratedRefs.current,
                    localSessionHistory,
                    taskStreams as Record<string, StreamLike>,
                )
            ) {
                return;
            }
            const requestId = normalized.request_id;
            hydratedRefs.current.add(requestId);
            void hydrateCompletedTask({
                requestId,
                sessionId,
                setLocalSessionHistory,
            });
        });
    }, [data.history, localSessionHistory, taskStreams, setLocalSessionHistory, sessionId]);

    // Sync feedback from history to local state
    useEffect(() => {
        const updates = extractFeedbackUpdates(
            data.history,
            interactive.state.historyDetail as { request_id?: string; feedback?: { rating?: string; comment?: string | null } | null } | null,
        );
        if (Object.keys(updates).length > 0) {
            interactive.setters.setFeedbackByRequest((prev) => mergeFeedbackUpdates(prev, updates));
        }
    }, [data.history, interactive.state.historyDetail, interactive.setters]);

    // Sync active server/model if selection is empty
    useEffect(() => {
        // Sync Server
        if (!interactive.state.selectedLlmServer && data.activeServerInfo?.active_server) {
            interactive.setters.setSelectedLlmServer(data.activeServerInfo.active_server);
        }
        // Sync Model
        if (!interactive.state.selectedLlmModel && data.activeServerInfo?.active_model) {
            interactive.setters.setSelectedLlmModel(data.activeServerInfo.active_model);
        }
    }, [
        data.activeServerInfo,
        interactive.state.selectedLlmServer,
        interactive.state.selectedLlmModel,
        interactive.setters
    ]);

    // Chat UI Interface
    const { language } = useLanguage();

    const historyMessages = useMemo(() => {
        if (pendingResetSessionRef.current) {
            if (sessionId && pendingResetSessionRef.current === sessionId) {
                pendingResetSessionRef.current = null;
            } else {
                return [];
            }
        }
        if (!sessionId) {
            return [];
        }
        let deduped = mergeHistoryFallbacks({
            sessionHistory,
            localSessionHistory,
            historyRequests: data.history,
            tasks: data.tasks,
            sessionId,
            sessionEntryKey,
        });

        mergeStreamsIntoHistory(deduped as HistoryEntryLike[], taskStreams as Record<string, StreamLike>);

        deduped = filterHistoryAfterReset(deduped, resetAtRef.current);
        const ordered = orderHistoryEntriesByRequestId(deduped);

        return toHistoryMessages(ordered as HistoryEntryLike[]);

    }, [localSessionHistory, sessionHistory, taskStreams, sessionEntryKey, data.history, data.tasks, sessionId]);

    const chatUi = useCockpitChatUi({
        chatMessages: historyMessages, // Use computed
        chatScrollRef,
        // ... Pass ALL interactive state setters ...
        feedbackByRequest: interactive.state.feedbackByRequest,
        setFeedbackByRequest: interactive.setters.setFeedbackByRequest,
        setFeedbackSubmittingId: interactive.setters.setFeedbackSubmittingId,
        sendFeedback,
        refreshHistory: data.refresh.history,
        refreshTasks: data.refresh.tasks,
        responseDurations: interactive.state.responseDurations,
        lastResponseDurationMs: interactive.state.lastResponseDurationMs,
        labMode: layout.labMode,
        chatMode: interactive.state.chatMode,
        generationParams: interactive.state.generationParams,
        selectedLlmModel: interactive.state.selectedLlmModel,
        activeServerInfo: data.activeServerInfo,
        sessionId: sessionId,
        language: language ?? "pl",
        resetSession,
        refreshActiveServer: () => {
            void data.refresh.activeServer();
        },
        setActiveLlmRuntime: setActiveLlmRuntime,
        sendSimpleChatStream,
        sendTask: sendTask, // No cast
        ingestMemoryEntry,
        refreshQueue: data.refresh.queue,
        refreshSessionHistory,
        enqueueOptimisticRequest: interactive.optimistic.enqueueOptimisticRequest,
        linkOptimisticRequest: interactive.optimistic.linkOptimisticRequest,
        dropOptimisticRequest: interactive.optimistic.dropOptimisticRequest,
        updateSimpleStream: interactive.optimistic.updateSimpleStream,
        recordUiTiming: interactive.optimistic.recordUiTiming,
        uiTimingsRef: interactive.optimistic.uiTimingsRef,
        clearSimpleStream: interactive.optimistic.clearSimpleStream,
        setLocalSessionHistory,
        setSimpleRequestDetails: interactive.optimistic.setSimpleRequestDetails,
        setMessage: interactive.setters.setMessage,
        setSending: interactive.setters.setSending,
        setLastResponseDurationMs: interactive.setters.setLastResponseDurationMs,
        setResponseDurations: interactive.setters.setResponseDurations,
        models: data.models,
        fetchModelConfig: fetchModelConfig,
        updateModelConfig,
        setTuningOpen: layout.setTuningOpen, // Layout state!
        setLoadingSchema: interactive.setters.setLoadingSchema,
        setModelSchema: interactive.setters.setModelSchema,
        setGenerationParams: interactive.setters.setGenerationParams,
        setTuningSaving: interactive.setters.setTuningSaving,
        pushToast,
        pinnedLogs: interactive.state.pinnedLogs,
        setExportingPinned: layout.setExportingPinned, // Layout state!
    });

    const macros = useCockpitMacros(chatUi.handleSend);
    const metricsDisplay = useCockpitMetricsDisplay(data);

    // Request Detail Actions
    const requestDetail = useCockpitRequestDetailActions({
        findTaskMatch: data.findTaskMatch,
        simpleRequestDetails: interactive.optimistic.simpleRequestDetails,
        fetchHistoryDetail,
        fetchTaskDetail,
        setSelectedRequestId: interactive.setters.setSelectedRequestId,
        setDetailOpen: layout.setDetailOpen,
        setHistoryDetail: interactive.setters.setHistoryDetail,
        setHistoryError: interactive.setters.setHistoryError,
        setCopyStepsMessage: interactive.setters.setCopyStepsMessage,
        setSelectedTask: interactive.setters.setSelectedTask,
        setLoadingHistory: interactive.setters.setLoadingHistory,
        historyDetail: interactive.state.historyDetail,
    });

    const contextPreviewMeta = useMemo(() => {
        return parseContextPreviewMeta(
            interactive.state.selectedTask as { context_history?: Record<string, unknown> } | null,
            interactive.state.historyDetail as {
                steps?: Array<{ component?: string; action?: string; details?: string | null }>;
            } | null,
        );
    }, [interactive.state.selectedTask, interactive.state.historyDetail]);

    const handleSetActiveHiddenPrompt = useCallback(async (payload: Parameters<typeof setActiveHiddenPrompt>[0]) => {
        try {
            await setActiveHiddenPrompt(payload);
            refreshActiveHiddenPrompts();
        } catch (e) {
            console.error("Failed to set active hidden prompt:", e);
        }
    }, [refreshActiveHiddenPrompts]);

    const handleActivateModel = async (model: string) => {
        interactive.setters.setSelectedLlmModel(model);

        let provider = interactive.state.selectedLlmServer || data.activeServerInfo?.active_server;
        const modelDef = data.models?.models?.find(m => m.name === model);
        if (modelDef?.provider) {
            provider = modelDef.provider;
        }

        if (provider) {
            try {
                if (provider === "openai" || provider === "google") {
                    // Cloud providers use /system/llm-runtime/active
                    await setActiveLlmRuntime(provider, model);
                } else {
                    // Local providers (ollama, vllm)
                    // 1. If provider changed, switch server first
                    if (provider !== data.activeServerInfo?.active_server) {
                        await setActiveLlmServer(provider);
                    }
                    // 2. Activate specific model via /models/switch
                    await switchModel(model);
                }

                pushToast(`Aktywowano model: ${model}`, "success");
                data.refresh.activeServer();
            } catch (err) {
                pushToast(`Błąd aktywacji modelu: ${(err as Error).message}`, "error");
            }
        } else {
            pushToast("Nie można ustalić serwera dla wybranego modelu.", "warning");
        }
    };

    return {
        sessionId,
        resetSession,
        telemetry: { connected: telemetryConnected, entries: telemetryEntries },
        handleActivateModel, // Exposed
        sessionActions,
        sessionHistoryState: {
            sessionHistory,
            localSessionHistory,
            setLocalSessionHistory,
            sessionEntryKey,
            refreshSessionHistory, // Exposed
        },
        hiddenState: {
            ...hiddenState,
            filter: hiddenIntentFilter,
            setFilter: setHiddenIntentFilter,
            score: hiddenScoreFilter,
            setScore: setHiddenScoreFilter,
            hiddenPrompts, // Exposed
            activeHiddenPrompts, // Exposed
            onSetActiveHiddenPrompt: handleSetActiveHiddenPrompt,
            refreshHiddenPrompts,
            refreshActiveHiddenPrompts,
        },
        historyMessages,
        chatUi,
        queue: {
            queueAction,
            queueActionMessage,
            onToggleQueue: handleToggleQueue,
            onExecuteQueueMutation: handleExecuteQueueMutation,
        },
        requestDetail: {
            ...requestDetail,
            contextPreviewMeta,
        },
        macros,
        metricsDisplay,
    };
}

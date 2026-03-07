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
    extractFeedbackUpdates,
    hydrateCompletedTask,
    mergeFeedbackUpdates,
    mergeStreamsIntoHistory,
    parseContextPreviewMeta,
    shouldHydrateCompletedTask,
    StreamLike,
    toHistoryMessages,
    HistoryEntryLike,
    HistoryTaskLike,
} from "./cockpit-history-utils";
import { useCockpitQueueActions } from "./use-cockpit-queue-actions";
import { useCockpitModelActivation } from "./use-cockpit-model-activation";
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
import { resolveCockpitRuntimeModelSelection } from "@/lib/cockpit-runtime-selection";
import { filterRuntimeBaseModels } from "@/lib/runtime-model-filters";

type Data = ReturnType<typeof useCockpitData>;
type Interactive = ReturnType<typeof useCockpitInteractiveState>;
type Layout = ReturnType<typeof useCockpitLayout>;

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
    const { language, t } = useLanguage();
    const { connected: telemetryConnected, entries: telemetryEntries } =
        useTelemetryFeed();
    const queueActions = useCockpitQueueActions({
        queuePaused: data.queue?.paused ?? false,
        refreshQueue: data.refresh.queue,
        refreshTasks: data.refresh.tasks,
        purgeQueueFn: purgeQueue,
        emergencyStopFn: emergencyStop,
        toggleQueueFn: toggleQueue,
        t,
    });

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
        Promise.resolve(refreshSessionHistory()).catch((error) => {
            console.error("Failed to refresh session history:", error);
        });
    }, [refreshSessionHistory]);
    const refreshHistoryVoid = useCallback(() => {
        Promise.resolve(refreshHistory()).catch((error) => {
            console.error("Failed to refresh history:", error);
        });
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
        if (globalThis.window === undefined) return;
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
            hydrateCompletedTask({
                requestId,
                sessionId,
                setLocalSessionHistory,
                fetchTaskDetailFn: fetchTaskDetail,
            }).catch((error) => {
                console.error("Failed to hydrate completed task:", error);
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

    // Sync active server from runtime state on initial load.
    useEffect(() => {
        if (!interactive.state.selectedLlmServer && data.activeServerInfo?.active_server) {
            interactive.setters.setSelectedLlmServer(data.activeServerInfo.active_server);
        }
    }, [
        data.activeServerInfo,
        interactive.state.selectedLlmServer,
        interactive.setters
    ]);

    useEffect(() => {
        const runtimeTargets = data.unifiedModelCatalog?.runtimes ?? [];
        const activeServer = (data.activeServerInfo?.active_server || "").trim();
        const effectiveServer = (interactive.state.selectedLlmServer || activeServer).trim();
        if (!effectiveServer) {
            if (interactive.state.selectedLlmModel) {
                interactive.setters.setSelectedLlmModel("");
            }
            return;
        }
        const runtime = runtimeTargets.find((item) => item.runtime_id === effectiveServer);
        const runtimeModels = filterRuntimeBaseModels(
            (runtime?.models ?? []).filter((model) => model.chat_compatible !== false),
        )
            .map((model) => model.name);
        if (runtimeModels.length === 0) {
            if (interactive.state.selectedLlmModel) {
                interactive.setters.setSelectedLlmModel("");
            }
            return;
        }
        const currentSelection = (interactive.state.selectedLlmModel || "").trim();
        const selectedModel = resolveCockpitRuntimeModelSelection(
            currentSelection,
            runtimeModels,
        );
        if (selectedModel === currentSelection) {
            return;
        }
        if (!currentSelection && effectiveServer === activeServer) {
            const activeModel = resolveCockpitRuntimeModelSelection(
                (data.activeServerInfo?.active_model || "").trim(),
                runtimeModels,
            );
            if (activeModel) {
                interactive.setters.setSelectedLlmModel(activeModel);
            }
            return;
        }
        interactive.setters.setSelectedLlmModel(selectedModel);
    }, [
        data.activeServerInfo?.active_model,
        data.activeServerInfo?.active_server,
        data.unifiedModelCatalog?.runtimes,
        interactive.state.selectedLlmModel,
        interactive.state.selectedLlmServer,
        interactive.setters,
    ]);

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

    const refreshActiveServerSafe = useCallback(() => {
        Promise.resolve(data.refresh.activeServer()).catch((error) => {
            console.error("Failed to refresh active server:", error);
        });
    }, [data.refresh]);

    const { handleActivateModel } = useCockpitModelActivation({
        selectedLlmServer: interactive.state.selectedLlmServer,
        selectedLlmModel: interactive.state.selectedLlmModel,
        activeServer: data.activeServerInfo?.active_server || "",
        setSelectedLlmModel: interactive.setters.setSelectedLlmModel,
        setActiveLlmRuntimeFn: setActiveLlmRuntime,
        setActiveLlmServerFn: setActiveLlmServer,
        refreshActiveServer: refreshActiveServerSafe,
        pushToast,
        t,
    });

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
        selectedLlmServer: interactive.state.selectedLlmServer,
        generationParams: interactive.state.generationParams,
        selectedLlmModel: interactive.state.selectedLlmModel,
        activeServerInfo: data.activeServerInfo,
        sessionId: sessionId,
        language: language ?? "pl",
        resetSession,
        refreshActiveServer: refreshActiveServerSafe,
        setActiveLlmRuntime: setActiveLlmRuntime,
        setActiveLlmServer: setActiveLlmServer,
        ensureModelActive: handleActivateModel,
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
            queueAction: queueActions.queueAction,
            queueActionMessage: queueActions.queueActionMessage,
            onToggleQueue: queueActions.handleToggleQueue,
            onExecuteQueueMutation: queueActions.handleExecuteQueueMutation,
        },
        requestDetail: {
            ...requestDetail,
            contextPreviewMeta,
        },
        macros,
        metricsDisplay,
    };
}

"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { ApiError } from "@/lib/api-client";
import { rememberChatSession } from "@/lib/chat-sessions";
import { useSession } from "@/lib/session";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
import { orderHistoryEntriesByRequestId } from "@/components/cockpit/hooks/history-order";
import { useSessionHistoryState, useTrackedRequestIds } from "@/components/cockpit/cockpit-hooks";
import { useTaskStream } from "@/hooks/use-task-stream";
import { useCockpitSessionActions } from "@/components/cockpit/cockpit-session-actions";
import { useCockpitChatUi } from "@/components/cockpit/cockpit-chat-ui";
import { extractFeedbackUpdates, hydrateCompletedTask, mergeFeedbackUpdates, mergeStreamsIntoHistory, shouldHydrateCompletedTask, toHistoryMessages, type HistoryTaskLike } from "@/components/cockpit/hooks/cockpit-history-utils";
import { useCockpitModelActivation } from "@/components/cockpit/hooks/use-cockpit-model-activation";
import { clearSessionMemory, clearGlobalMemory, fetchModelConfig, updateModelConfig, sendSimpleChatStream, sendTask, ingestMemoryEntry, sendFeedback, fetchTaskDetail, setActiveLlmRuntime, setActiveLlmServer, useSessionHistory } from "@/hooks/use-api";
import { filterHistoryAfterReset, mergeHistoryFallbacks } from "@/components/cockpit/hooks/history-merge";
import type { useCockpitData } from "@/components/cockpit/hooks/use-cockpit-data";
import type { useCockpitInteractiveState } from "@/components/cockpit/hooks/use-cockpit-interactive-state";
import type { useCockpitLayout } from "@/components/cockpit/hooks/use-cockpit-layout";
import { normalizeRuntimeId, resolveCockpitRuntimeModelSelection, resolveCockpitEmptyRuntimeModelUpdate } from "@/lib/cockpit-runtime-selection";
import { filterRuntimeBaseModels } from "@/lib/runtime-model-filters";

const taskUuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

type CockpitData = ReturnType<typeof useCockpitData>;
export type ConversationData = Pick<CockpitData, "history" | "tasks" | "activeServerInfo" | "unifiedModelCatalog" | "models"> & {
  refresh: Pick<CockpitData["refresh"], "history" | "tasks" | "queue" | "activeServer">;
};
export type ConversationInteraction = ReturnType<typeof useCockpitInteractiveState>;
type ConversationLayout = Pick<ReturnType<typeof useCockpitLayout>, "labMode" | "setTuningOpen" | "setExportingPinned">;

/** One owner of conversation/history/stream per mounted route, without system telemetry. */
export function useConversationController({ data, interactive, layout, chatScrollRef, onTurnFinished, materialIds }: {
  materialIds?: string[];
  data: ConversationData;
  interactive: ConversationInteraction;
  layout: ConversationLayout;
  chatScrollRef: React.RefObject<HTMLDivElement>;
  onTurnFinished?: () => void;
}) {
    const { sessionId, resetSession, bootId } = useSession();
    const { pushToast } = useToast();
    const { language, t } = useLanguage();
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
        backendBootId: bootId,
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

        };
        globalThis.window.addEventListener("venom-session-reset", handleReset);
        return () => globalThis.window.removeEventListener("venom-session-reset", handleReset);
    }, [interactive.optimistic, interactive.setters, setLocalSessionHistory]);

    // Tracking & Streams
    const historyForTracking = useMemo(() => {
        if (!data.history) return data.history;
        if (!sessionId) return [];
        return data.history.filter((entry) => entry.session_id === sessionId);
    }, [data.history, sessionId]);
    const trackedLiveRequestIds = useTrackedRequestIds({
        optimisticRequests: interactive.optimistic.optimisticRequests,
        history: historyForTracking,
        selectedRequestId: interactive.state.selectedRequestId,
    });

    const ownedSessionTaskIds = useMemo(() => new Set([
        ...localSessionHistory, ...sessionHistory, ...(historyForTracking ?? []),
    ].filter(entry => !entry.session_id || entry.session_id === sessionId).map(entry => entry.request_id).filter((id): id is string => !!id)),
    [localSessionHistory, sessionHistory, historyForTracking, sessionId]);

    const restoredPending = useMemo(() => {
      const live = new Set(interactive.optimistic.optimisticRequests.flatMap(request => [request.requestId, request.clientId]));
      const settled = new Set(sessionHistory.filter(entry => entry.role === "assistant" && !entry.pending && ["COMPLETED", "FAILED", "CANCELLED", "LOST"].includes(entry.status ?? "")).map(entry => entry.request_id));
      return [...new Set(localSessionHistory.filter(entry => entry.role === "assistant" && entry.request_id
        && (entry.pending || ["PENDING", "PROCESSING"].includes(entry.status ?? "")) && !live.has(entry.request_id) && !settled.has(entry.request_id))
        .map(entry => entry.request_id!))];
    }, [localSessionHistory, sessionHistory, interactive.optimistic.optimisticRequests]);
    const restoredKey = JSON.stringify(restoredPending);
    const trackedRequestIds = useMemo(() => [...new Set([...trackedLiveRequestIds, ...restoredPending.filter(id => taskUuid.test(id))])].filter(id => ownedSessionTaskIds.has(id)), [trackedLiveRequestIds, restoredPending, ownedSessionTaskIds]);
    useEffect(() => {
      const request = new AbortController();
      const finishRestored = (id: string, status: string, content?: string | null) => {
        if (request.signal.aborted) return;
        setLocalSessionHistory(previous => previous.map(entry => entry.request_id === id && (entry.pending || ["PENDING", "PROCESSING"].includes(entry.status ?? ""))
          ? { ...entry, pending: false, status, ...(entry.role === "assistant" && content ? { content } : {}) } : entry));
      };
      for (const id of JSON.parse(restoredKey) as string[]) {
        if (!taskUuid.test(id)) { finishRestored(id, "CANCELLED"); continue; }
        void fetchTaskDetail(id, request.signal).then(task => {
          if (["COMPLETED", "FAILED", "LOST"].includes(task.status)) finishRestored(id, task.status, task.result);
        }).catch(error => { if (error instanceof ApiError && [404, 422].includes(error.status)) finishRestored(id, "LOST"); });
      }
      return () => request.abort();
    }, [restoredKey, setLocalSessionHistory]);

    const { streams: unscopedTaskStreams } = useTaskStream(trackedRequestIds, {
        enabled: trackedRequestIds.length > 0,
        throttleMs: 250,
        onEvent: (event) => {
            if (!ownedSessionTaskIds.has(event.taskId)) return;
            if (event.taskId && event.status) {
                setLocalSessionHistory(previous => {
                    const next = [...previous];
                    mergeStreamsIntoHistory(next, { [event.taskId]: event });
                    return next.length !== previous.length || next.some((entry, index) => entry !== previous[index]) ? next : previous;
                });
            }
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

    const taskStreams = useMemo(() => Object.fromEntries(Object.entries(unscopedTaskStreams)
        .filter(([id]) => ownedSessionTaskIds.has(id))), [unscopedTaskStreams, ownedSessionTaskIds]);

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
            void data.refresh.history();
            void data.refresh.tasks();
            void refreshSessionHistory();
            onTurnFinished?.();
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
                    taskStreams,
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
        const activeServer = normalizeRuntimeId(
            data.activeServerInfo?.active_server ||
                data.unifiedModelCatalog?.active?.active_server ||
                "",
        );
        if (!interactive.state.selectedLlmServer && activeServer) {
            interactive.setters.setSelectedLlmServer(activeServer);
        }
    }, [
        data.activeServerInfo,
        data.unifiedModelCatalog?.active?.active_server,
        interactive.state.selectedLlmServer,
        interactive.setters
    ]);

    useEffect(() => {
        const runtimeTargets = data.unifiedModelCatalog?.runtimes ?? [];
        const activeServer = normalizeRuntimeId(
            data.activeServerInfo?.active_server ||
                data.unifiedModelCatalog?.active?.active_server ||
                "",
        );
        const activeModelFromRuntime = (
            data.activeServerInfo?.active_model ||
            data.unifiedModelCatalog?.active?.active_model ||
            ""
        ).trim();
        const effectiveServer = normalizeRuntimeId(
            interactive.state.selectedLlmServer || activeServer,
        );
        if (!effectiveServer) {
            if (interactive.state.selectedLlmModel) {
                interactive.setters.setSelectedLlmModel("");
            }
            return;
        }
        const runtime = runtimeTargets.find(
            (item) => normalizeRuntimeId(item.runtime_id) === effectiveServer,
        );
        const runtimeModels = filterRuntimeBaseModels(
            (runtime?.models ?? []).filter((model) => model.chat_compatible !== false),
        )
            .map((model) => model.name);
        const currentSelection = (interactive.state.selectedLlmModel || "").trim();
        if (runtimeModels.length === 0) {
            const modelUpdate = resolveCockpitEmptyRuntimeModelUpdate(
                effectiveServer,
                activeModelFromRuntime,
                interactive.state.selectedLlmModel || "",
            );
            if (modelUpdate !== null) {
                interactive.setters.setSelectedLlmModel(modelUpdate);
            }
            return;
        }
        const selectedModel = resolveCockpitRuntimeModelSelection(
            currentSelection,
            runtimeModels,
        );
        if (selectedModel === currentSelection) {
            return;
        }
        if (!currentSelection) {
            return;
        }
        interactive.setters.setSelectedLlmModel(selectedModel);
    }, [
        data.activeServerInfo?.active_model,
        data.activeServerInfo?.active_server,
        data.unifiedModelCatalog?.active?.active_model,
        data.unifiedModelCatalog?.active?.active_server,
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

        mergeStreamsIntoHistory(deduped, taskStreams);

        deduped = filterHistoryAfterReset(deduped, resetAtRef.current);
        const ordered = orderHistoryEntriesByRequestId(deduped);

        return toHistoryMessages(ordered);

    }, [localSessionHistory, sessionHistory, taskStreams, sessionEntryKey, data.history, data.tasks, sessionId]);

    const sessionTitle = historyMessages.find(message => message.role === "user")?.text;
    useEffect(() => { rememberChatSession(sessionId, sessionTitle); }, [sessionId, sessionTitle]);

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

    const conversationHistory = useMemo(() => historyMessages
      .filter(message => !message.pending && message.text && !["FAILED", "CANCELLED", "LOST"].includes(message.status ?? "")).map(message => ({ role: message.role, content: message.text,
        ...(message.materialIds?.length ? { material_ids: message.materialIds } : {}) })), [historyMessages]);
    const chatUi = useCockpitChatUi({
        materialIds,
        conversationHistory,
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

    return {
      sessionId, resetSession, handleActivateModel, sessionActions, historyMessages, chatUi,
      normalRequestIds: trackedRequestIds,
      sessionHistoryState: { sessionHistory, localSessionHistory, setLocalSessionHistory, sessionEntryKey, refreshSessionHistory },
    };
}

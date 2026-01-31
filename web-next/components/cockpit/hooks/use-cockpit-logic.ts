"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSession } from "@/lib/session";
import { useToast } from "@/components/ui/toast";
import { useLanguage } from "@/lib/i18n";
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

import { type SessionHistoryEntry } from "@/components/cockpit/cockpit-hooks";

import { useCockpitData } from "./use-cockpit-data";
import { useCockpitInteractiveState } from "./use-cockpit-interactive-state";
import { useCockpitLayout } from "./use-cockpit-layout";
import { useCockpitMacros } from "./use-cockpit-macros";
import { useCockpitMetricsDisplay } from "./use-cockpit-metrics-display";

type Data = ReturnType<typeof useCockpitData>;
type Interactive = ReturnType<typeof useCockpitInteractiveState>;
type Layout = ReturnType<typeof useCockpitLayout>;


export function useCockpitLogic(
    data: Data,
    interactive: Interactive,
    layout: Layout,
    chatScrollRef: React.RefObject<HTMLDivElement>
) {
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

    const {
        sessionHistory,
        localSessionHistory,
        setLocalSessionHistory,
        sessionEntryKey,
    } = useSessionHistoryState({
        sessionId,
        sessionHistoryData,
        refreshSessionHistory,
        refreshHistory: data.refresh.history,
    });

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
    const trackedRequestIds = useTrackedRequestIds({
        optimisticRequests: interactive.optimistic.optimisticRequests,
        history: data.history,
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
    useEffect(() => {
        let shouldRefresh = false;

        const activeStreams = Object.values(taskStreams) as { status: string }[];
        const hasActive = activeStreams.some(
            (s) => s.status === "processing" || s.status === "pending"
        );
        if (!hasActive && activeStreams.length > 0) {
            // Just finished?
            // Simplified check: if any stream is done or we have optimistic requests that might have completed
            shouldRefresh = true;
        }

        // Telemetry check (simplified from original)
        if (shouldRefresh) {
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

        // Find tasks that are COMPLETED in history but don't have a corresponding message in session history
        // or the message is empty.
        const completedTasks = data.history.filter(h => h.status === 'COMPLETED');

        completedTasks.forEach(task => {
            // Only hydrate tasks belonging to the current session context!
            if (task.session_id !== sessionId) return;

            if (hydratedRefs.current.has(task.request_id)) return;

            // Check if we have an assistant message for this task
            const stringKeyId = task.request_id;
            const hasMessage = localSessionHistory.some(
                msg => msg.request_id === stringKeyId && msg.role === 'assistant' && msg.content
            );

            if (!hasMessage) {
                // Double check streams - maybe it's there?
                const stream = taskStreams[stringKeyId];
                if (stream && stream.result) return; // It's in stream, will be merged

                // It is NOT in history, and NOT in stream. Hydrate it.
                hydratedRefs.current.add(stringKeyId);
                fetchTaskDetail(stringKeyId).then(taskDetail => {
                    if (taskDetail.result) {
                        setLocalSessionHistory(prev => {
                            // Double check existence to avoid dups
                            if (prev.some(p => p.request_id === stringKeyId && p.role === 'assistant')) return prev;

                            return [...prev, {
                                role: 'assistant',
                                content: taskDetail.result || "",
                                request_id: stringKeyId,
                                timestamp: taskDetail.created_at || new Date().toISOString()
                            }].sort((a, b) => new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime());
                        });
                    }
                }).catch(err => {
                    // Ignore 404s (task not found/deleted) to prevent console spam
                    if (err?.status !== 404 && !err?.message?.includes("404")) {
                        console.error("Failed to hydrate task", stringKeyId, err);
                    }
                });
            }
        });
    }, [data.history, localSessionHistory, taskStreams, setLocalSessionHistory, sessionId]);

    // Sync feedback from history to local state
    useEffect(() => {
        interface FeedbackValue { rating?: "up" | "down" | null; comment?: string }
        const updates: Record<string, FeedbackValue> = {};

        // 1. From history list
        if (data.history) {
            data.history.forEach((item) => {
                if (item.feedback && item.request_id) {
                    updates[item.request_id] = {
                        rating: item.feedback.rating as "up" | "down",
                        comment: item.feedback.comment ?? undefined
                    };
                }
            });
        }

        // 2. From detailed history
        const detail = interactive.state.historyDetail;
        if (detail && detail.feedback && detail.request_id) {
            updates[detail.request_id] = {
                rating: detail.feedback.rating as "up" | "down",
                comment: detail.feedback.comment ?? undefined
            };
        }

        if (Object.keys(updates).length > 0) {
            // Only update if something changed to avoid re-renders
            interactive.setters.setFeedbackByRequest(prev => {
                const copy = { ...prev };
                let changed = false;
                for (const [id, val] of Object.entries(updates)) {
                    if (prev[id]?.rating !== val.rating || prev[id]?.comment !== val.comment) {
                        copy[id] = val;
                        changed = true;
                    }
                }
                return changed ? copy : prev;
            });
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
        const resolvedHistory =
            localSessionHistory.length > 0 ? localSessionHistory : sessionHistory;
        let deduped: SessionHistoryEntry[] = [];

        if (resolvedHistory.length > 0) {
            const seenMap = new Map<string, SessionHistoryEntry>();
            resolvedHistory.forEach((entry) => {
                const key = sessionEntryKey(entry);
                const existing = seenMap.get(key);
                if (!existing) {
                    seenMap.set(key, entry);
                } else if (entry.timestamp && existing.timestamp) {
                    // Dedup logic simplified
                    if (new Date(entry.timestamp) > new Date(existing.timestamp)) {
                        seenMap.set(key, entry);
                    }
                } else if (entry.timestamp && !existing.timestamp) {
                    seenMap.set(key, entry);
                }
            });
            deduped = Array.from(seenMap.values());
        }

        // Merge streams
        Object.entries(taskStreams).forEach(([taskId, stream]) => {
            // TaskStreamState has: result, status, logs...
            const content = stream.result || "";
            const isPending = stream.status === "PROCESSING" || stream.status === "PENDING";

            // Check if this taskId is already in history (as assistant)
            const index = deduped.findIndex(entry => entry.request_id === taskId && entry.role === 'assistant');

            if (index !== -1) {
                // Update existing entry if stream has more data or is active
                if (content && content.length > (deduped[index].content?.length || 0)) {
                    deduped[index] = {
                        ...deduped[index],
                        content: content,
                        pending: isPending,
                        status: stream.status,
                        contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
                    };
                } else if (isPending && !deduped[index].pending) {
                    // Revival of pending state if needed
                    deduped[index] = {
                        ...deduped[index],
                        pending: true,
                        status: stream.status,
                        contextUsed: stream.contextUsed ?? deduped[index].contextUsed,
                    };
                }
            } else if (content || isPending) {
                deduped.push({
                    role: 'assistant',
                    content: content,
                    request_id: taskId,
                    timestamp: new Date().toISOString(), // pending
                    pending: isPending,
                    status: stream.status,
                    contextUsed: stream.contextUsed ?? undefined,
                });
            }
        });

        // Ensure sorting by timestamp
        deduped.sort((a, b) => new Date(a.timestamp || 0).getTime() - new Date(b.timestamp || 0).getTime());

        return deduped.map((entry, index) => {
            const fallbackId = `msg-${index}-${entry.timestamp}`;
            const uniqueId = entry.request_id
                ? `${entry.request_id}-${entry.role}`
                : fallbackId;

            return {
                bubbleId: uniqueId,
                role: entry.role === "assistant" ? "assistant" : "user",
                text: entry.content || "",
                requestId: entry.request_id,
                timestamp: entry.timestamp,
                pending: entry.pending || false,
                status: entry.status || null,
                contextUsed: entry.contextUsed ?? null,
            };
        });

    }, [localSessionHistory, sessionHistory, taskStreams, sessionEntryKey]);

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
        refreshActiveServer: data.refresh.activeServer,
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
        const task = interactive.state.selectedTask;
        const detail = interactive.state.historyDetail;

        // 1. Try task context_history (Primary)
        if (task?.context_history) {
            const ctx = task.context_history;
            const preview = typeof ctx.preview === 'string' ? ctx.preview : (typeof ctx.prompt_context_preview === 'string' ? ctx.prompt_context_preview : null);

            // Only use task context if we actually found a preview string
            if (preview) {
                return {
                    preview,
                    truncated: !!ctx.truncated || !!ctx.prompt_context_truncated,
                    hiddenPrompts: typeof ctx.hidden_prompts_count === 'number' ? ctx.hidden_prompts_count : null,
                    mode: typeof ctx.mode === 'string' ? ctx.mode : null
                };
            }
        }

        // 2. Fallback: Parse historyDetail steps
        if (detail?.steps) {
            // Priority 1: Context preview steps
            const contextStep = detail.steps.find(s =>
                s.component === "ContextBuilder" ||
                s.action === "context_preview" ||
                (s.details && (s.details.includes("preview=") || s.details.includes("preview\"") || s.details.includes("prompt_context_preview")))
            );

            // Priority 2: Hidden prompts count
            const hiddenStep = detail.steps.find(s =>
                s.action === "hidden_prompts" ||
                (s.details && (s.details.includes("hidden_prompts") || s.details.includes("hiddenPrompts")))
            );

            interface ContextPreviewMeta {
                preview: string | null;
                truncated: boolean;
                hiddenPrompts: number | null;
                mode: string | null;
            }
            let meta: ContextPreviewMeta | null = null;

            if (contextStep?.details) {
                const details = contextStep.details.trim();
                // Try to parse JSON first
                if (details.startsWith("{")) {
                    try {
                        const parsed = JSON.parse(details);
                        meta = {
                            preview: parsed.preview || parsed.context || parsed.prompt || parsed.prompt_context_preview || null,
                            truncated: !!parsed.truncated || !!parsed.prompt_context_truncated,
                            hiddenPrompts: parsed.hidden_prompts_count ?? null,
                            mode: parsed.mode ?? null
                        };
                    } catch { }
                }

                if (!meta) {
                    // Try regex parsing for key=value format
                    const previewMatch = details.match(/(?:preview|prompt|context|prompt_context_preview)=([\s\S]*?)(?:$|\s\w+=)/);
                    const hiddenMatch = details.match(/hidden_prompts_count=(\d+)/);
                    const modeMatch = details.match(/mode=(\w+)/);

                    if (previewMatch || hiddenMatch) {
                        meta = {
                            preview: previewMatch ? previewMatch[1].trim() : null,
                            truncated: details.includes("truncated=true") || details.includes("truncated\":true"),
                            hiddenPrompts: hiddenMatch ? parseInt(hiddenMatch[1], 10) : null,
                            mode: modeMatch ? modeMatch[1] : null
                        };
                    }
                }
            }

            // If we found a contextStep but didn't get meta, or if we still need more info (e.g. hiddenPrompts from hiddenStep)
            if (!meta && !contextStep) {
                // Try fallback to LLM start step
                const llmStep = detail.steps.find(s =>
                    (s.component === "LLM" && s.action === "start") ||
                    (s.component === "ChatAgent" && s.action === "process_task") ||
                    (s.details && (s.details.includes("prompt=") || s.details.includes("payload=") || s.details.includes("input=")))
                );
                if (llmStep?.details) {
                    const details = llmStep.details.trim();
                    if (details.startsWith("{")) {
                        try {
                            const parsed = JSON.parse(details);
                            meta = {
                                preview: parsed.prompt || parsed.payload || parsed.input || null,
                                truncated: false,
                                hiddenPrompts: null,
                                mode: null
                            };
                        } catch { }
                    }
                    if (!meta) {
                        const promptMatch = details.match(/(?:prompt|payload|input)=([\s\S]*?)(?:$|\s\w+=)/);
                        if (promptMatch) {
                            meta = {
                                preview: promptMatch[1].trim(),
                                truncated: false,
                                hiddenPrompts: null,
                                mode: null
                            };
                        }
                    }
                }
            }

            // If we have meta but missing hiddenPrompts, try to get it from hiddenStep
            if (hiddenStep?.details) {
                const hiddenMatch = hiddenStep.details.match(/hidden_prompts:?\s*(\d+)/i) ||
                    hiddenStep.details.match(/hidden_prompts_count=(\d+)/);
                if (hiddenMatch) {
                    if (!meta) meta = { preview: null, truncated: false, mode: null, hiddenPrompts: null };
                    meta.hiddenPrompts = parseInt(hiddenMatch[1], 10);
                }
            }

            return meta;
        }
        return null;
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

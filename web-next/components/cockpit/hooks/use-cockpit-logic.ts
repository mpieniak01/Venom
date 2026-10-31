"use client";

import { useCallback, useMemo, useState } from "react";
import { useLanguage } from "@/lib/i18n";
import { useTelemetryFeed } from "@/hooks/use-telemetry";
import { useHiddenPromptState } from "@/components/cockpit/cockpit-hooks";
import { useCockpitQueueActions } from "./use-cockpit-queue-actions";
import { useCockpitRequestDetailActions } from "@/components/cockpit/cockpit-request-detail-actions";
import { useCockpitMacros } from "./use-cockpit-macros";
import { useCockpitMetricsDisplay } from "./use-cockpit-metrics-display";
import { parseContextPreviewMeta } from "./cockpit-history-utils";
import { useConversationController } from "@/components/chat/use-conversation-controller";
import type { useCockpitData } from "./use-cockpit-data";
import type { useCockpitInteractiveState } from "./use-cockpit-interactive-state";
import type { useCockpitLayout } from "./use-cockpit-layout";
import { toggleQueue, purgeQueue, emergencyStop, useHiddenPrompts, useActiveHiddenPrompts, setActiveHiddenPrompt, fetchHistoryDetail, fetchTaskDetail } from "@/hooks/use-api";

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
    const { t } = useLanguage();
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

    const onTurnFinished = useCallback(() => {
      void data.refresh.metrics(); void data.refresh.tokenMetrics();
      void data.refresh.modelsUsage(); void data.refresh.services();
    }, [data.refresh]);
    const { sessionId, resetSession, handleActivateModel, sessionActions, sessionHistoryState, historyMessages, chatUi } = useConversationController({ data, interactive, layout, chatScrollRef, onTurnFinished });
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
            void refreshActiveHiddenPrompts();
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
        sessionHistoryState,
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

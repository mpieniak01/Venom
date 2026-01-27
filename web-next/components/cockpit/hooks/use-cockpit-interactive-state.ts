"use client";

import { useState } from "react";
import type {
    GenerationParams,
    HistoryRequestDetail,
    Task,
} from "@/lib/types";
import { LogEntryType } from "@/lib/logs";
import type { GenerationSchema } from "@/components/ui/dynamic-parameter-form";
import type { ChatMode } from "@/components/cockpit/cockpit-chat-thread";
import { useOptimisticRequests } from "@/components/cockpit/cockpit-chat-hooks";

export function useCockpitInteractiveState() {
    const [chatMode, setChatMode] = useState<ChatMode>("normal");
    const [sending, setSending] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [llmActionPending, setLlmActionPending] = useState<string | null>(
        null,
    );
    const [selectedLlmServer, setSelectedLlmServer] = useState("");
    const [selectedLlmModel, setSelectedLlmModel] = useState("");

    // History detail
    const [historyDetail, setHistoryDetail] =
        useState<HistoryRequestDetail | null>(null);
    const [loadingHistory, setLoadingHistory] = useState(false);
    const [historyError, setHistoryError] = useState<string | null>(null);

    // Logs
    const [pinnedLogs, setPinnedLogs] = useState<LogEntryType[]>([]);
    const [logFilter, setLogFilter] = useState("");

    // Selection
    const [selectedRequestId, setSelectedRequestId] = useState<string | null>(
        null,
    );
    const [selectedTask, setSelectedTask] = useState<Task | null>(null);
    const [copyStepsMessage, setCopyStepsMessage] = useState<string | null>(null);

    // Feedback
    const [feedbackByRequest, setFeedbackByRequest] = useState<
        Record<
            string,
            {
                rating?: "up" | "down" | null;
                comment?: string;
                message?: string | null;
            }
        >
    >({});
    const [feedbackSubmittingId, setFeedbackSubmittingId] = useState<
        string | null
    >(null);

    // Actions
    const [gitAction, setGitAction] = useState<"sync" | "undo" | null>(null);
    const [memoryAction, setMemoryAction] = useState<
        null | "session" | "global"
    >(null);

    // Tuning
    const [generationParams, setGenerationParams] =
        useState<GenerationParams | null>(null);
    const [modelSchema, setModelSchema] = useState<GenerationSchema | null>(
        null,
    );
    const [loadingSchema, setLoadingSchema] = useState(false);
    const [tuningSaving, setTuningSaving] = useState(false);

    // Timings
    const [lastResponseDurationMs, setLastResponseDurationMs] = useState<
        number | null
    >(null);
    const [responseDurations, setResponseDurations] = useState<number[]>([]);

    // Optimistic
    const optimistic = useOptimisticRequests<HistoryRequestDetail>(chatMode);

    return {
        state: {
            chatMode,
            sending,
            message,
            llmActionPending,
            selectedLlmServer,
            selectedLlmModel,
            historyDetail,
            loadingHistory,
            historyError,
            pinnedLogs,
            logFilter,
            selectedRequestId,
            selectedTask,
            copyStepsMessage,
            feedbackByRequest,
            feedbackSubmittingId,
            gitAction,
            memoryAction,
            generationParams,
            modelSchema,
            loadingSchema,
            tuningSaving,
            lastResponseDurationMs,
            responseDurations,
        },
        setters: {
            setChatMode,
            setSending,
            setMessage,
            setLlmActionPending,
            setSelectedLlmServer,
            setSelectedLlmModel,
            setHistoryDetail,
            setLoadingHistory,
            setHistoryError,
            setPinnedLogs,
            setLogFilter,
            setSelectedRequestId,
            setSelectedTask,
            setCopyStepsMessage,
            setFeedbackByRequest,
            setFeedbackSubmittingId,
            setGitAction,
            setMemoryAction,
            setGenerationParams,
            setModelSchema,
            setLoadingSchema,
            setTuningSaving,
            setLastResponseDurationMs,
            setResponseDurations,
        },
        optimistic,
    };
}

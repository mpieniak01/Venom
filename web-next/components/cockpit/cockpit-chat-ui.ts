"use client";

import { useCallback, useEffect, useRef } from "react";
import type { GenerationParams, HistoryRequestDetail, GenerationSchema } from "@/lib/types";
import type { TaskExtraContext, ForcedRoute } from "@/hooks/use-api";
import type { ChatMessage, ChatComposerHandle } from "@/components/cockpit/cockpit-chat-thread";
import { useChatSend } from "@/components/cockpit/cockpit-chat-send";
import { useTranslation } from "@/lib/i18n";

type ActiveServerInfo = {
  active_server?: string | null;
  active_model?: string | null;
  active_endpoint?: string | null;
  config_hash?: string | null;
  runtime_id?: string | null;
} | null;

type FeedbackState = {
  rating?: "up" | "down" | null;
  comment?: string;
  message?: string | null;
};

type CockpitChatUiParams = {
  chatMessages: ChatMessage[];
  chatScrollRef: React.RefObject<HTMLDivElement>;
  feedbackByRequest: Record<string, FeedbackState>;
  setFeedbackByRequest: React.Dispatch<React.SetStateAction<Record<string, FeedbackState>>>;
  setFeedbackSubmittingId: React.Dispatch<React.SetStateAction<string | null>>;
  sendFeedback: (
    requestId: string,
    rating: "up" | "down",
    comment?: string,
  ) => Promise<{ follow_up_task_id?: string | null }>;
  refreshHistory: () => Promise<unknown>;
  refreshTasks: () => Promise<unknown>;
  responseDurations: number[];
  lastResponseDurationMs: number | null;
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
  sendTask: (
    content: string,
    storeKnowledge?: boolean,
    generationParams?: GenerationParams | null,
    runtimeMeta?: { configHash?: string | null; runtimeId?: string | null } | null,
    extraContext?: TaskExtraContext | null,
    forcedRoute?: ForcedRoute | null,
    forcedIntent?: string | null,
    preferredLanguage?: "pl" | "en" | "de" | null,
    sessionId?: string | null,
    preferenceScope?: "session" | "global" | null,
  ) => Promise<{ task_id?: string | null }>;
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
  refreshQueue: () => Promise<unknown>;
  refreshSessionHistory: () => Promise<unknown>;
  enqueueOptimisticRequest: (
    prompt: string,
    forced?: { tool?: string; provider?: string; simpleMode?: boolean },
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
  setLocalSessionHistory: React.Dispatch<React.SetStateAction<Array<{
    role?: string;
    content?: string;
    session_id?: string;
    request_id?: string;
    timestamp?: string;
  }>>>;
  setSimpleRequestDetails: React.Dispatch<
    React.SetStateAction<Record<string, HistoryRequestDetail>>
  >;
  setMessage: React.Dispatch<React.SetStateAction<string | null>>;
  setSending: React.Dispatch<React.SetStateAction<boolean>>;
  setLastResponseDurationMs: React.Dispatch<React.SetStateAction<number | null>>;
  setResponseDurations: React.Dispatch<React.SetStateAction<number[]>>;
  models: {
    active?: { model?: string; provider?: string };
  } | null;
  fetchModelConfig: (modelName: string) => Promise<{
    generation_schema?: GenerationSchema;
    current_values?: Record<string, unknown>;
  } | null>;
  updateModelConfig: (modelName: string, payload: {
    runtime?: string;
    params: Record<string, number | string | boolean | null | undefined>;
  }) => Promise<unknown>;
  setTuningOpen: React.Dispatch<React.SetStateAction<boolean>>;
  setLoadingSchema: React.Dispatch<React.SetStateAction<boolean>>;
  setModelSchema: React.Dispatch<React.SetStateAction<GenerationSchema | null>>;
  setGenerationParams: React.Dispatch<React.SetStateAction<GenerationParams | null>>;
  setTuningSaving: React.Dispatch<React.SetStateAction<boolean>>;
  pushToast: (message: string, tone?: "success" | "warning" | "error" | "info") => void;
  pinnedLogs: Array<{ payload: unknown }>;
  setExportingPinned: React.Dispatch<React.SetStateAction<boolean>>;
};

export function useCockpitChatUi({
  chatMessages,
  chatScrollRef,
  feedbackByRequest,
  setFeedbackByRequest,
  setFeedbackSubmittingId,
  sendFeedback,
  refreshHistory,
  refreshTasks,
  responseDurations,
  lastResponseDurationMs,
  labMode,
  chatMode,
  generationParams,
  selectedLlmModel,
  activeServerInfo,
  sessionId,
  language,
  resetSession,
  refreshActiveServer,
  setActiveLlmRuntime,
  sendSimpleChatStream,
  sendTask,
  ingestMemoryEntry,
  refreshQueue,
  refreshSessionHistory,
  enqueueOptimisticRequest,
  linkOptimisticRequest,
  dropOptimisticRequest,
  updateSimpleStream,
  recordUiTiming,
  uiTimingsRef,
  clearSimpleStream,
  setLocalSessionHistory,
  setSimpleRequestDetails,
  setMessage,
  setSending,
  setLastResponseDurationMs,
  setResponseDurations,
  models,
  fetchModelConfig,
  updateModelConfig,
  setTuningOpen,
  setLoadingSchema,
  setModelSchema,
  setGenerationParams,
  setTuningSaving,
  pushToast,
  pinnedLogs,
  setExportingPinned,
}: CockpitChatUiParams) {
  const t = useTranslation();
  const lastChatScrollTop = useRef(0);
  const didInitialChatScroll = useRef(false);
  const programmaticChatScroll = useRef(false);
  const autoScrollEnabled = useRef(true);
  const scrollChatToBottom = useCallback(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    programmaticChatScroll.current = true;
    container.scrollTop = container.scrollHeight;
    requestAnimationFrame(() => {
      programmaticChatScroll.current = false;
      lastChatScrollTop.current = container.scrollTop;
      autoScrollEnabled.current = true;
    });
  }, [chatScrollRef]);
  useEffect(() => {
    if (didInitialChatScroll.current) return;
    if (chatMessages.length === 0) return;
    scrollChatToBottom();
    didInitialChatScroll.current = true;
  }, [chatMessages.length, scrollChatToBottom]);
  useEffect(() => {
    if (!autoScrollEnabled.current) return;
    scrollChatToBottom();
  }, [chatMessages, scrollChatToBottom]);
  const handleChatScroll = useCallback(() => {
    const container = chatScrollRef.current;
    if (!container) return;
    if (programmaticChatScroll.current) {
      lastChatScrollTop.current = container.scrollTop;
      return;
    }
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    const isAtBottom = distanceFromBottom <= 12;
    const scrolledUp = container.scrollTop < lastChatScrollTop.current - 2;
    if (scrolledUp) {
      autoScrollEnabled.current = false;
    } else if (isAtBottom) {
      autoScrollEnabled.current = true;
    }
    lastChatScrollTop.current = container.scrollTop;
  }, [chatScrollRef]);
  const updateFeedbackState = useCallback(
    (
      requestId: string,
      patch: Partial<FeedbackState>,
    ) => {
      setFeedbackByRequest((prev) => ({
        ...prev,
        [requestId]: { ...prev[requestId], ...patch },
      }));
    },
    [setFeedbackByRequest],
  );
  const handleFeedbackSubmit = useCallback(
    async (
      requestId: string,
      override?: { rating: "up" | "down"; comment?: string },
    ) => {
      const state = feedbackByRequest[requestId] || {};
      const rating = override?.rating ?? state.rating;
      const comment = override?.comment ?? state.comment ?? "";
      if (!rating) return;
      setFeedbackSubmittingId(requestId);
      updateFeedbackState(requestId, { message: null });
      try {
        const response = await sendFeedback(
          requestId,
          rating,
          rating === "down" ? comment.trim() : undefined,
        );
        if (rating === "down") {
          updateFeedbackState(requestId, {
            message: response.follow_up_task_id
              ? t("cockpit.feedback.refining", { taskId: response.follow_up_task_id })
              : t("cockpit.feedback.refiningPending"),
          });
        } else {
          updateFeedbackState(requestId, { message: t("cockpit.feedback.success") });
        }
        refreshHistory();
        refreshTasks();
      } catch (error) {
        updateFeedbackState(requestId, {
          message:
            error instanceof Error
              ? error.message
              : t("cockpit.feedback.error"),
        });
      } finally {
        setFeedbackSubmittingId(null);
      }
    },
    [feedbackByRequest, refreshHistory, refreshTasks, sendFeedback, setFeedbackSubmittingId, updateFeedbackState, t],
  );
  const handleFeedbackClick = useCallback(
    (requestId: string, rating: "up" | "down") => {
      if (rating === "up") {
        updateFeedbackState(requestId, { rating: "up", comment: "" });
        handleFeedbackSubmit(requestId, { rating: "up" });
        return;
      }
      updateFeedbackState(requestId, { rating: "down" });
    },
    [handleFeedbackSubmit, updateFeedbackState],
  );
  const averageResponseDurationMs =
    responseDurations.length > 0
      ? responseDurations.reduce((acc, value) => acc + value, 0) /
      Math.max(responseDurations.length, 1)
      : null;
  const responseBadgeText =
    lastResponseDurationMs !== null ? `${(lastResponseDurationMs / 1000).toFixed(1)}s` : t("cockpit.response.notAvailable");
  const responseBadgeTone =
    lastResponseDurationMs === null
      ? "neutral"
      : lastResponseDurationMs <= 4000
        ? "success"
        : "warning";
  const responseBadgeTitle =
    averageResponseDurationMs !== null
      ? t("cockpit.response.avg", {
        count: responseDurations.length,
        avg: (averageResponseDurationMs / 1000).toFixed(1)
      })
      : t("cockpit.response.noData");
  const handleSend = useChatSend({
    labMode,
    chatMode,
    generationParams,
    selectedLlmModel,
    activeServerInfo,
    sessionId,
    language,
    resetSession,
    refreshActiveServer,
    setActiveLlmRuntime,
    sendSimpleChatStream,
    sendTask,
    ingestMemoryEntry,
    refreshTasks,
    refreshQueue,
    refreshHistory,
    refreshSessionHistory,
    enqueueOptimisticRequest,
    linkOptimisticRequest,
    dropOptimisticRequest,
    updateSimpleStream,
    recordUiTiming,
    uiTimingsRef,
    clearSimpleStream,
    setLocalSessionHistory,
    setSimpleRequestDetails,
    setMessage,
    setSending,
    setLastResponseDurationMs,
    setResponseDurations,
    scrollChatToBottom,
    autoScrollEnabled,
  });

  const handleOpenTuning = useCallback(async () => {
    setTuningOpen(true);
    setLoadingSchema(true);
    setGenerationParams(null);
    try {
      const activeModelName = models?.active?.model || "llama3";
      const config = await fetchModelConfig(activeModelName);
      const schema = config?.generation_schema as GenerationSchema | undefined;
      setModelSchema(schema ?? null);
      if (config?.current_values) {
        setGenerationParams(config.current_values as GenerationParams);
      }
    } catch (err) {
      console.error(t("cockpit.feedback.schemaError"), err);
      setModelSchema(null);
    } finally {
      setLoadingSchema(false);
    }
  }, [fetchModelConfig, models, setGenerationParams, setLoadingSchema, setModelSchema, setTuningOpen, t]);

  const handleApplyTuning = useCallback(async () => {
    const activeModelName = models?.active?.model;
    if (!activeModelName) {
      pushToast(t("cockpit.feedback.noLlm"), "warning");
      return;
    }
    setTuningSaving(true);
    try {
      await updateModelConfig(activeModelName, {
        runtime: models?.active?.provider,
        params: (generationParams ?? {}) as Record<
          string,
          number | string | boolean | null | undefined
        >,
      });
      pushToast(t("cockpit.feedback.tuningSaved"), "success");
    } catch (err) {
      pushToast(
        err instanceof Error ? err.message : t("cockpit.feedback.tuningError"),
        "error",
      );
    } finally {
      setTuningSaving(false);
    }
  }, [generationParams, models, pushToast, setTuningSaving, updateModelConfig, t]);

  const handleExportPinnedLogs = useCallback(async () => {
    if (pinnedLogs.length === 0) return;
    setExportingPinned(true);
    try {
      const blob = new Blob(
        [JSON.stringify(pinnedLogs.map((log) => log.payload), null, 2)],
        { type: "application/json" },
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "pinned-logs.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Clipboard error:", err);
    } finally {
      setExportingPinned(false);
    }
  }, [pinnedLogs, setExportingPinned]);

  const composerRef = useRef<ChatComposerHandle | null>(null);
  const handleSuggestionClick = useCallback((prompt: string) => {
    composerRef.current?.setDraft(prompt);
  }, []);

  return {
    autoScrollEnabled,
    composerRef,
    handleApplyTuning,
    handleChatScroll,
    handleExportPinnedLogs,
    handleFeedbackClick,
    handleFeedbackSubmit,
    handleOpenTuning,
    handleSend,
    handleSuggestionClick,
    responseBadgeText,
    responseBadgeTone,
    responseBadgeTitle,
    scrollChatToBottom,
    updateFeedbackState,
    chatMessages,
  };
}

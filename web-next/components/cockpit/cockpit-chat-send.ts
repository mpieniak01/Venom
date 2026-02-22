"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n";
import { parseSlashCommand } from "@/lib/slash-commands";

import {
  ChatSendParams,
  RuntimeOverride,
  handleRuntimeSwitch,
  handleSimpleTaskSend,
  handleStandardTaskSend,
} from "./chat-send-helpers";

export function useChatSend(params: ChatSendParams) {
  const {
    labMode,
    chatMode,
    generationParams,
    selectedLlmModel,
    selectedLlmServer,
    activeServerInfo,
    sessionId,
    language,
    resetSession,
    refreshActiveServer,
    setActiveLlmRuntime,
    setActiveLlmServer,
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
  } = params;

  const t = useTranslation();

  return useCallback(async (payload: string) => {
    const parsed = parseSlashCommand(payload);
    const trimmed = parsed.cleaned.trim();
    if (!trimmed) {
      setMessage(t("cockpit.chatMessages.emptyPrompt"));
      return false;
    }

    let sessionOverride: string | null = null;
    const switchResult = await handleRuntimeSwitch({
      parsed,
      activeServerInfo,
      selectedLlmModel,
      setActiveLlmRuntime,
      refreshActiveServer,
      setMessage,
      confirm: (msg) => globalThis.window.confirm(msg),
      t,
    });

    if (!switchResult.success) return false;
    const runtimeOverride: RuntimeOverride = switchResult.runtimeOverride;

    if (parsed.sessionReset) {
      sessionOverride = resetSession();
    }
    const resolvedSession = sessionOverride ?? sessionId;
    if (!resolvedSession) {
      setMessage(t("cockpit.chatMessages.sessionInitializing"));
      return false;
    }

    const targetServer = (selectedLlmServer || "").toLowerCase().trim();
    const activeServer = (activeServerInfo?.active_server || "").toLowerCase().trim();
    if (targetServer && activeServer && targetServer !== activeServer) {
      try {
        await setActiveLlmServer(targetServer);
        refreshActiveServer();
      } catch (err) {
        setMessage(
          err instanceof Error
            ? err.message
            : t("cockpit.chatMessages.serverSwitchError"),
        );
        return false;
      }
    }

    autoScrollEnabled.current = true;
    scrollChatToBottom();
    setSending(true);
    setMessage(null);

    const shouldUseSimple =
      chatMode === "direct" &&
      !parsed.forcedTool &&
      !parsed.forcedProvider &&
      !parsed.sessionReset;

    const forcedIntent = chatMode === "complex" ? "COMPLEX_PLANNING" : null;
    const clientId = enqueueOptimisticRequest(trimmed, {
      tool: parsed.forcedTool,
      provider: parsed.forcedProvider,
      intent: forcedIntent ?? undefined,
      simpleMode: shouldUseSimple,
    });

    if (!shouldUseSimple) {
      const timestamp = new Date().toISOString();
      setLocalSessionHistory((prev) => {
        if (prev.some((entry) => entry.request_id === clientId && entry.role === "user")) {
          return prev;
        }
        return [
          ...prev,
          {
            role: "user",
            content: trimmed,
            request_id: clientId,
            timestamp,
            session_id: resolvedSession ?? undefined,
          },
        ];
      });
      const timing = uiTimingsRef.current.get(clientId);
      if (timing && timing.historyMs === undefined) {
        recordUiTiming(clientId, { historyMs: Date.now() - timing.t0 });
      }
    }

    void (async () => {
      const taskParams = {
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
      };

      if (shouldUseSimple) {
        await handleSimpleTaskSend(taskParams);
      } else {
        await handleStandardTaskSend({
          ...taskParams,
          labMode,
          runtimeOverride,
          parsed,
          forcedIntent,
          language,
          sendTask,
          refreshTasks,
          refreshQueue,
          refreshHistory,
          refreshSessionHistory,
          t,
        });
      }
    })();

    return true;
  }, [
    activeServerInfo,
    autoScrollEnabled,
    chatMode,
    clearSimpleStream,
    dropOptimisticRequest,
    enqueueOptimisticRequest,
    generationParams,
    ingestMemoryEntry,
    language,
    linkOptimisticRequest,
    recordUiTiming,
    refreshActiveServer,
    refreshHistory,
    refreshQueue,
    refreshSessionHistory,
    refreshTasks,
    resetSession,
    scrollChatToBottom,
    selectedLlmModel,
    selectedLlmServer,
    sendSimpleChatStream,
    sendTask,
    sessionId,
    t,
    labMode,
    setLastResponseDurationMs,
    setLocalSessionHistory,
    setMessage,
    setResponseDurations,
    setSending,
    setSimpleRequestDetails,
    setActiveLlmRuntime,
    setActiveLlmServer,
    uiTimingsRef,
    updateSimpleStream,
  ]);
}

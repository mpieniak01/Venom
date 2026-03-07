"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n";
import { parseInputCommand } from "@/lib/slash-commands";

import {
  ChatSendParams,
  RuntimeOverride,
  handleRuntimeSwitch,
  handleSimpleTaskSend,
  handleStandardTaskSend,
} from "./chat-send-helpers";

function resolveSession(
  parsed: ReturnType<typeof parseInputCommand>,
  sessionId: string | null,
  resetSession: () => string | null,
): string | null {
  if (!parsed.sessionReset) {
    return sessionId;
  }
  return resetSession() ?? sessionId;
}

function getServerSwitchErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback;
}

function isCloudRuntimeServer(server: string): server is "openai" | "google" {
  return server === "openai" || server === "google";
}

function shouldUseSimpleMode(
  chatMode: ChatSendParams["chatMode"],
  parsed: ReturnType<typeof parseInputCommand>,
): boolean {
  return (
    chatMode === "direct" &&
    !parsed.forcedTool &&
    !parsed.forcedProvider &&
    !parsed.sessionReset
  );
}

async function syncTargetServerIfNeeded(params: {
  selectedLlmServer: string;
  selectedLlmModel: string;
  activeServerInfo: ChatSendParams["activeServerInfo"];
  setActiveLlmRuntime: ChatSendParams["setActiveLlmRuntime"];
  setActiveLlmServer: ChatSendParams["setActiveLlmServer"];
  refreshActiveServer: ChatSendParams["refreshActiveServer"];
  setMessage: ChatSendParams["setMessage"];
  t: (key: string) => string;
}): Promise<boolean> {
  const targetServer = (params.selectedLlmServer || "").toLowerCase().trim();
  const activeServer = (params.activeServerInfo?.active_server || "").toLowerCase().trim();
  if (!targetServer || !activeServer || targetServer === activeServer) return true;
  try {
    if (isCloudRuntimeServer(targetServer)) {
      await params.setActiveLlmRuntime(targetServer, params.selectedLlmModel);
    } else {
      await params.setActiveLlmServer(targetServer, params.selectedLlmModel);
    }
    params.refreshActiveServer();
    return true;
  } catch (err) {
    params.setMessage(getServerSwitchErrorMessage(err, params.t("cockpit.chatMessages.serverSwitchError")));
    return false;
  }
}

async function ensureSelectedModelIsActive(params: {
  activeServerInfo: ChatSendParams["activeServerInfo"];
  selectedLlmModel: string;
  ensureModelActive: ChatSendParams["ensureModelActive"];
  setMessage: ChatSendParams["setMessage"];
  t: (key: string) => string;
}): Promise<boolean> {
  const activeModel = (params.activeServerInfo?.active_model || "").trim().toLowerCase();
  const selectedModel = (params.selectedLlmModel || "").trim().toLowerCase();
  if (!selectedModel || selectedModel === activeModel || !params.ensureModelActive) {
    return true;
  }
  const activated = await params.ensureModelActive(params.selectedLlmModel);
  if (activated) return true;
  params.setMessage(params.t("cockpit.chatMessages.serverSwitchError"));
  return false;
}

async function executeSendFlow(params: {
  shouldUseSimple: boolean;
  taskParams: Parameters<typeof handleSimpleTaskSend>[0];
  standardParams: Parameters<typeof handleStandardTaskSend>[0];
}) {
  if (params.shouldUseSimple) {
    await handleSimpleTaskSend(params.taskParams);
    return;
  }
  await handleStandardTaskSend(params.standardParams);
}

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
    ensureModelActive,
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
    autoScrollEnabled: autoScrollEnabledRef,
  } = params;

  const t = useTranslation();

  return useCallback(async (payload: string) => {
    const parsed = parseInputCommand(payload);
    const trimmed = parsed.cleaned.trim();
    if (!trimmed) {
      setMessage(t("cockpit.chatMessages.emptyPrompt"));
      return false;
    }
    if (selectedLlmServer && !selectedLlmModel) {
      setMessage(t("cockpit.chatMessages.modelSelectionRequired"));
      return false;
    }

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

    const resolvedSession = resolveSession(parsed, sessionId, resetSession);
    if (!resolvedSession) {
      setMessage(t("cockpit.chatMessages.sessionInitializing"));
      return false;
    }

    const serverOk = await syncTargetServerIfNeeded({
      selectedLlmServer,
      selectedLlmModel,
      activeServerInfo,
      setActiveLlmRuntime,
      setActiveLlmServer,
      refreshActiveServer,
      setMessage,
      t,
    });
    if (!serverOk) return false;
    const modelOk = await ensureSelectedModelIsActive({
      activeServerInfo,
      selectedLlmModel,
      ensureModelActive,
      setMessage,
      t,
    });
    if (!modelOk) return false;

    autoScrollEnabledRef.current = true;
    scrollChatToBottom();
    setSending(true);
    setMessage(null);

    const shouldUseSimple = shouldUseSimpleMode(chatMode, parsed);

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
    executeSendFlow({
      shouldUseSimple,
      taskParams,
      standardParams: {
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
      },
    }).catch((error) => {
      const message = error instanceof Error ? error.message : t("cockpit.chatMessages.serverSwitchError");
      setMessage(message);
      setSending(false);
    });

    return true;
  }, [
    activeServerInfo,
    autoScrollEnabledRef,
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
    ensureModelActive,
    uiTimingsRef,
    updateSimpleStream,
  ]);
}

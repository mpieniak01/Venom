"use client";

import { runtimeControlErrorHint } from "@/lib/runtime-control-error";
import { useCallback, useRef } from "react";
import { quoteOpenRouterChat } from "@/hooks/use-api";
import { pendingOpenRouterCost, type OpenRouterQuote } from "@/lib/openrouter-chat";
import { publishOpenRouterQuote } from "@/lib/openrouter-quote-state";
import { allowsOpenRouterChat, isOpenRouterRuntime } from "@/lib/remote-chat";
import { appendVastChatTurn, vastChatHistoryKey, type VastChatTurn } from "@/lib/vast-chat-history";
import { useTranslation } from "@/lib/i18n";
import { parseInputCommand } from "@/lib/slash-commands";

import {
  ChatSendParams,
  RuntimeOverride,
  handleRuntimeSwitch,
  handleSimpleTaskSend,
  handleStandardTaskSend,
  buildSimpleStreamRequestPayload,
  addInitialSimpleUserHistoryEntry,
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

function getServerSwitchErrorMessage(err: unknown, fallback: string, t: (key: string) => string): string {
  return runtimeControlErrorHint(err, t) ?? (err instanceof Error ? err.message : fallback);
}

function isCloudRuntimeServer(server: string): server is "openai" | "google" | "openrouter" {
  return server === "openai" || server === "google" || server === "openrouter";
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

export function resolveEffectiveChatModelSelection(
  selectedLlmModel: string,
  activeModel: string | null | undefined,
  selectedRuntime = "",
  activeRuntime = "",
): string {
  const selected = (selectedLlmModel || "").trim();
  if (selected) return selected;
  if (selectedRuntime !== activeRuntime && [selectedRuntime, activeRuntime].some(runtime => runtime === "vast_ollama" || runtime === "openrouter")) return "";
  return String(activeModel || "").trim();
}

export async function syncTargetServerIfNeeded(params: {
  selectedLlmServer: string;
  selectedLlmModel: string;
  activeServerInfo: ChatSendParams["activeServerInfo"];
  setActiveLlmRuntime: ChatSendParams["setActiveLlmRuntime"];
  setActiveLlmServer: ChatSendParams["setActiveLlmServer"];
  refreshActiveServer: ChatSendParams["refreshActiveServer"];
  setMessage: ChatSendParams["setMessage"];
  t: (key: string) => string;
}): Promise<ChatSendParams["activeServerInfo"] | false> {
  const targetServer = (params.selectedLlmServer || "").toLowerCase().trim();
  const activeServer = (params.activeServerInfo?.active_server || "").toLowerCase().trim();
  const sameModel = !params.selectedLlmModel || params.selectedLlmModel === params.activeServerInfo?.active_model;
  const identityReady = targetServer !== "openrouter" || Boolean(
    params.activeServerInfo?.active_model
    && params.activeServerInfo.runtime_id === "openrouter@" + params.activeServerInfo.active_model
    && params.activeServerInfo.config_hash?.trim(),
  );
  if (!targetServer || (targetServer === activeServer && sameModel && identityReady)) return params.activeServerInfo;
  try {
    const switched = isCloudRuntimeServer(targetServer)
      ? await params.setActiveLlmRuntime(targetServer, params.selectedLlmModel)
      : await params.setActiveLlmServer(targetServer, params.selectedLlmModel);
    params.refreshActiveServer();
    return { ...params.activeServerInfo, ...switched, active_server: targetServer };
  } catch (err) {
    params.setMessage(getServerSwitchErrorMessage(err, params.t("cockpit.chatMessages.serverSwitchError"), params.t));
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

async function prepareOpenRouterQuote(params: {
  activeServerInfo: ChatSendParams["activeServerInfo"];
  trimmed: string;
  selectedModel: string;
  generationParams: ChatSendParams["generationParams"];
  resolvedSession: string;
  history: VastChatTurn[] | undefined;
  setMessage: ChatSendParams["setMessage"];
  setSending: ChatSendParams["setSending"];
  t: (key: string) => string;
}): Promise<OpenRouterQuote | undefined | false> {
  if (!isOpenRouterRuntime(params.activeServerInfo?.runtime_id) && params.activeServerInfo?.active_server !== "openrouter") {
    return undefined;
  }
  try {
    const quote = await quoteOpenRouterChat(buildSimpleStreamRequestPayload(
      params.trimmed, params.selectedModel, params.generationParams,
      params.resolvedSession, params.activeServerInfo, params.history,
    ));
    publishOpenRouterQuote(params.selectedModel, params.resolvedSession, quote);
    return quote;
  } catch {
    params.setMessage(params.t("cockpit.openrouter.quoteFailed"));
    params.setSending(false);
    return false;
  }
}

function recordStandardRequestHistory(params: {
  shouldUseSimple: boolean;
  clientId: string;
  trimmed: string;
  resolvedSession: string | null;
  setLocalSessionHistory: ChatSendParams["setLocalSessionHistory"];
  uiTimingsRef: ChatSendParams["uiTimingsRef"];
  recordUiTiming: ChatSendParams["recordUiTiming"];
}): void {
  if (params.shouldUseSimple) return;
  addInitialSimpleUserHistoryEntry(
    params.setLocalSessionHistory,
    params.clientId,
    params.trimmed,
    new Date().toISOString(),
    params.resolvedSession,
  );
  const timing = params.uiTimingsRef.current.get(params.clientId);
  if (timing && timing.historyMs === undefined) {
    params.recordUiTiming(params.clientId, { historyMs: Date.now() - timing.t0 });
  }
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
  const vastHistory = useRef(new Map<string, VastChatTurn[]>());

  return useCallback(async (payload: string) => {
    const parsed = parseInputCommand(payload);
    const trimmed = parsed.cleaned.trim();
    if (!trimmed) {
      setMessage(t("cockpit.chatMessages.emptyPrompt"));
      return false;
    }
    const effectiveSelectedModel = resolveEffectiveChatModelSelection(
      selectedLlmModel,
      activeServerInfo?.active_model,
      selectedLlmServer,
      activeServerInfo?.active_server ?? "",
    );
    if (selectedLlmServer && !effectiveSelectedModel) {
      setMessage(t("cockpit.chatMessages.modelSelectionRequired"));
      return false;
    }

    if (!allowsOpenRouterChat(selectedLlmServer || activeServerInfo?.active_server || "", shouldUseSimpleMode(chatMode, parsed))) {
      setMessage(t("cockpit.openrouter.directOnly"));
      return false;
    }

    const resolvedSession = resolveSession(parsed, sessionId, resetSession);
    if (!resolvedSession) {
      setMessage(t("cockpit.chatMessages.sessionInitializing"));
      return false;
    }

    const switchResult = await handleRuntimeSwitch({
      parsed,
      activeServerInfo,
      selectedLlmModel: effectiveSelectedModel,
      setActiveLlmRuntime,
      refreshActiveServer,
      setMessage,
      confirm: (msg) => globalThis.window.confirm(msg),
      t,
    });

    if (!switchResult.success) return false;
    const runtimeOverride: RuntimeOverride = switchResult.runtimeOverride;

    const effectiveActiveServerInfo = await syncTargetServerIfNeeded({
      selectedLlmServer,
      selectedLlmModel: effectiveSelectedModel,
      activeServerInfo,
      setActiveLlmRuntime,
      setActiveLlmServer,
      refreshActiveServer,
      setMessage,
      t,
    });
    if (effectiveActiveServerInfo === false) return false;
    const modelOk = await ensureSelectedModelIsActive({
      activeServerInfo: effectiveActiveServerInfo,
      selectedLlmModel: effectiveSelectedModel,
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
    const historyKey = vastChatHistoryKey(effectiveActiveServerInfo?.runtime_id, effectiveSelectedModel, resolvedSession, effectiveActiveServerInfo?.config_hash);
    const history = historyKey ? (vastHistory.current.get(historyKey) ?? []).map(turn => ({...turn})) : undefined;
    const quote = await prepareOpenRouterQuote({
      activeServerInfo: effectiveActiveServerInfo,
      trimmed,
      selectedModel: effectiveSelectedModel,
      generationParams,
      resolvedSession,
      history,
      setMessage,
      setSending,
      t,
    });
    if (quote === false) return false;

    const forcedIntent = chatMode === "complex" ? "COMPLEX_PLANNING" : null;
    const clientId = enqueueOptimisticRequest(trimmed, {
      tool: parsed.forcedTool,
      provider: parsed.forcedProvider,
      intent: forcedIntent ?? undefined,
      simpleMode: shouldUseSimple,
    });

    recordStandardRequestHistory({
      shouldUseSimple,
      clientId,
      trimmed,
      resolvedSession,
      setLocalSessionHistory,
      uiTimingsRef,
      recordUiTiming,
    });


    const taskParams = {
      ...(historyKey ? {
        history,
        onCompleted: (answer: string) => {
          const history = appendVastChatTurn(vastHistory.current.get(historyKey) ?? [], trimmed, answer);
          vastHistory.current.clear();
          vastHistory.current.set(historyKey, history);
        },
      } : {}),
      ...(quote ? {expectedQuoteHash: quote.quote_hash, initialCost: {...pendingOpenRouterCost(), estimated_usd: quote.estimated_usd}} : {}),
      clientId,
      trimmed,
      resolvedSession,
      generationParams,
      selectedLlmModel: effectiveSelectedModel,
      activeServerInfo: effectiveActiveServerInfo,
      t,
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

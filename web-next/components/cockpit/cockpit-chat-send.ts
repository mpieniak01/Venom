"use client";

import { useCallback } from "react";
import { useTranslation } from "@/lib/i18n";
import type { GenerationParams, HistoryRequestDetail } from "@/lib/types";
import type { TaskExtraContext, ForcedRoute } from "@/hooks/use-api";
import { parseSlashCommand } from "@/lib/slash-commands";
import { createParser } from "eventsource-parser";

type ActiveServerInfo = {
  active_server?: string | null;
  active_model?: string | null;
  active_endpoint?: string | null;
  config_hash?: string | null;
  runtime_id?: string | null;
} | null;

type ChatSendParams = {
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
  refreshTasks: () => Promise<unknown>;
  refreshQueue: () => Promise<unknown>;
  refreshHistory: () => Promise<unknown>;
  refreshSessionHistory: () => Promise<unknown>;
  enqueueOptimisticRequest: (
    prompt: string,
    forced?: {
      tool?: string;
      provider?: string;
      intent?: string;
      simpleMode?: boolean;
    },
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
  setSimpleRequestDetails: React.Dispatch<React.SetStateAction<Record<string, HistoryRequestDetail>>>;
  setMessage: (message: string | null) => void;
  setSending: (value: boolean) => void;
  setLastResponseDurationMs: React.Dispatch<React.SetStateAction<number | null>>;
  setResponseDurations: React.Dispatch<React.SetStateAction<number[]>>;
  scrollChatToBottom: () => void;
  autoScrollEnabled: React.MutableRefObject<boolean>;
};

export function useChatSend({
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
}: ChatSendParams) {
  const t = useTranslation();
  return useCallback(async (payload: string) => {
    const parsed = parseSlashCommand(payload);
    const trimmed = parsed.cleaned.trim();
    if (!trimmed) {
      setMessage("Podaj treść zadania.");
      return false;
    }
    let sessionOverride: string | null = null;
    let runtimeOverride: { configHash?: string | null; runtimeId?: string | null } | null = null;
    const forcedRuntimeProvider =
      parsed.forcedProvider === "gpt"
        ? "openai"
        : parsed.forcedProvider === "gem"
          ? "google"
          : parsed.forcedProvider;
    const activeRuntime = activeServerInfo?.active_server ?? null;
    if (forcedRuntimeProvider && activeRuntime !== forcedRuntimeProvider) {
      const label = forcedRuntimeProvider === "openai" ? "OpenAI" : "Gemini";
      const confirmed = window.confirm(
        `Dyrektywa wymaga przełączenia runtime na ${label}. Przełączyć teraz?`,
      );
      if (!confirmed) {
        setMessage("Anulowano przełączenie runtime.");
        return false;
      }
      try {
        const runtime = await setActiveLlmRuntime(forcedRuntimeProvider as "openai" | "google", selectedLlmModel);
        runtimeOverride = {
          configHash: runtime.config_hash ?? null,
          runtimeId: runtime.runtime_id ?? null,
        };
        refreshActiveServer();
      } catch (err) {
        setMessage(err instanceof Error ? err.message : "Nie udało się przełączyć runtime.");
        return false;
      }
    }
    if (parsed.sessionReset) {
      sessionOverride = resetSession();
    }
    const resolvedSession = sessionOverride ?? sessionId;
    if (!resolvedSession) {
      setMessage("Sesja inicjalizuje się. Spróbuj ponownie za chwilę.");
      return false;
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
      if (shouldUseSimple) {
        try {
          const createdTimestamp = new Date().toISOString();
          setLocalSessionHistory((prev) => {
            const next = [...prev];
            const exists = next.some(
              (entry) => entry.request_id === clientId && entry.role === "user",
            );
            if (!exists) {
              next.push({
                role: "user",
                content: trimmed,
                request_id: clientId,
                timestamp: createdTimestamp,
                session_id: resolvedSession ?? undefined,
              });
            }
            return next;
          });
          updateSimpleStream(clientId, { text: "", status: "W toku", done: false });
          const maxTokens =
            typeof generationParams?.max_tokens === "number"
              ? generationParams.max_tokens
              : null;
          const temperature =
            typeof generationParams?.temperature === "number"
              ? generationParams.temperature
              : null;
          const response = await sendSimpleChatStream({
            content: trimmed,
            model: selectedLlmModel || null,
            maxTokens,
            temperature,
            sessionId: resolvedSession,
          });
          const headerRequestId = response.headers.get("x-request-id");
          const simpleRequestId = headerRequestId || `simple-${clientId}`;
          linkOptimisticRequest(clientId, simpleRequestId);

          // Reconcile user message ID in local history to avoid duplication
          setLocalSessionHistory((prev) => {
            return prev.map((entry) => {
              if (entry.request_id === clientId && entry.role === "user") {
                return { ...entry, request_id: simpleRequestId };
              }
              return entry;
            });
          });
          let lastHistoryUpdate = 0;
          const upsertLocalHistory = (role: "user" | "assistant", content: string) => {
            const now = Date.now();
            if (role === "assistant" && now - lastHistoryUpdate < 60) {
              return;
            }
            lastHistoryUpdate = now;
            setLocalSessionHistory((prev) => {
              const next = [...prev];
              const idx = next.findIndex(
                (entry) =>
                  entry.request_id === simpleRequestId && entry.role === role,
              );
              const timestamp = role === "assistant" ? new Date().toISOString() : createdTimestamp;
              if (idx >= 0) {
                next[idx] = {
                  ...next[idx],
                  content,
                  timestamp,
                };
              } else {
                next.push({
                  role,
                  content,
                  request_id: simpleRequestId,
                  timestamp,
                  session_id: resolvedSession ?? undefined,
                });
              }
              return next;
            });
          };
          upsertLocalHistory("user", trimmed);
          const historyTiming = uiTimingsRef.current.get(clientId);
          if (historyTiming && historyTiming.historyMs === undefined) {
            recordUiTiming(clientId, { historyMs: Date.now() - historyTiming.t0 });
          }
          const reader = response.body?.getReader();
          if (!reader) {
            throw new Error("Brak strumienia odpowiedzi z API.");
          }

          const decoder = new TextDecoder();
          let buffer = ""; // To store the full text for history/memory
          const startedAt = Date.now();
          let firstChunkLogged = false;

          const parser = createParser({
            onEvent: (msg) => {
              if (msg.event === "content") {
                const data = JSON.parse(msg.data);
                if (data.text) {
                  buffer += data.text;
                  if (!firstChunkLogged) {
                    const ttftTiming = uiTimingsRef.current.get(simpleRequestId);
                    if (ttftTiming && ttftTiming.ttftMs === undefined) {
                      recordUiTiming(simpleRequestId, { ttftMs: Date.now() - ttftTiming.t0 });
                    }
                    firstChunkLogged = true;
                  }
                  updateSimpleStream(clientId, { text: buffer, status: "W toku" });
                  upsertLocalHistory("assistant", buffer);
                }
              } else if (msg.event === "error") {
                const data = JSON.parse(msg.data);
                throw new Error(data.error || "Wystąpił błąd strumieniowania.");
              }
            },
          });

          try {
            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              const chunk = decoder.decode(value, { stream: true });
              if (chunk) {
                parser.feed(chunk);
              }
            }
          } finally {
            reader.releaseLock();
          }
          updateSimpleStream(clientId, { text: buffer, status: "COMPLETED", done: true });
          const duration = Date.now() - startedAt;
          const timestamp = new Date().toISOString();
          const simpleModelName = selectedLlmModel || activeServerInfo?.active_model || undefined;
          const simpleEndpoint = activeServerInfo?.active_endpoint ?? undefined;
          setLocalSessionHistory((prev) => {
            const next = [...prev];
            const upsert = (role: "user" | "assistant", content: string) => {
              const idx = next.findIndex(
                (entry) =>
                  entry.request_id === simpleRequestId && entry.role === role,
              );
              if (idx >= 0) {
                next[idx] = {
                  ...next[idx],
                  content,
                  timestamp,
                };
              } else {
                next.push({
                  role,
                  content,
                  request_id: simpleRequestId,
                  timestamp,
                  session_id: resolvedSession ?? undefined,
                });
              }
            };
            upsert("user", trimmed);
            upsert("assistant", buffer);
            return next;
          });
          const timing = uiTimingsRef.current.get(simpleRequestId);
          const steps = [
            timing?.historyMs !== undefined
              ? {
                component: "UI",
                action: "submit_to_history",
                status: "OK",
                timestamp,
                details: `history_ms=${Math.round(timing.historyMs)}`,
              }
              : null,
            timing?.ttftMs !== undefined
              ? {
                component: "UI",
                action: "ttft",
                status: "OK",
                timestamp,
                details: `ttft_ms=${Math.round(timing.ttftMs)}`,
              }
              : null,
          ].filter(Boolean) as HistoryRequestDetail["steps"];
          const simpleProvider =
            activeServerInfo?.active_server ?? activeServerInfo?.runtime_id?.split("@")[0] ?? "local";
          setSimpleRequestDetails((prev) => ({
            ...prev,
            [simpleRequestId]: {
              request_id: simpleRequestId,
              prompt: trimmed,
              status: "COMPLETED",
              model: simpleModelName,
              llm_provider: simpleProvider,
              llm_model: simpleModelName ?? null,
              llm_endpoint: simpleEndpoint ?? null,
              llm_config_hash: activeServerInfo?.config_hash ?? null,
              llm_runtime_id: activeServerInfo?.runtime_id ?? null,
              forced_tool: null,
              forced_provider: null,
              session_id: resolvedSession ?? null,
              created_at: timestamp,
              finished_at: timestamp,
              duration_seconds: Number.isFinite(duration)
                ? Math.round((duration / 1000) * 100) / 100
                : null,
              steps: steps && steps.length > 0 ? steps : undefined,
            },
          }));
          try {
            await ingestMemoryEntry({
              text: buffer,
              category: "assistant",
              sessionId: resolvedSession ?? null,
              userId: "user_default",
              pinned: true,
              memoryType: "fact",
              scope: "session",
              timestamp,
            });
          } catch (err) {
            console.warn(
              "Nie udało się zapisać pamięci dla trybu prostego:",
              err,
            );
          }
          if (Number.isFinite(duration)) {
            setLastResponseDurationMs(duration);
            setResponseDurations((prev) => [...prev, duration].slice(-10));
          }
          window.setTimeout(() => {
            dropOptimisticRequest(clientId);
            clearSimpleStream(clientId);
          }, 200);
        } catch (err) {
          updateSimpleStream(clientId, {
            text: err instanceof Error ? err.message : "Błąd trybu prostego.",
            status: "FAILED",
            done: true,
          });
          dropOptimisticRequest(clientId);
          setMessage(
            err instanceof Error ? err.message : "Nie udało się wysłać zadania",
          );
          setLocalSessionHistory((prev) => {
            const next = [...prev];
            const exists = next.some(
              (entry) =>
                entry.request_id === clientId && entry.role === "assistant",
            );
            if (!exists) {
              next.push({
                role: "assistant",
                content:
                  err instanceof Error ? err.message : "Błąd trybu prostego.",
                request_id: clientId,
                timestamp: new Date().toISOString(),
                session_id: resolvedSession ?? undefined,
              });
            }
            return next;
          });
        } finally {
          setSending(false);
        }
        return;
      }
      try {
        const res = await sendTask(
          trimmed,
          !labMode,
          generationParams,
          {
            configHash: runtimeOverride?.configHash ?? activeServerInfo?.config_hash ?? null,
            runtimeId: runtimeOverride?.runtimeId ?? activeServerInfo?.runtime_id ?? null,
          },
          null,
          {
            tool: parsed.forcedTool,
            provider: parsed.forcedProvider,
          },
          forcedIntent,
          language as ("pl" | "en" | "de" | null),
          resolvedSession,
          "session",
        );
        const resolvedId = res.task_id ?? null;
        linkOptimisticRequest(clientId, resolvedId);

        // Reconcile user message ID in local history to avoid duplication
        if (resolvedId) {
          setLocalSessionHistory((prev) => {
            return prev.map(entry => {
              if (entry.request_id === clientId && entry.role === 'user') {
                return { ...entry, request_id: resolvedId };
              }
              return entry;
            });
          });
        }

        const displayId = resolvedId ?? t("cockpit.chatMessages.taskPendingId");
        setMessage(t("cockpit.chatMessages.taskSent", { id: displayId }));
        await Promise.all([
          refreshTasks(),
          refreshQueue(),
          refreshHistory(),
          refreshSessionHistory(),
        ]);
      } catch (err) {
        dropOptimisticRequest(clientId);
        setMessage(
          err instanceof Error ? err.message : t("cockpit.chatMessages.taskSendError"),
        );
      } finally {
        setSending(false);
      }
    })();
    return true;
  }, [
    activeServerInfo?.active_endpoint,
    activeServerInfo?.active_model,
    activeServerInfo?.active_server,
    activeServerInfo?.config_hash,
    activeServerInfo?.runtime_id,
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
    uiTimingsRef,
    updateSimpleStream,
  ]);
}

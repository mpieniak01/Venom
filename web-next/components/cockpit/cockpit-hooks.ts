"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { LogEntryType } from "@/lib/logs";
import type { ServiceStatus, Task, ContextUsed } from "@/lib/types";
import type { TokenSample } from "@/components/cockpit/token-types";
import {
  isTelemetryEventPayload,
  MACRO_STORAGE_KEY,
  mapTelemetryTone,
  normalizeMatchValue,
  type MacroAction,
  type TelemetryFeedEntry,
  type TelemetryEventPayload,
} from "@/components/cockpit/cockpit-utils";
import type { HiddenPromptEntry } from "@/lib/types";
import type { SendTaskInput } from "@/hooks/use-api";

const MAX_SESSION_HISTORY_ENTRIES = 500;

type ModelsPayload = {
  providers?: Record<string, Array<{ name?: string; provider?: string | null }>>;
  models?: Array<{ name?: string; provider?: string | null }>;
} | null;

type ActiveServerInfo = {
  active_model?: string | null;
  active_server?: string | null;
} | null;

export function useLlmServerSelectionData({
  llmServers,
  models,
  selectedLlmServer,
  activeServerInfo,
}: {
  llmServers: Array<{ name: string; display_name: string; status?: string | null }>;
  models: ModelsPayload;
  selectedLlmServer: string;
  activeServerInfo: ActiveServerInfo;
}) {
  const selectedServerEntry = useMemo(
    () => llmServers.find((server) => server.name === selectedLlmServer) ?? null,
    [llmServers, selectedLlmServer],
  );
  const availableModelsForServer = useMemo(() => {
    if (!models || !selectedLlmServer) return [];
    const normalProvider = (value?: string | null) => {
      if (!value) return "";
      return value.toLowerCase();
    };
    const inferProvider = (name?: string | null) => {
      if (!name) return null;
      return name.includes(":") ? "ollama" : "vllm";
    };
    let base =
      models.providers && selectedLlmServer in models.providers
        ? models.providers[selectedLlmServer] ?? []
        : (models.models ?? []).filter(
          (model) => normalProvider(model.provider) === selectedLlmServer,
        );
    base = base.filter((model) => normalProvider(model.provider) !== "onnx");
    if (activeServerInfo?.active_model) {
      const inferred = inferProvider(activeServerInfo.active_model);
      if (inferred === selectedLlmServer) {
        const hasActive = base.some((model) => model.name === activeServerInfo.active_model);
        if (!hasActive) {
          base = [...base, { name: activeServerInfo.active_model, provider: selectedLlmServer }];
        }
      }
    }
    return base;
  }, [models, selectedLlmServer, activeServerInfo?.active_model]);
  const llmServerOptions = useMemo(
    () =>
      llmServers.map((server) => ({
        value: server.name,
        label: server.display_name,
      })),
    [llmServers],
  );
  const llmModelOptions = useMemo(
    () =>
      availableModelsForServer.map((model) => ({
        value: model.name ?? "",
        label: model.name ?? "",
      })),
    [availableModelsForServer],
  );

  return {
    selectedServerEntry,
    availableModelsForServer,
    llmServerOptions,
    llmModelOptions,
  };
}

export function useServiceStatusMap(services: ServiceStatus[] | null | undefined) {
  return useMemo(() => {
    const map = new Map<string, ServiceStatus>();
    (services || []).forEach((svc) => {
      if (svc?.name) {
        map.set(svc.name.toLowerCase(), svc);
      }
    });
    return map;
  }, [services]);
}

export function useTasksIndex(tasks: Task[] | null | undefined) {
  const tasksByPrompt = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      if (task.content) {
        bucket.set(task.content.trim(), task);
      }
    });
    return bucket;
  }, [tasks]);
  const tasksById = useMemo(() => {
    const bucket = new Map<string, Task>();
    (tasks || []).forEach((task) => {
      const key = task.task_id || task.id;
      if (key) {
        bucket.set(key, task);
      }
    });
    return bucket;
  }, [tasks]);

  return { tasksByPrompt, tasksById };
}

export function useTelemetryFeedEntries(entries: LogEntryType[]) {
  return useMemo<TelemetryFeedEntry[]>(() => {
    return entries
      .filter((entry) => isTelemetryEventPayload(entry.payload) && entry.payload.type)
      .slice(0, 12)
      .map((entry) => {
        const payload = entry.payload as TelemetryEventPayload;
        return {
          id: entry.id,
          type: payload.type ?? "SYSTEM_LOG",
          message:
            payload.message ||
            (typeof payload.data?.message === "string"
              ? payload.data?.message
              : "Zdarzenie telemetryczne"),
          timestamp: new Date(entry.ts).toLocaleTimeString(),
          tone: mapTelemetryTone(payload.type ?? "SYSTEM_LOG"),
        };
      });
  }, [entries]);
}

export function useHistorySummary(history: Array<{ status?: string | null }> | null | undefined) {
  return useMemo(() => {
    const bucket: Record<string, number> = {};
    (history || []).forEach((item) => {
      const key = item.status || "UNKNOWN";
      bucket[key] = (bucket[key] || 0) + 1;
    });
    return Object.entries(bucket)
      .map(([name, value]) => ({ name, value }))
      .sort((a, b) => b.value - a.value);
  }, [history]);
}

export function useTokenMetricsSummary({
  tokenMetrics,
  tokenHistory,
}: {
  tokenMetrics: { total_tokens?: number; prompt_tokens?: number; completion_tokens?: number; cached_tokens?: number } | null;
  tokenHistory: TokenSample[];
}) {
  const tokenSplits = useMemo(
    () =>
      [
        { label: "Prompt", value: tokenMetrics?.prompt_tokens ?? 0 },
        { label: "Completion", value: tokenMetrics?.completion_tokens ?? 0 },
        { label: "Cached", value: tokenMetrics?.cached_tokens ?? 0 },
      ].filter((item) => item.value && item.value > 0),
    [tokenMetrics?.prompt_tokens, tokenMetrics?.completion_tokens, tokenMetrics?.cached_tokens],
  );
  const totalTokens = tokenMetrics?.total_tokens ?? 0;
  const promptTokens = tokenMetrics?.prompt_tokens ?? 0;
  const completionTokens = tokenMetrics?.completion_tokens ?? 0;
  const cachedTokens = tokenMetrics?.cached_tokens ?? 0;
  const lastTokenSample =
    tokenHistory.length > 0 ? tokenHistory.at(-1)?.value ?? null : null;
  const prevTokenSample =
    tokenHistory.length > 1 ? tokenHistory.at(-2)?.value ?? null : null;
  const tokenTrendDelta =
    lastTokenSample !== null && prevTokenSample !== null
      ? lastTokenSample - prevTokenSample
      : null;
  const tokenTrendLabel = (() => {
    if (tokenTrendDelta === null) return "Stabilny";
    if (tokenTrendDelta > 0) return `+${tokenTrendDelta.toLocaleString("pl-PL")}↑`;
    return `${tokenTrendDelta.toLocaleString("pl-PL")}↓`;
  })();

  return {
    tokenSplits,
    totalTokens,
    promptTokens,
    completionTokens,
    cachedTokens,
    tokenTrendDelta,
    tokenTrendLabel,
  };
}

export type SessionHistoryEntry = {
  role?: string;
  content?: string;
  session_id?: string;
  request_id?: string;
  timestamp?: string;
  pending?: boolean;
  status?: string | null;
  contextUsed?: ContextUsed | null;
};

type SessionHistoryHookArgs = {
  sessionId: string | null;
  sessionHistoryData?: { history?: SessionHistoryEntry[] } | null;
  refreshSessionHistory: () => void;
  refreshHistory: () => void;
};

export const sessionEntryKey = (entry: SessionHistoryEntry) => {
  const role = entry.role ?? "user";
  const requestId = entry.request_id ?? "no-request";
  if (requestId !== "no-request") {
    return `${requestId}:${role}`;
  }
  const content = entry.content ?? "";
  return `no-request:${role}:${content}`;
};

export function useSessionHistoryState({
  sessionId,
  sessionHistoryData,
  refreshSessionHistory,
  refreshHistory,
}: SessionHistoryHookArgs) {
  const sessionHistory = useMemo(
    () => sessionHistoryData?.history ?? [],
    [sessionHistoryData],
  );
  const [localSessionHistory, setLocalSessionHistory] = useState<SessionHistoryEntry[]>([]);
  const lastSessionIdRef = useRef<string | null>(null);
  const initializedStorageKeyRef = useRef<string | null>(null);
  const [bootId, setBootId] = useState<string | null>(null);
  const sessionHistoryStorageKey =
    sessionId && bootId ? `venom-session-history:${sessionId}:${bootId}` : null;

  useEffect(() => {
    if (typeof globalThis.window === "undefined") return;
    try {
      const storedBootId = globalThis.window.localStorage.getItem("venom-backend-boot-id");
      setBootId(storedBootId);
    } catch {
      setBootId(null);
    }
  }, [sessionId]);

  // The effect clearing history on bootId was removed to preserve continuity during navigation.
  // Loading from cache is handled by the effect below, which reacts to sessionHistoryStorageKey.

  useEffect(() => {
    if (!sessionId) return;
    const initKey = sessionHistoryStorageKey ?? `session:${sessionId}`;
    if (initializedStorageKeyRef.current === initKey) return;
    initializedStorageKeyRef.current = initKey;
    if (lastSessionIdRef.current && lastSessionIdRef.current !== sessionId) {
      setLocalSessionHistory([]);
    }
    lastSessionIdRef.current = sessionId;
    if (sessionHistoryStorageKey) {
      try {
        const cached = globalThis.window.sessionStorage.getItem(sessionHistoryStorageKey);
        if (cached) {
          const parsed = JSON.parse(cached) as SessionHistoryEntry[];
          if (Array.isArray(parsed) && parsed.length > 0) {
            const normalized = parsed.slice(-MAX_SESSION_HISTORY_ENTRIES);
            setLocalSessionHistory((prev) => {
              const prevKey = prev.map(sessionEntryKey).join("|");
              const nextKey = normalized.map(sessionEntryKey).join("|");
              return prevKey === nextKey ? prev : normalized;
            });
          }
        }
      } catch {
        // ignore cache errors
      }
    }
    refreshSessionHistory();
    refreshHistory();
  }, [sessionId, refreshSessionHistory, refreshHistory, sessionHistoryStorageKey]);

  useEffect(() => {
    if (!sessionId) return;
    if (!sessionHistory.length) return;
    setLocalSessionHistory((prev) => {
      if (prev.length === 0) return sessionHistory.slice(-MAX_SESSION_HISTORY_ENTRIES);
      const keys = new Set(prev.map(sessionEntryKey));
      const merged = [...prev];
      sessionHistory.forEach((entry) => {
        const key = sessionEntryKey(entry);
        if (!keys.has(key)) {
          keys.add(key);
          merged.push(entry);
        }
      });
      return merged.slice(-MAX_SESSION_HISTORY_ENTRIES);
    });
  }, [sessionHistory, sessionId]);

  useEffect(() => {
    if (!sessionHistoryStorageKey) return;
    if (localSessionHistory.length === 0) return;
    try {
      const snapshot = localSessionHistory.slice(-200);
      globalThis.window.sessionStorage.setItem(
        sessionHistoryStorageKey,
        JSON.stringify(snapshot),
      );
    } catch {
      // ignore cache errors
    }
  }, [localSessionHistory, sessionHistoryStorageKey]);

  return {
    sessionHistory,
    localSessionHistory,
    setLocalSessionHistory,
    sessionEntryKey,
  };
}

type HiddenPromptStateArgs = {
  hiddenPrompts?: { items?: HiddenPromptEntry[] } | null;
  activeHiddenPrompts?: { items?: HiddenPromptEntry[] } | null;
  hiddenIntentFilter: string;
};

export function useHiddenPromptState({
  hiddenPrompts,
  activeHiddenPrompts,
  hiddenIntentFilter,
}: HiddenPromptStateArgs) {
  const activeHiddenKeys = useMemo(() => {
    const keys = new Set<string>();
    activeHiddenPrompts?.items?.forEach((entry) => {
      const key = entry.prompt_hash ?? entry.prompt;
      if (key) keys.add(key);
    });
    return keys;
  }, [activeHiddenPrompts]);

  const activeHiddenMap = useMemo(() => {
    const map = new Map<string, HiddenPromptEntry>();
    activeHiddenPrompts?.items?.forEach((entry) => {
      const key = entry.prompt_hash ?? entry.prompt;
      if (key) map.set(key, entry);
    });
    return map;
  }, [activeHiddenPrompts]);

  const hiddenResponseCandidates = useMemo(
    () =>
      (activeHiddenPrompts?.items ?? [])
        .map((entry) => entry.approved_response ?? "")
        .map(normalizeMatchValue)
        .filter(Boolean),
    [activeHiddenPrompts],
  );

  const isHiddenResponse = useCallback(
    (text: string) => {
      if (!text) return false;
      const normalized = normalizeMatchValue(text);
      if (!normalized) return false;
      return hiddenResponseCandidates.some(
        (candidate) =>
          candidate.length > 0 &&
          (normalized.includes(candidate) || candidate.includes(normalized)),
      );
    },
    [hiddenResponseCandidates],
  );

  const hiddenIntentOptions = useMemo(() => {
    const intents = new Set<string>();
    hiddenPrompts?.items?.forEach((entry) => {
      if (entry.intent) intents.add(entry.intent);
    });
    return ["all", ...Array.from(intents).sort((a, b) => a.localeCompare(b))];
  }, [hiddenPrompts]);

  const selectableHiddenPrompts = useMemo(() => {
    if (!hiddenPrompts?.items?.length || hiddenIntentFilter === "all") return [];
    return hiddenPrompts.items.filter(
      (entry) => entry.intent && entry.intent === hiddenIntentFilter,
    );
  }, [hiddenPrompts, hiddenIntentFilter]);

  const activeForIntent = useMemo(() => {
    if (!activeHiddenPrompts?.items?.length || hiddenIntentFilter === "all") return null;
    return activeHiddenPrompts.items.find(
      (entry) => entry.intent === hiddenIntentFilter,
    );
  }, [activeHiddenPrompts, hiddenIntentFilter]);

  return {
    activeHiddenKeys,
    activeHiddenMap,
    hiddenIntentOptions,
    selectableHiddenPrompts,
    activeForIntent,
    isHiddenResponse,
  };
}

type OptimisticRequestLike = { requestId?: string | null };
type HistoryRequestLike = { request_id: string; status?: string | null };

export function useTrackedRequestIds({
  optimisticRequests,
  history,
  selectedRequestId,
}: {
  optimisticRequests: OptimisticRequestLike[];
  history: HistoryRequestLike[] | null;
  selectedRequestId: string | null;
}) {
  return useMemo(() => {
    const ids = new Set<string>();
    optimisticRequests.forEach((entry) => {
      if (entry.requestId) ids.add(entry.requestId);
    });
    (history ?? [])
      .filter((item) => item.status === "PENDING" || item.status === "PROCESSING")
      .forEach((item) => ids.add(item.request_id));
    if (selectedRequestId) ids.add(selectedRequestId);
    return Array.from(ids);
  }, [optimisticRequests, history, selectedRequestId]);
}

type MacroRunContext = {
  enqueueOptimisticRequest: (prompt: string) => string;
  linkOptimisticRequest: (clientId: string, requestId: string | null) => void;
  dropOptimisticRequest: (clientId: string) => void;
  sendTask: (payload: SendTaskInput) => Promise<{ task_id?: string | null }>;
  refreshTasks: () => Promise<unknown>;
  refreshQueue: () => Promise<unknown>;
  refreshHistory: () => Promise<unknown>;
  labMode: boolean;
  activeConfigHash?: string | null;
  activeRuntimeId?: string | null;
  language: string;
  sessionId: string | null;
  setMessage: (message: string | null) => void;
};

export function useMacroActions({
  enqueueOptimisticRequest,
  linkOptimisticRequest,
  dropOptimisticRequest,
  sendTask,
  refreshTasks,
  refreshQueue,
  refreshHistory,
  labMode,
  activeConfigHash,
  activeRuntimeId,
  language,
  sessionId,
  setMessage,
}: MacroRunContext) {
  const [macroSending, setMacroSending] = useState<string | null>(null);
  const [customMacros, setCustomMacros] = useState<MacroAction[]>([]);
  const [newMacro, setNewMacro] = useState({
    label: "",
    description: "",
    content: "",
  });

  useEffect(() => {
    const raw = globalThis.window.localStorage.getItem(MACRO_STORAGE_KEY);
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as MacroAction[];
      if (Array.isArray(parsed)) {
        setCustomMacros(parsed);
      }
    } catch {
      // Ignore malformed storage
    }
  }, []);

  useEffect(() => {
    globalThis.window.localStorage.setItem(MACRO_STORAGE_KEY, JSON.stringify(customMacros));
  }, [customMacros]);

  const macroActions = useMemo<MacroAction[]>(
    () => [
      {
        id: "graph-scan",
        label: "Skanuj graf wiedzy",
        description: "Wywołaj /api/v1/graph/scan i odśwież podgląd Brain.",
        content: "Przeskanuj repozytorium i zaktualizuj graf wiedzy.",
      },
      {
        id: "system-health",
        label: "Status usług",
        description: "Sprawdź /api/v1/system/services i zgłoś anomalie.",
        content:
          "Zbadaj kondycję wszystkich usług Venoma i przygotuj raport o stanie wraz z rekomendacjami.",
      },
      {
        id: "roadmap-sync",
        label: "Roadmap sync",
        description: "Poproś Strategy agenta o aktualizację roadmapy.",
        content:
          "Uzgodnij bieżące zadania z roadmapą i wypisz brakujące milestone'y wraz z datami.",
      },
      {
        id: "git-audit",
        label: "Git audit",
        description: "Analiza repo: zmiany, konflikty, propozycje commitów.",
        content:
          "Przeanalizuj repozytorium git, wypisz niezatwierdzone zmiany i zaproponuj strukturę commitów.",
      },
    ],
    [],
  );

  const allMacros = useMemo(
    () => [...macroActions, ...customMacros],
    [macroActions, customMacros],
  );

  const handleMacroRun = useCallback(
    async (macro: { id: string; content: string; label: string }) => {
      if (macroSending) return;
      setMacroSending(macro.id);
      setMessage(null);
      const clientId = enqueueOptimisticRequest(macro.content);
      try {
        const res = await sendTask({
          content: macro.content,
          storeKnowledge: !labMode,
          generationParams: null,
          runtimeMeta: {
            configHash: activeConfigHash ?? null,
            runtimeId: activeRuntimeId ?? null,
          },
          extraContext: null,
          forcedRoute: null,
          forcedIntent: null,
          preferredLanguage: language as ("pl" | "en" | "de" | null),
          sessionId,
          preferenceScope: "session",
        });
        linkOptimisticRequest(clientId, res.task_id ?? null);
        setMessage(`Makro ${macro.label} wysłane: ${res.task_id ?? "w toku…"}`);
        await Promise.all([refreshTasks(), refreshQueue(), refreshHistory()]);
      } catch (err) {
        dropOptimisticRequest(clientId);
        setMessage(err instanceof Error ? err.message : "Nie udało się wykonać makra.");
      } finally {
        setMacroSending(null);
      }
    },
    [
      activeConfigHash,
      activeRuntimeId,
      dropOptimisticRequest,
      enqueueOptimisticRequest,
      labMode,
      language,
      linkOptimisticRequest,
      macroSending,
      refreshHistory,
      refreshQueue,
      refreshTasks,
      sendTask,
      sessionId,
      setMessage,
    ],
  );

  return {
    macroSending,
    customMacros,
    setCustomMacros,
    newMacro,
    setNewMacro,
    allMacros,
    handleMacroRun,
  };
}

type QueueSnapshot = {
  paused?: boolean | null;
} | null;

type QueueActionsParams = {
  queue: QueueSnapshot;
  refreshQueue: () => void;
  refreshTasks: () => void;
  toggleQueue: (paused: boolean) => Promise<unknown>;
  purgeQueue: () => Promise<{ removed?: number }>;
  emergencyStop: () => Promise<{ cancelled?: number; purged?: number }>;
};

export function useQueueActions({
  queue,
  refreshQueue,
  refreshTasks,
  toggleQueue,
  purgeQueue,
  emergencyStop,
}: QueueActionsParams) {
  const [queueAction, setQueueAction] = useState<null | "pause" | "resume" | "purge" | "emergency">(
    null,
  );
  const [queueActionMessage, setQueueActionMessage] = useState<string | null>(null);

  const handleToggleQueue = useCallback(async () => {
    if (!queue) return;
    const action = queue.paused ? "resume" : "pause";
    if (queueAction) return;
    setQueueAction(action);
    setQueueActionMessage(null);
    try {
      await toggleQueue(action === "pause");
      setQueueActionMessage(
        action === "pause"
          ? "Kolejka wstrzymana."
          : "Kolejka wznowiona.",
      );
      refreshQueue();
      refreshTasks();
    } catch (err) {
      setQueueActionMessage(
        err instanceof Error
          ? err.message
          : "Nie udało się zmienić stanu kolejki.",
      );
    } finally {
      setQueueAction(null);
    }
  }, [queue, queueAction, refreshQueue, refreshTasks, toggleQueue]);

  const executeQueueMutation = useCallback(
    async (type: "purge" | "emergency") => {
      if (queueAction) return;
      setQueueAction(type);
      setQueueActionMessage(null);
      try {
        if (type === "purge") {
          const res = await purgeQueue();
          setQueueActionMessage(`Wyczyszczono kolejkę (${res.removed} zadań).`);
        } else {
          const res = await emergencyStop();
          setQueueActionMessage(
            `Zatrzymano zadania: cancelled ${res.cancelled}, purged ${res.purged}.`,
          );
        }
        refreshQueue();
        refreshTasks();
      } catch (err) {
        setQueueActionMessage(
          err instanceof Error
            ? err.message
            : "Nie udało się wykonać akcji na kolejce.",
        );
      } finally {
        setQueueAction(null);
      }
    },
    [
      emergencyStop,
      purgeQueue,
      queueAction,
      refreshQueue,
      refreshTasks,
    ],
  );

  return {
    queueAction,
    queueActionMessage,
    handleToggleQueue,
    executeQueueMutation,
  };
}

"use client";

import { useCallback, useRef, useState } from "react";

export type OptimisticRequestState = {
  clientId: string;
  requestId: string | null;
  prompt: string;
  createdAt: string;
  startedAt: number;
  confirmed: boolean;
  forcedTool?: string | null;
  forcedProvider?: string | null;
  forcedIntent?: string | null;
  simpleMode?: boolean;
  chatMode?: "normal" | "direct" | "complex";
};

type UiTimingEntry = {
  historyMs?: number;
  ttftMs?: number;
};

export type SimpleStreamState = Record<string, { text: string; status: string; done: boolean }>;

type UiTimingState = { t0: number; historyMs?: number; ttftMs?: number };
type HistoryItem = {
  request_id: string;
  status?: string | null;
  finished_at?: string | null;
  created_at?: string | null;
};

function mapLinkedOptimisticRequest(
  entries: OptimisticRequestState[],
  clientId: string,
  requestId: string | null,
): OptimisticRequestState[] {
  return entries.map((entry) =>
    entry.clientId === clientId
      ? {
          ...entry,
          requestId: requestId ?? entry.requestId ?? entry.clientId,
          confirmed: true,
        }
      : entry,
  );
}

function buildSimpleStreamUpdate(
  prev: SimpleStreamState,
  clientId: string,
  mappedId: string | undefined,
  patch: { text?: string; status?: string; done?: boolean },
): SimpleStreamState {
  const existing = prev[clientId] ?? { text: "", status: "W toku", done: false };
  const mappedExisting =
    mappedId && mappedId !== clientId
      ? prev[mappedId] ?? { text: "", status: "W toku", done: false }
      : null;
  const next: SimpleStreamState = {
    ...prev,
    [clientId]: {
      ...existing,
      ...patch,
    },
  };
  if (mappedId && mappedId !== clientId) {
    next[mappedId] = {
      text: patch.text ?? mappedExisting?.text ?? "",
      status: patch.status ?? mappedExisting?.status ?? "W toku",
      done: patch.done ?? mappedExisting?.done ?? false,
    };
  }
  return next;
}

function pruneCompletedRequests(
  entries: OptimisticRequestState[],
  history: HistoryItem[],
): { next: OptimisticRequestState[]; latestDuration: number | null; changed: boolean } {
  let changed = false;
  let latestDuration: number | null = null;
  const next = entries.filter((entry) => {
    if (!entry.requestId) return true;
    const match = history.find((item) => item.request_id === entry.requestId);
    const isFinished =
      !!match?.status &&
      (match.status === "COMPLETED" || match.status === "FAILED" || match.status === "LOST");
    if (!isFinished) return true;
    changed = true;
    const finishTs = match.finished_at ?? match.created_at ?? entry.createdAt;
    if (finishTs) {
      const duration = new Date(finishTs).getTime() - entry.startedAt;
      if (Number.isFinite(duration)) latestDuration = duration;
    }
    return false;
  });
  return { next, latestDuration, changed };
}

export function useOptimisticRequests<TDetail = unknown>(
  chatMode?: OptimisticRequestState["chatMode"],
) {
  const [optimisticRequests, setOptimisticRequests] = useState<OptimisticRequestState[]>([]);
  const [simpleStreams, setSimpleStreams] = useState<SimpleStreamState>({});
  const [simpleRequestDetails, setSimpleRequestDetails] = useState<Record<string, TDetail>>({});
  const uiTimingsRef = useRef<Map<string, UiTimingState>>(
    new Map(),
  );
  const uiTimingKeyMapRef = useRef<Map<string, string>>(new Map());
  const [uiTimingsByRequest, setUiTimingsByRequest] = useState<Record<string, UiTimingEntry>>({});

  const enqueueOptimisticRequest = useCallback(
    (
      prompt: string,
      forced?: {
        tool?: string;
        provider?: string;
        intent?: string;
        simpleMode?: boolean;
      },
    ) => {
      const entry: OptimisticRequestState = {
        clientId: createOptimisticId(),
        requestId: null,
        prompt,
        createdAt: new Date().toISOString(),
        startedAt: Date.now(),
        confirmed: false,
        forcedTool: forced?.tool ?? null,
        forcedProvider: forced?.provider ?? null,
        forcedIntent: forced?.intent ?? null,
        simpleMode: forced?.simpleMode ?? false,
        chatMode,
      };
      setOptimisticRequests((prev) => [...prev, entry]);
      uiTimingsRef.current.set(entry.clientId, { t0: entry.startedAt });
      return entry.clientId;
    },
    [chatMode],
  );

  const linkOptimisticRequest = useCallback((clientId: string, requestId: string | null) => {
    if (!clientId) return;
    setOptimisticRequests((prev) => mapLinkedOptimisticRequest(prev, clientId, requestId));
    if (requestId) {
      const existing = uiTimingsRef.current.get(clientId);
      if (existing) {
        uiTimingsRef.current.delete(clientId);
        uiTimingsRef.current.set(requestId, existing);
        uiTimingKeyMapRef.current.set(clientId, requestId);
        setUiTimingsByRequest((prev) => ({
          ...prev,
          [requestId]: {
            historyMs: existing.historyMs,
            ttftMs: existing.ttftMs,
          },
        }));
      } else {
        uiTimingKeyMapRef.current.set(clientId, requestId);
      }
    }
  }, []);

  const dropOptimisticRequest = useCallback((clientId: string) => {
    if (!clientId) return;
    setOptimisticRequests((prev) => prev.filter((entry) => entry.clientId !== clientId));
    const mapped = uiTimingKeyMapRef.current.get(clientId);
    uiTimingKeyMapRef.current.delete(clientId);
    if (mapped) {
      uiTimingsRef.current.delete(mapped);
      setUiTimingsByRequest((prev) => {
        const next = { ...prev };
        delete next[mapped];
        return next;
      });
    } else {
      uiTimingsRef.current.delete(clientId);
    }
  }, []);

  const updateSimpleStream = useCallback(
    (clientId: string, patch: { text?: string; status?: string; done?: boolean }) => {
      setSimpleStreams((prev) =>
        buildSimpleStreamUpdate(prev, clientId, uiTimingKeyMapRef.current.get(clientId), patch),
      );
    },
    [],
  );

  const recordUiTiming = useCallback((key: string, patch: UiTimingEntry) => {
    const mapped = uiTimingKeyMapRef.current.get(key);
    const targetKey = mapped ?? key;
    const current = uiTimingsRef.current.get(targetKey) ?? uiTimingsRef.current.get(key);
    if (!current) return;
    const next = { ...current, ...patch };
    uiTimingsRef.current.set(targetKey, next);
    setUiTimingsByRequest((prev) => ({
      ...prev,
      [targetKey]: {
        historyMs: next.historyMs,
        ttftMs: next.ttftMs,
      },
    }));
  }, []);

  const clearSimpleStream = useCallback((clientId: string) => {
    setSimpleStreams((prev) => {
      const next = { ...prev };
      delete next[clientId];
      return next;
    });
  }, []);

  const resetOptimisticState = useCallback(() => {
    setOptimisticRequests([]);
    setSimpleStreams({});
    setSimpleRequestDetails({});
    uiTimingsRef.current.clear();
    uiTimingKeyMapRef.current.clear();
    setUiTimingsByRequest({});
  }, []);

  const pruneOptimisticRequests = useCallback(
    (
      history: HistoryItem[] | null,
      onDuration?: (duration: number) => void,
    ) => {
      if (!history || history.length === 0) return;
      let latestDuration: number | null = null;
      setOptimisticRequests((prev) => {
        if (prev.length === 0) return prev;
        const pruned = pruneCompletedRequests(prev, history);
        latestDuration = pruned.latestDuration;
        return pruned.changed ? pruned.next : prev;
      });
      if (latestDuration !== null && onDuration) {
        onDuration(latestDuration);
      }
    },
    [],
  );

  return {
    optimisticRequests,
    simpleStreams,
    simpleRequestDetails,
    setSimpleRequestDetails,
    uiTimingsByRequest,
    uiTimingsRef,
    uiTimingKeyMapRef,
    enqueueOptimisticRequest,
    linkOptimisticRequest,
    dropOptimisticRequest,
    updateSimpleStream,
    recordUiTiming,
    clearSimpleStream,
    pruneOptimisticRequests,
    resetOptimisticState,
  };
}

let optimisticIdFallbackCounter = 0;

function createOptimisticId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    const randomPart = crypto.randomUUID().replaceAll("-", "").slice(0, 4);
    return `opt-${Date.now().toString(36)}-${randomPart}`;
  }
  optimisticIdFallbackCounter += 1;
  const randomPart =
    optimisticIdFallbackCounter.toString(36) + Date.now().toString(36).slice(-2);
  return `opt-${Date.now().toString(36)}-${randomPart}`;
}

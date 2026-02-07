"use client";

import type { SessionHistoryEntry } from "@/components/cockpit/cockpit-hooks";
import type { HistoryRequest, Task } from "@/lib/types";

type MergeArgs = {
  sessionHistory: SessionHistoryEntry[];
  localSessionHistory: SessionHistoryEntry[];
  historyRequests: HistoryRequest[] | null | undefined;
  tasks: Task[] | null | undefined;
  sessionId: string | null;
  sessionEntryKey: (entry: SessionHistoryEntry) => string;
};

export function mergeHistoryFallbacks({
  sessionHistory,
  localSessionHistory,
  historyRequests,
  tasks,
  sessionId,
  sessionEntryKey,
}: MergeArgs): SessionHistoryEntry[] {
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
        return;
      }

      const existingTimestamp = existing.timestamp ?? entry.timestamp;
      const existingContentLength = existing.content?.length ?? 0;
      const nextContentLength = entry.content?.length ?? 0;
      const shouldUpdateContent = nextContentLength > existingContentLength;

      if (shouldUpdateContent) {
        seenMap.set(key, {
          ...existing,
          ...entry,
          timestamp: existingTimestamp,
        });
      } else if (!existing.timestamp && entry.timestamp) {
        seenMap.set(key, { ...existing, timestamp: entry.timestamp });
      }
    });
    deduped = Array.from(seenMap.values());
  }

  const historyPromptIndex = new Map<
    string,
    { prompt: string; created_at?: string | null; session_id?: string | null }
  >();
  (historyRequests ?? []).forEach((entry) => {
    if (!entry?.request_id || !entry.prompt) return;
    if (sessionId) {
      if (!entry.session_id || entry.session_id !== sessionId) {
        return;
      }
    }
    historyPromptIndex.set(entry.request_id, {
      prompt: entry.prompt,
      created_at: entry.created_at ?? null,
      session_id: entry.session_id ?? null,
    });
  });

  const taskResultIndex = new Map<
    string,
    {
      result?: string | null;
      status?: string | null;
      updated_at?: string | null;
      created_at?: string | null;
      session_id?: string | null;
    }
  >();
  (tasks ?? []).forEach((task) => {
    const taskId = task.task_id ?? task.id;
    if (!taskId) return;
    let taskSession: string | null = null;
    const ctx = task.context_history as Record<string, unknown> | null | undefined;
    if (ctx && typeof ctx === "object") {
      const session = (ctx as { session?: { session_id?: string } }).session;
      if (session?.session_id) {
        taskSession = session.session_id;
      }
    }
    if (sessionId) {
      if (!taskSession || taskSession !== sessionId) {
        return;
      }
    }
    taskResultIndex.set(String(taskId), {
      result: task.result ?? null,
      status: task.status ?? null,
      updated_at: task.updated_at ?? null,
      created_at: task.created_at ?? null,
      session_id: taskSession ?? null,
    });
  });

  if (historyPromptIndex.size > 0) {
    const hasUser = new Set(
      deduped
        .filter((entry) => entry.request_id && entry.role === "user")
        .map((entry) => String(entry.request_id)),
    );
    deduped = deduped.map((entry) => {
      if (entry.role !== "user" || !entry.request_id) return entry;
      if ((entry.content ?? "").trim()) return entry;
      const fallback = historyPromptIndex.get(String(entry.request_id));
      if (!fallback?.prompt) return entry;
      return {
        ...entry,
        content: fallback.prompt,
        timestamp: entry.timestamp || fallback.created_at || entry.timestamp,
        session_id: entry.session_id || fallback.session_id || entry.session_id,
      };
    });
    historyPromptIndex.forEach((fallback, requestId) => {
      if (hasUser.has(requestId)) return;
      deduped.push({
        role: "user",
        content: fallback.prompt,
        request_id: requestId,
        timestamp: fallback.created_at ?? undefined,
        session_id: fallback.session_id ?? undefined,
      });
    });
  }

  if (taskResultIndex.size > 0) {
    const hasAssistant = new Set(
      deduped
        .filter((entry) => entry.request_id && entry.role === "assistant")
        .map((entry) => String(entry.request_id)),
    );
    deduped = deduped.map((entry) => {
      if (entry.role !== "assistant" || !entry.request_id) return entry;
      if ((entry.content ?? "").trim()) return entry;
      const fallback = taskResultIndex.get(String(entry.request_id));
      if (!fallback?.result) return entry;
      return {
        ...entry,
        content: fallback.result,
        timestamp:
          entry.timestamp ||
          fallback.updated_at ||
          fallback.created_at ||
          entry.timestamp,
        session_id: entry.session_id || fallback.session_id || entry.session_id,
        status: entry.status || fallback.status || entry.status,
      };
    });
    taskResultIndex.forEach((fallback, requestId) => {
      if (hasAssistant.has(requestId)) return;
      if (!fallback.result) return;
      deduped.push({
        role: "assistant",
        content: fallback.result,
        request_id: requestId,
        timestamp: fallback.updated_at ?? fallback.created_at ?? undefined,
        session_id: fallback.session_id ?? undefined,
        status: fallback.status ?? undefined,
      });
    });
  }

  return deduped;
}

export function filterHistoryAfterReset(
  entries: SessionHistoryEntry[],
  resetAtIso: string | null,
): SessionHistoryEntry[] {
  if (!resetAtIso) return entries;
  const resetAt = new Date(resetAtIso).getTime();
  if (!Number.isFinite(resetAt)) return entries;
  return entries.filter((entry) => {
    const ts = entry.timestamp ? new Date(entry.timestamp).getTime() : Number.NaN;
    if (!Number.isFinite(ts)) return false;
    return ts >= resetAt;
  });
}

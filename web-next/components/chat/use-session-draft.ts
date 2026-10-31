"use client";

import { useCallback, useState, useSyncExternalStore } from "react";
const fallback = new Map<string, string>();
const dirty = new Set<string>();
const listeners = new Set<() => void>();
const prefix = "venom-chat-draft:";
function read(key: string) {
  if (!key) return "";
  if (dirty.has(key)) return fallback.get(key) ?? "";
  try { return globalThis.window?.localStorage?.getItem(prefix + key) ?? fallback.get(key) ?? ""; }
  catch { return fallback.get(key) ?? ""; }
}
function storageChanged(event: StorageEvent) {
  try { if (event.storageArea && event.storageArea !== globalThis.window?.localStorage) return; }
  catch { return; }
  if (event.key === null) { fallback.clear(); dirty.clear(); }
  else if (event.key.startsWith(prefix)) { const key = event.key.slice(prefix.length); fallback.delete(key); dirty.delete(key); }
  else return;
  listeners.forEach(listener => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) globalThis.window?.addEventListener?.("storage", storageChanged);
  return () => {
    listeners.delete(listener);
    if (!listeners.size) globalThis.window?.removeEventListener?.("storage", storageChanged);
  };
}
/** Shared by both shells; render/hydration never generates or changes a session. */
export function useSessionDraft(sessionId: string | undefined) {
  const [localDraft, setLocalDraft] = useState("");
  const persisted = useSyncExternalStore(subscribe, () => read(sessionId ?? ""), () => "");
  const draft = sessionId === undefined ? localDraft : persisted;
  const setDraft = useCallback((value: string | ((previous: string) => string)) => {
    if (sessionId === undefined) { setLocalDraft(value); return; }
    if (!sessionId) return;
    const next = typeof value === "function" ? value(read(sessionId)) : value;
    fallback.set(sessionId, next); dirty.add(sessionId);
    try {
      const storage = globalThis.window?.localStorage;
      if (storage) { storage.setItem(prefix + sessionId, next); dirty.delete(sessionId); }
    } catch { /* prefer the latest in-memory value until a write succeeds */ }
    listeners.forEach(listener => listener());
  }, [sessionId]);
  return [draft, setDraft] as const;
}

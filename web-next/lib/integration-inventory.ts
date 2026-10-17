"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { components } from "@/lib/generated/api-types";
export type Integration = components["schemas"]["IntegrationEntry"];
export type Inventory = components["schemas"]["ApiMapResponse"];
type Snapshot = { data: Inventory | null; failed: boolean; loading: boolean };
const initial: Snapshot = { data: null, failed: false, loading: false };
let snapshot = initial;
const listeners = new Set<() => void>();
let pending: { controller: AbortController; promise: Promise<void> } | null = null;
let timer: ReturnType<typeof setInterval> | null = null;
const emit = (value: Snapshot) => { snapshot = value; listeners.forEach((listener) => listener()); };

export function refreshIntegrationInventory() {
  if (pending) return pending.promise;
  const controller = new AbortController();
  const request = { controller, promise: Promise.resolve() };
  pending = request;
  request.promise = (async () => {
    const timeout = setTimeout(() => controller.abort(), 8000);
    emit({ ...snapshot, loading: true });
    try {
      const response = await fetch("/api/v1/system/api-map", { signal: controller.signal, cache: "no-store" });
      if (!response.ok) throw new Error("inventory_unavailable");
      const data: Inventory = await response.json();
      if (!Array.isArray(data.integrations)) throw new Error("inventory_contract_unavailable");
      if (pending === request) emit({ data, failed: false, loading: false });
    } catch {
      if (pending === request) emit({ ...snapshot, failed: true, loading: false });
    } finally {
      clearTimeout(timeout);
      if (pending === request) { pending = null; if (snapshot.loading) emit({ ...snapshot, loading: false }); }
    }
  })();
  return request.promise;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) {
    void refreshIntegrationInventory();
    timer = setInterval(() => { if (!document.hidden) void refreshIntegrationInventory(); }, 10000);
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      if (timer) clearInterval(timer);
      timer = null;
      const request = pending;
      pending = null;
      request?.controller.abort();
      if (snapshot.loading) snapshot = { ...snapshot, loading: false };
    }
  };
}
const getSnapshot = () => snapshot;
const getServerSnapshot = () => initial;

export function useIntegrationInventory(active = true) {
  const listen = useCallback((listener: () => void) => active ? subscribe(listener) : () => undefined, [active]);
  const result = useSyncExternalStore(listen, getSnapshot, getServerSnapshot);
  return { ...result, refresh: refreshIntegrationInventory };
}

// Keeps isolated component fixtures from sharing observations between tests.
export function resetIntegrationInventory() {
  pending?.controller.abort();
  pending = null;
  if (timer) clearInterval(timer);
  timer = null;
  emit(initial);
}

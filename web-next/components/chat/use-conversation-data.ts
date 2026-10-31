"use client";
import { useMemo } from "react";
import { useActiveLlmServer, useUnifiedModelCatalog } from "@/hooks/use-api";
import { resolveCockpitActiveRuntimeInfo } from "@/lib/cockpit-runtime-selection";
import type { ConversationData } from "./use-conversation-controller";
const noRefresh = async () => {};
/** Only catalog and runtime identity. History is session-owned by the shared controller. */
export function useConversationData() {
  const catalog = useUnifiedModelCatalog(0);
  const active = useActiveLlmServer(0);
  const data = useMemo<ConversationData>(() => ({
    history: null, tasks: null, models: null, unifiedModelCatalog: catalog.data,
    activeServerInfo: resolveCockpitActiveRuntimeInfo(active.data ? null : catalog.data, active.data),
    refresh: { history: noRefresh, tasks: noRefresh, queue: noRefresh, activeServer: active.refresh },
  }), [catalog.data, active.data, active.refresh]);
  return { data, loading: catalog.loading || active.loading, error: catalog.error || active.error,
    refresh: async () => { await Promise.all([catalog.refresh(), active.refresh()]); } };
}

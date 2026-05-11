"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getGemma4ApiBaseUrl } from "@/lib/env";
import {
  type DaemonConfigRequest,
  type DaemonConfigResponse,
  type DaemonStatus,
  type ReloadSignal,
  fetchDaemonStatus,
  postAttachAssistant,
  postDaemonConfig,
  postDaemonFallback,
  postDaemonReload,
  postDaemonRestart,
  postDetachAssistant,
} from "@/lib/gemma4-daemon-api";

export type { DaemonStatus, DaemonConfigRequest, ReloadSignal };

export type Gemma4DaemonState = {
  status: DaemonStatus | null;
  loading: boolean;
  error: string | null;
  actionPending: string | null;
  lastAppliedSignal: ReloadSignal | null;
  refresh: () => Promise<void>;
  applyConfig: (params: DaemonConfigRequest) => Promise<DaemonConfigResponse | null>;
  reload: () => Promise<void>;
  restart: () => Promise<void>;
  fallback: () => Promise<ReloadSignal | null>;
  attachAssistant: (modelId: string) => Promise<void>;
  detachAssistant: () => Promise<void>;
};

export function useGemma4Daemon(pollingIntervalMs = 10_000): Gemma4DaemonState {
  const [status, setStatus] = useState<DaemonStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState<string | null>(null);
  const [lastAppliedSignal, setLastAppliedSignal] = useState<ReloadSignal | null>(null);

  const baseUrlRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    baseUrlRef.current = getGemma4ApiBaseUrl();
  }, []);

  const doFetch = useCallback(async () => {
    const base = baseUrlRef.current || getGemma4ApiBaseUrl();
    try {
      const data = await fetchDaemonStatus(base);
      if (mountedRef.current) {
        setStatus(data);
        setError(null);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e.message : "Daemon unavailable");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    baseUrlRef.current = getGemma4ApiBaseUrl();
    doFetch();
    timerRef.current = setInterval(doFetch, pollingIntervalMs);
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [doFetch, pollingIntervalMs]);

  const withAction = useCallback(
    async <T>(key: string, fn: () => Promise<T>): Promise<T | null> => {
      if (actionPending) return null;
      setActionPending(key);
      try {
        const result = await fn();
        await doFetch();
        return result;
      } catch (e) {
        if (mountedRef.current) {
          setError(e instanceof Error ? e.message : `Action '${key}' failed`);
        }
        return null;
      } finally {
        if (mountedRef.current) setActionPending(null);
      }
    },
    [actionPending, doFetch],
  );

  const applyConfig = useCallback(
    async (params: DaemonConfigRequest) => {
      const base = baseUrlRef.current || getGemma4ApiBaseUrl();
      const result = await withAction("config", () => postDaemonConfig(base, params));
      if (result) setLastAppliedSignal(result.reload_signal);
      return result;
    },
    [withAction],
  );

  const reload = useCallback(async () => {
    const base = baseUrlRef.current || getGemma4ApiBaseUrl();
    await withAction("reload", () => postDaemonReload(base));
  }, [withAction]);

  const restart = useCallback(async () => {
    const base = baseUrlRef.current || getGemma4ApiBaseUrl();
    await withAction("restart", () => postDaemonRestart(base));
  }, [withAction]);

  const fallback = useCallback(async () => {
    const base = baseUrlRef.current || getGemma4ApiBaseUrl();
    const result = await withAction("fallback", () => postDaemonFallback(base));
    return result ? result.reload_signal : null;
  }, [withAction]);

  const attachAssistant = useCallback(
    async (modelId: string) => {
      const base = baseUrlRef.current || getGemma4ApiBaseUrl();
      await withAction("attach", () => postAttachAssistant(base, modelId));
    },
    [withAction],
  );

  const detachAssistant = useCallback(async () => {
    const base = baseUrlRef.current || getGemma4ApiBaseUrl();
    await withAction("detach", () => postDetachAssistant(base));
  }, [withAction]);

  return {
    status,
    loading,
    error,
    actionPending,
    lastAppliedSignal,
    refresh: doFetch,
    applyConfig,
    reload,
    restart,
    fallback,
    attachAssistant,
    detachAssistant,
  };
}

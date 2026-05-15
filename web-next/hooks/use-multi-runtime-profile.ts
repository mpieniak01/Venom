"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getGemma4ApiBaseUrl } from "@/lib/env";
import { getApiBaseUrl } from "@/lib/env";
import {
  fetchDaemonStatus,
  postDaemonReload,
  postDaemonRestart,
  type MultiRuntimeProfileResponse,
  type MultiRuntimeProfileUpdateRequest,
  type MultiRuntimeProfileUpdateResponse,
  getMultiRuntimeProfile,
  updateMultiRuntimeProfile,
} from "@/lib/gemma4-daemon-api";

export type { MultiRuntimeApplyMode } from "@/lib/gemma4-daemon-api";
export type {
  MultiRuntimeProfileResponse,
  MultiRuntimeProfileUpdateRequest,
  MultiRuntimeProfileUpdateResponse,
};

export type MultiRuntimeProfileState = {
  data: MultiRuntimeProfileResponse | null;
  loading: boolean;
  error: string | null;
  updatePending: boolean;
  lastUpdateResult: MultiRuntimeProfileUpdateResponse | null;
  refresh: () => Promise<void>;
  applyUpdate: (
    update: MultiRuntimeProfileUpdateRequest,
  ) => Promise<MultiRuntimeProfileUpdateResponse | null>;
};

export function useMultiRuntimeProfile(
  pollingIntervalMs = 15_000,
): MultiRuntimeProfileState {
  const [data, setData] = useState<MultiRuntimeProfileResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatePending, setUpdatePending] = useState(false);
  const [lastUpdateResult, setLastUpdateResult] =
    useState<MultiRuntimeProfileUpdateResponse | null>(null);

  const apiBaseRef = useRef<string>("");
  const daemonBaseRef = useRef<string>("");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    apiBaseRef.current = getApiBaseUrl();
    daemonBaseRef.current = getGemma4ApiBaseUrl();
  }, []);

  const waitForDaemonReadyAfterAction = useCallback(
    async (timeoutMs: number): Promise<void> => {
      const daemonBase = daemonBaseRef.current || getGemma4ApiBaseUrl();
      const startedAt = Date.now();
      while (Date.now() - startedAt < timeoutMs && mountedRef.current) {
        try {
          const status = await fetchDaemonStatus(daemonBase);
          if (!status.pending_reload) return;
        } catch {
          // daemon can be temporarily unavailable during restart
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Timed out while waiting for daemon runtime to become ready");
    },
    [],
  );

  const doFetch = useCallback(async () => {
    const base = apiBaseRef.current || getApiBaseUrl();
    try {
      const result = await getMultiRuntimeProfile(base);
      if (mountedRef.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (mountedRef.current) {
        setError(e instanceof Error ? e.message : "Failed to load profile");
      }
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []);

  const scheduleNext = useCallback(() => {
    if (!mountedRef.current) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      await doFetch();
      scheduleNext();
    }, pollingIntervalMs);
  }, [doFetch, pollingIntervalMs]);

  useEffect(() => {
    mountedRef.current = true;
    doFetch().then(scheduleNext).catch(() => undefined);
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [doFetch, scheduleNext]);

  const refresh = useCallback(async () => {
    setLoading(true);
    await doFetch();
  }, [doFetch]);

  const applyUpdate = useCallback(
    async (
      update: MultiRuntimeProfileUpdateRequest,
    ): Promise<MultiRuntimeProfileUpdateResponse | null> => {
      const base = apiBaseRef.current || getApiBaseUrl();
      setUpdatePending(true);
      try {
        const result = await updateMultiRuntimeProfile(base, update);
        if (mountedRef.current) {
          setLastUpdateResult(result);
        }
        const daemonBase = daemonBaseRef.current || getGemma4ApiBaseUrl();
        if (result.required_apply_mode === "soft_reload") {
          await postDaemonReload(daemonBase);
          await waitForDaemonReadyAfterAction(180_000);
        } else if (result.required_apply_mode === "hard_restart") {
          await postDaemonRestart(daemonBase);
          await waitForDaemonReadyAfterAction(240_000);
        }
        await doFetch();
        return result;
      } catch (e) {
        if (mountedRef.current) {
          setError(e instanceof Error ? e.message : "Update failed");
        }
        return null;
      } finally {
        if (mountedRef.current) setUpdatePending(false);
      }
    },
    [doFetch, waitForDaemonReadyAfterAction],
  );

  return {
    data,
    loading,
    error,
    updatePending,
    lastUpdateResult,
    refresh,
    applyUpdate,
  };
}

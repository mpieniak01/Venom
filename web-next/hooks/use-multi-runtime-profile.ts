"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getApiBaseUrl } from "@/lib/env";
import {
  type MultiRuntimeApplyMode,
  type MultiRuntimeProfileResponse,
  type MultiRuntimeProfileUpdateRequest,
  type MultiRuntimeProfileUpdateResponse,
  getMultiRuntimeProfile,
  updateMultiRuntimeProfile,
} from "@/lib/gemma4-daemon-api";

export type {
  MultiRuntimeApplyMode,
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
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    apiBaseRef.current = getApiBaseUrl();
  }, []);

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
    void doFetch().then(scheduleNext);
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
          if (result.applied) await doFetch();
        }
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
    [doFetch],
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

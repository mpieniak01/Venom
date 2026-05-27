"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getServerApiBaseUrl } from "@/lib/env";
import type {
  IntrospectionSnapshot,
  SnapshotResponse,
} from "@/components/inspector/model-introspection-dashboard-types";

type SnapshotHookResult = {
  snapshot: IntrospectionSnapshot | null;
  loading: boolean;
  error: string | null;
  loadSnapshot: () => Promise<IntrospectionSnapshot | null>;
};

type UseModelIntrospectionSnapshotOptions = {
  autoLoad?: boolean;
};

function readErrorMessage(data: SnapshotResponse & { detail?: string }): string {
  if (typeof data === "object" && data && "detail" in data) {
    return String(data.detail ?? "Request failed");
  }
  return "Request failed";
}

export function useModelIntrospectionSnapshot(
  options?: UseModelIntrospectionSnapshotOptions,
): SnapshotHookResult {
  const autoLoad = options?.autoLoad ?? true;
  const [snapshot, setSnapshot] = useState<IntrospectionSnapshot | null>(null);
  const [loading, setLoading] = useState(autoLoad);
  const [error, setError] = useState<string | null>(null);
  const latestRequestIdRef = useRef(0);

  const loadSnapshot = useCallback(async () => {
    const requestId = ++latestRequestIdRef.current;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${getServerApiBaseUrl()}/api/v1/models/introspection`,
        {
          cache: "no-store",
        },
      );
      const rawBody = await response.text();
      let data: (SnapshotResponse & { detail?: string }) | null = null;
      try {
        data = JSON.parse(rawBody) as SnapshotResponse & { detail?: string };
      } catch {
        data = null;
      }
      if (!response.ok) {
        const fallbackMessage = rawBody.trim() || "Request failed";
        const errorMessage = data ? readErrorMessage(data) : fallbackMessage;
        throw new Error(errorMessage);
      }
      if (!data) {
        throw new Error("Request failed");
      }
      const loadedSnapshot = data.snapshot;
      if (requestId === latestRequestIdRef.current) {
        setSnapshot(loadedSnapshot);
        return loadedSnapshot;
      }
      return null;
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Request failed";
      if (requestId === latestRequestIdRef.current) {
        setError(message);
        setSnapshot(null);
      }
      return null;
    } finally {
      if (requestId === latestRequestIdRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!autoLoad) {
      return;
    }
    loadSnapshot().catch(() => undefined);
  }, [autoLoad, loadSnapshot]);

  return { snapshot, loading, error, loadSnapshot };
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { getServerApiBaseUrl } from "@/lib/env";
import type {
  IntrospectionSnapshot,
  SnapshotResponse,
} from "@/components/inspector/model-introspection-dashboard-types";

type SnapshotHookResult = {
  snapshot: IntrospectionSnapshot | null;
  loading: boolean;
  error: string | null;
  loadSnapshot: () => Promise<void>;
};

function readErrorMessage(data: SnapshotResponse & { detail?: string }): string {
  if (typeof data === "object" && data && "detail" in data) {
    return String(data.detail ?? "Request failed");
  }
  return "Request failed";
}

export function useModelIntrospectionSnapshot(): SnapshotHookResult {
  const [snapshot, setSnapshot] = useState<IntrospectionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `${getServerApiBaseUrl()}/api/v1/models/introspection`,
        {
          cache: "no-store",
        },
      );
      const data = (await response.json()) as SnapshotResponse & { detail?: string };
      if (!response.ok) {
        throw new Error(readErrorMessage(data));
      }
      setSnapshot(data.snapshot);
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "Request failed";
      setError(message);
      setSnapshot(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSnapshot().catch(() => undefined);
  }, [loadSnapshot]);

  return { snapshot, loading, error, loadSnapshot };
}

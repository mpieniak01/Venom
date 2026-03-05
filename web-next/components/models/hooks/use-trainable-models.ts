/**
 * Hook for managing trainable models data
 *
 * Fetches and caches trainable models from unified runtime options.
 */

import { useEffect, useState } from "react";
import {
  getUnifiedModelCatalog,
  type TrainableModelInfo,
} from "@/lib/academy-api";

const CACHE_KEY = "trainable-models-cache";
const CACHE_DURATION_MS = 5 * 60 * 1000; // 5 minutes

interface TrainableModelsCache {
  data: TrainableModelInfo[];
  timestamp: number;
}

function readCache(): TrainableModelInfo[] | null {
  if (globalThis.window === undefined) return null;

  try {
    const cached = globalThis.window.localStorage.getItem(CACHE_KEY);
    if (!cached) return null;

    const parsed = JSON.parse(cached) as TrainableModelsCache;
    const now = Date.now();

    // Check if cache is still valid.
    if (now - parsed.timestamp < CACHE_DURATION_MS) {
      return parsed.data;
    }

    // Cache expired, remove it.
    globalThis.window.localStorage.removeItem(CACHE_KEY);
    return null;
  } catch {
    return null;
  }
}

function writeCache(data: TrainableModelInfo[]) {
  if (globalThis.window === undefined) return;

  try {
    const cache: TrainableModelsCache = {
      data,
      timestamp: Date.now(),
    };
    globalThis.window.localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Ignore cache write errors.
  }
}

export function useTrainableModels() {
  const [trainableModels, setTrainableModels] = useState<TrainableModelInfo[] | null>(
    null,
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTrainableModels() {
      const cached = readCache();
      if (cached) {
        setTrainableModels(cached);
        setLoading(false);
        return;
      }

      try {
        const catalog = await getUnifiedModelCatalog();
        const data = catalog.trainable_models;
        setTrainableModels(data);
        writeCache(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch trainable models:", err);
        setError(err instanceof Error ? err.message : "Unknown error");
        setTrainableModels([]);
      } finally {
        setLoading(false);
      }
    }

    fetchTrainableModels();
  }, []);

  const refresh = async () => {
    setLoading(true);
    try {
      const catalog = await getUnifiedModelCatalog();
      const data = catalog.trainable_models;
      setTrainableModels(data);
      writeCache(data);
      setError(null);
    } catch (err) {
      console.error("Failed to refresh trainable models:", err);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  return {
    trainableModels,
    loading,
    error,
    refresh,
  };
}

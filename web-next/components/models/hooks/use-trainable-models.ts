/**
 * Hook for managing trainable models data
 * 
 * Fetches and caches trainable models from Academy API
 */

import { useState, useEffect } from "react";
import { getTrainableModels, type TrainableModelInfo } from "@/lib/academy-api";

const CACHE_KEY = "trainable-models-cache";
const CACHE_DURATION_MS = 5 * 60 * 1000; // 5 minutes

interface TrainableModelsCache {
  data: TrainableModelInfo[];
  timestamp: number;
}

function readCache(): TrainableModelInfo[] | null {
  if (typeof window === "undefined") return null;
  
  try {
    const cached = window.localStorage.getItem(CACHE_KEY);
    if (!cached) return null;
    
    const parsed = JSON.parse(cached) as TrainableModelsCache;
    const now = Date.now();
    
    // Check if cache is still valid
    if (now - parsed.timestamp < CACHE_DURATION_MS) {
      return parsed.data;
    }
    
    // Cache expired, remove it
    window.localStorage.removeItem(CACHE_KEY);
    return null;
  } catch {
    return null;
  }
}

function writeCache(data: TrainableModelInfo[]) {
  if (typeof window === "undefined") return;
  
  try {
    const cache: TrainableModelsCache = {
      data,
      timestamp: Date.now(),
    };
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Ignore cache write errors
  }
}

export function useTrainableModels() {
  const [trainableModels, setTrainableModels] = useState<TrainableModelInfo[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchTrainableModels() {
      // Try cache first
      const cached = readCache();
      if (cached) {
        setTrainableModels(cached);
        setLoading(false);
        return;
      }

      // Fetch from API
      try {
        const data = await getTrainableModels();
        setTrainableModels(data);
        writeCache(data);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch trainable models:", err);
        setError(err instanceof Error ? err.message : "Unknown error");
        // Set empty array on error so UI can still render
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
      const data = await getTrainableModels();
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

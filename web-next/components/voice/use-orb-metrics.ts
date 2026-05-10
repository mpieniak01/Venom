"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { useModelsUsage } from "@/hooks/use-api";

export type OrbMetrics = {
  cpu: number;
  gpu: number;
  vram: number;
  ram: number;
};

const ZERO_METRICS: OrbMetrics = { cpu: 0, gpu: 0, vram: 0, ram: 0 };

export function useOrbMetrics(): RefObject<OrbMetrics> {
  const metricsRef = useRef<OrbMetrics>({ ...ZERO_METRICS });
  const { data } = useModelsUsage(5000);

  useEffect(() => {
    if (!data?.usage) return;
    const u = data.usage as Record<string, number | undefined>;
    metricsRef.current = {
      cpu: u.cpu_usage_percent ?? 0,
      gpu: typeof u.gpu_usage_percent === "number" ? u.gpu_usage_percent : Number.NaN,
      vram: u.vram_usage_percent ?? 0,
      ram: u.memory_usage_percent ?? 0,
    };
  }, [data]);

  return metricsRef;
}

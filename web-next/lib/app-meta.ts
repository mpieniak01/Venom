"use client";

import { useEffect, useState } from "react";

export type AppMeta = {
  appName?: string;
  version?: string;
  commit?: string;
  timestamp?: string;
  environmentRole?: string;
  generatedBy?: string;
  nodeVersion?: string;
};

let cachedMeta: AppMeta | null = null;
let metaLoadAttempted = false;

function normalizeEnvironmentRole(raw: string | undefined): string | undefined {
  if (!raw) return undefined;
  const normalized = raw.trim().toLowerCase();
  if (["preprod", "pre-prod", "pre_prod", "staging", "stage"].includes(normalized)) {
    return "preprod";
  }
  if (normalized === "dev" || normalized === "development") {
    return "dev";
  }
  return normalized;
}

function fallbackMeta(): AppMeta {
  return {
    version: process.env.NEXT_PUBLIC_APP_VERSION,
    commit: process.env.NEXT_PUBLIC_APP_COMMIT,
    environmentRole: normalizeEnvironmentRole(process.env.NEXT_PUBLIC_ENVIRONMENT_ROLE),
  };
}

export function useAppMeta() {
  const [meta, setMeta] = useState<AppMeta | null>(cachedMeta ?? fallbackMeta());

  useEffect(() => {
    if (metaLoadAttempted) return;
    metaLoadAttempted = true;
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/meta.json", { cache: "no-store" });
        if (!response.ok) throw new Error("meta fetch failed");
        const data: AppMeta = await response.json();
        const merged = { ...fallbackMeta(), ...data };
        cachedMeta = merged;
        if (active) {
          setMeta(merged);
        }
      } catch (err) {
        if (process.env.NODE_ENV !== "production") {
          console.warn("Nie udało się pobrać meta.json", err);
        }
        const fallback = fallbackMeta();
        cachedMeta = fallback;
        if (active) {
          setMeta(fallback);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, []);

  return meta;
}

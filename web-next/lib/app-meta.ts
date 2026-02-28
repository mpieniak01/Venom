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
let metaLoadPromise: Promise<AppMeta> | null = null;

export function normalizeEnvironmentRole(raw: string | undefined): string | undefined {
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

async function loadMeta(): Promise<AppMeta> {
  try {
    const response = await fetch("/meta.json", { cache: "no-store" });
    if (!response.ok) throw new Error("meta fetch failed");
    const data: AppMeta = await response.json();
    const merged = { ...fallbackMeta(), ...data };
    cachedMeta = merged;
    return merged;
  } catch (err) {
    if (process.env.NODE_ENV !== "production") {
      console.warn("Nie udało się pobrać meta.json", err);
    }
    const fallback = fallbackMeta();
    cachedMeta = fallback;
    return fallback;
  }
}

export function useAppMeta() {
  const [meta, setMeta] = useState<AppMeta | null>(cachedMeta ?? fallbackMeta());

  useEffect(() => {
    let active = true;

    if (cachedMeta) {
      Promise.resolve().then(() => {
        if (active && cachedMeta) {
          setMeta(cachedMeta);
        }
      });
      return () => {
        active = false;
      };
    }
    metaLoadPromise ??= loadMeta();
    metaLoadPromise.then((loadedMeta) => {
      if (active) {
        setMeta(loadedMeta);
      }
    });

    return () => {
      active = false;
    };
  }, []);

  return meta;
}

"use client";

import { useEffect, useState } from "react";

export type AppMeta = {
  version?: string;
  commit?: string;
  timestamp?: string;
};

let cachedMeta: AppMeta | null = null;

export function useAppMeta() {
  const [meta, setMeta] = useState<AppMeta | null>(cachedMeta);
  const [loading, setLoading] = useState(!cachedMeta);

  useEffect(() => {
    if (cachedMeta || loading === false) return;
    let active = true;
    const load = async () => {
      try {
        const response = await fetch("/meta.json", { cache: "no-store" });
        if (!response.ok) throw new Error("meta fetch failed");
        const data: AppMeta = await response.json();
        cachedMeta = data;
        if (active) {
          setMeta(data);
        }
      } catch (err) {
        if (process.env.NODE_ENV !== "production") {
          console.warn("Nie udało się pobrać meta.json", err);
        }
        if (active) {
          setMeta(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    load();
    return () => {
      active = false;
    };
  }, [loading]);

  return meta;
}

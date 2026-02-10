import type { ModelCatalogEntry } from "@/lib/types";

export const formatNumber = (value?: number | null) => {
    if (value === null || value === undefined) return "—";
    return value.toLocaleString("pl-PL");
};

export const getRuntimeForProvider = (provider?: string | null) => {
    if (!provider) return "vllm";
    return provider === "ollama" ? "ollama" : "vllm";
};

export const normalizeProvider = (value?: string | null) => {
    if (!value) return "";
    return value.toLowerCase();
};

export const inferProviderFromName = (name?: string | null) => {
    if (!name) return null;
    return name.includes(":") ? "ollama" : "vllm";
};

export const getStatusTone = (status?: string) => {
    if (!status) return "neutral";
    if (status === "completed") return "success";
    if (status === "failed") return "danger";
    if (status === "in_progress") return "warning";
    return "neutral";
};

export const getInstalledModelSizeLabel = (t: (key: string, vars?: Record<string, string | number>) => string, sizeGb?: number) =>
    typeof sizeGb === "number"
        ? `${sizeGb.toFixed(2)} GB`
        : `${t("models.status.size")} —`;

export const readStorageJson = <T,>(key: string): T | null => {
    if (globalThis.window === undefined) return null;
    const raw = globalThis.window.localStorage.getItem(key);
    if (!raw) return null;
    try {
        return JSON.parse(raw) as T;
    } catch {
        globalThis.window.localStorage.removeItem(key);
        return null;
    }
};

export const writeStorageJson = (key: string, value: unknown) => {
    if (globalThis.window === undefined) return;
    globalThis.window.localStorage.setItem(key, JSON.stringify(value));
};

export const readStorageItem = (key: string): string | null => {
    if (globalThis.window === undefined) return null;
    return globalThis.window.localStorage.getItem(key);
};

export type CatalogCachePayload = {
    data: ModelCatalogEntry[];
    stale?: boolean;
    error?: string | null;
};

export type NewsItem = {
    title?: string | null;
    url?: string | null;
    summary?: string | null;
    published_at?: string | null;
    authors?: string[] | null;
};

export type NewsCachePayload = {
    items: NewsItem[];
    stale?: boolean;
    error?: string | null;
};

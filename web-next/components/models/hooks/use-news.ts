import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api-client";
import { useLanguage } from "@/lib/i18n";
import { readStorageJson, writeStorageJson, readStorageItem, NewsCachePayload, NewsItem } from "../models-helpers";

export type NewsResponse = {
    items?: NewsItem[];
    stale?: boolean;
    error?: string | null;
};

export function useNews() {
    const { language } = useLanguage();
    const [newsHf, setNewsHf] = useState<{ items: NewsItem[]; stale?: boolean; error?: string | null; loading: boolean }>({ items: [], loading: false });
    const [papersHf, setPapersHf] = useState<{ items: NewsItem[]; stale?: boolean; error?: string | null; loading: boolean }>({ items: [], loading: false });
    const [newsSort, setNewsSort] = useState<"newest" | "oldest">("newest");
    const [newsCollapsed, setNewsCollapsed] = useState(false);
    const [papersCollapsed, setPapersCollapsed] = useState(false);

    // Initial load from cache
    useEffect(() => {
        const cachedNews = readStorageJson<NewsCachePayload>(`models-blog-hf-${language}`);
        const cachedPapers = readStorageJson<NewsCachePayload>(`models-papers-hf-${language}`);
        const cachedSort = readStorageItem("models-news-sort");

        if (cachedNews) setNewsHf(prev => ({ ...prev, ...cachedNews }));
        if (cachedPapers) setPapersHf(prev => ({ ...prev, ...cachedPapers }));
        if (cachedSort === "newest" || cachedSort === "oldest") setNewsSort(cachedSort);
    }, [language]);

    useEffect(() => {
        if (typeof window !== "undefined") {
            window.localStorage.setItem("models-news-sort", newsSort);
        }
    }, [newsSort]);

    const refreshNews = async () => {
        setNewsHf((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const response = await apiFetch<NewsResponse>(`/api/v1/models/news?provider=huggingface&lang=${language}`);
            const payload = { items: response.items ?? [], stale: response.stale, error: response.error };
            setNewsHf({ ...payload, loading: false });
            writeStorageJson(`models-blog-hf-${language}`, payload);
        } catch (error) {
            setNewsHf((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : "Błąd newsów" }));
        }
    };

    const refreshPapers = async () => {
        setPapersHf((prev) => ({ ...prev, loading: true, error: null }));
        try {
            const response = await apiFetch<NewsResponse>(`/api/v1/models/news?provider=huggingface&type=papers&lang=${language}&limit=3`);
            const payload = { items: response.items ?? [], stale: response.stale, error: response.error };
            setPapersHf({ ...payload, loading: false });
            writeStorageJson(`models-papers-hf-${language}`, payload);
        } catch (error) {
            setPapersHf((prev) => ({ ...prev, loading: false, error: error instanceof Error ? error.message : "Błąd publikacji" }));
        }
    };

    return {
        newsHf, refreshNews,
        papersHf, refreshPapers,
        newsSort, setNewsSort,
        newsCollapsed, setNewsCollapsed,
        papersCollapsed, setPapersCollapsed,
        language
    };
}

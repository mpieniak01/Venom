import { useMemo, useState, useEffect } from "react";
import { useCockpitData } from "./use-cockpit-data";

type Data = ReturnType<typeof useCockpitData>;

export interface TokenSample {
    timestamp: string;
    value: number;
}

export function useCockpitMetricsDisplay(data: Data) {
    // 1. History Status Breakdown
    const historyStatusEntries = useMemo(() => {
        const bucket: Record<string, number> = {};
        (data.history || []).forEach((item) => {
            const key = item.status || "UNKNOWN";
            bucket[key] = (bucket[key] || 0) + 1;
        });
        return Object.entries(bucket)
            .map(([name, value]) => ({ label: name, value }))
            .sort((a, b) => b.value - a.value);
    }, [data.history]);

    // 2. Token Splits
    const tokenSplits = useMemo(() => {
        if (!data.tokenMetrics) return [];
        return [
            { label: "Prompt", value: data.tokenMetrics.prompt_tokens ?? 0 },
            { label: "Completion", value: data.tokenMetrics.completion_tokens ?? 0 },
            { label: "Cached", value: data.tokenMetrics.cached_tokens ?? 0 },
        ].filter((item) => item.value && item.value > 0);
    }, [data.tokenMetrics]);

    // 3. Token History
    const [tokenHistory, setTokenHistory] = useState<TokenSample[]>([]);

    useEffect(() => {
        const total = data.tokenMetrics?.total_tokens;
        if (total === undefined || total === null) return;

        setTokenHistory((prev) => {
            // Keep duplicate timestamps to preserve a simple sample history.
            const next = [
                ...prev,
                {
                    timestamp: new Date().toLocaleTimeString(),
                    value: total,
                },
            ];
            // Keep last 30 samples
            if (next.length > 30) return next.slice(-30);
            return next;
        });
    }, [data.tokenMetrics?.total_tokens]);

    return {
        historyStatusEntries,
        tokenSplits,
        tokenHistory,
    };
}

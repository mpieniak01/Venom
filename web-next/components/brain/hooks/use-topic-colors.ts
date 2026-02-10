import { useCallback } from "react";

export function useTopicColors() {
    const colorFromTopic = useCallback((topic?: string) => {
        if (!topic) return undefined;
        const palette = ["#fbbf24", "#22c55e", "#0ea5e9", "#a855f7", "#f97316", "#38bdf8", "#f43f5e"];
        let hash = 0;
        for (const char of topic) {
            hash = (hash * 31 + (char.codePointAt(0) ?? 0)) % 9973;
        }
        return palette[hash % palette.length];
    }, []);

    return { colorFromTopic };
}

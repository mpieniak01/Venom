export function getNodeData(node: unknown): Record<string, unknown> {
    const data = (node as { data?: unknown }).data;
    if (data && typeof data === "object" && !Array.isArray(data)) {
        return data as Record<string, unknown>;
    }
    return {};
}

export function getStringField(data: Record<string, unknown>, key: string): string {
    const value = data[key];
    return typeof value === "string" ? value : "";
}

export function getNodeId(node: unknown): string {
    return getStringField(getNodeData(node), "id");
}

export function sortByTimestamp(a: unknown, b: unknown): number {
    const aMeta = getNodeData(a).meta as Record<string, unknown> | undefined;
    const bMeta = getNodeData(b).meta as Record<string, unknown> | undefined;
    const aTs = typeof aMeta?.timestamp === "string" ? Date.parse(aMeta.timestamp) : Number.NaN;
    const bTs = typeof bMeta?.timestamp === "string" ? Date.parse(bMeta.timestamp) : Number.NaN;
    if (!Number.isNaN(aTs) && !Number.isNaN(bTs)) return aTs - bTs;
    return getStringField(getNodeData(a), "label").localeCompare(getStringField(getNodeData(b), "label"));
}

export function isAssistantEntry(node: unknown): boolean {
    const data = getNodeData(node);
    const label = typeof data.label === "string" ? data.label : "";
    const meta = (data.meta as Record<string, unknown> | undefined) || {};
    let roleHint = "";
    if (typeof meta.role === "string") {
        roleHint = meta.role;
    } else if (typeof meta.author === "string") {
        roleHint = meta.author;
    } else if (typeof meta.speaker === "string") {
        roleHint = meta.speaker;
    }
    return /assistant|asystent|venom/i.test(roleHint) || /^(assistant|asystent|venom)\b/i.test(label);
}

export function formatOperationTimestamp(value: string | null) {
    if (!value) return "brak daty";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString("pl-PL", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
    });
}

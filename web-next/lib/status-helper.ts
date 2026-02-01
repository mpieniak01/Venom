
type TFunction = (path: string, replacements?: Record<string, string | number>) => string;

export function getTranslatedStatus(status: string | null | undefined, t: TFunction): string {
    if (!status) return "—";

    const normalized = status.toUpperCase();

    switch (normalized) {
        case "PENDING":
            return t("common.pending");
        case "PROCESSING":
        case "IN_PROGRESS":
            return t("common.running");
        case "COMPLETED":
        case "SUCCESS":
            return t("common.completed");
        case "FAILED":
        case "ERROR":
            return t("common.failed");
        case "STOPPED":
            return t("common.stopped");
        default:
            return status; // Fallback to original string if no mapping found
    }
}

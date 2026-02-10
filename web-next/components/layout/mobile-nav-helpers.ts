export type TelemetryTab = "queue" | "tasks" | "ws";

export const AUTONOMY_LEVELS = [
    { value: 0, label: "Start" },
    { value: 10, label: "Monitor" },
    { value: 20, label: "Asystent" },
    { value: 30, label: "Hybryda" },
    { value: 40, label: "Pełny" },
];

export function formatUptime(totalSeconds: number) {
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    return `${hours}h ${minutes}m`;
}

export const getTelemetryContent = ({
    telemetryTab,
    queue,
    metrics,
    connected,
    entriesCount,
    latestLogsTs,
    t
}: {
    telemetryTab: TelemetryTab;
    queue: any;
    metrics: any;
    connected: boolean;
    entriesCount: number;
    latestLogsTs: string | null;
    t: any;
}) => {
    if (telemetryTab === "queue") {
        return {
            title: t("mobileNav.telemetry.queue"),
            rows: [
                { label: t("mobileNav.telemetry.rows.active"), value: queue?.active ?? "—" },
                { label: t("mobileNav.telemetry.rows.pending"), value: queue?.pending ?? "—" },
                { label: t("mobileNav.telemetry.rows.limit"), value: queue?.limit ?? "∞" },
            ],
            badge: queue?.paused
                ? { tone: "warning" as const, text: t("mobileNav.telemetry.status.paused") }
                : { tone: "success" as const, text: t("mobileNav.telemetry.status.active") },
        };
    }
    if (telemetryTab === "tasks") {
        return {
            title: t("mobileNav.telemetry.tasks"),
            rows: [
                { label: t("mobileNav.telemetry.rows.new"), value: metrics?.tasks?.created ?? 0 },
                { label: t("mobileNav.telemetry.rows.success"), value: metrics?.tasks?.success_rate ?? "—" },
                { label: t("mobileNav.telemetry.rows.uptime"), value: metrics?.uptime_seconds ? formatUptime(metrics.uptime_seconds) : "—" },
            ],
            badge: { tone: "neutral" as const, text: t("mobileNav.telemetry.status.preview") },
        };
    }
    return {
        title: t("mobileNav.telemetry.ws"),
        rows: [
            { label: t("mobileNav.telemetry.rows.status"), value: connected ? t("mobileNav.telemetry.status.connected") : t("mobileNav.telemetry.status.disconnected") },
            { label: t("mobileNav.telemetry.rows.logs"), value: `${entriesCount}` },
            { label: t("mobileNav.telemetry.rows.last"), value: latestLogsTs ?? "—" },
        ],
        badge: connected
            ? { tone: "success" as const, text: t("mobileNav.telemetry.status.live") }
            : { tone: "danger" as const, text: t("mobileNav.telemetry.status.none") },
    };
};

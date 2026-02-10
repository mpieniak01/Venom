import {
    Command,
    BugPlay,
    Brain,
    Layers,
    Calendar,
    Gauge,
    Settings
} from "lucide-react";

export const navItems = [
    { href: "/", label: "Kokpit", labelKey: "sidebar.nav.cockpit", icon: Command },
    { href: "/inspector", label: "Inspektor", labelKey: "sidebar.nav.inspector", icon: BugPlay },
    { href: "/brain", label: "Graf wiedzy", labelKey: "sidebar.nav.brain", icon: Brain },
    { href: "/models", label: "Przeglad modeli", labelKey: "sidebar.nav.models", icon: Layers },
    { href: "/calendar", label: "Kalendarz", labelKey: "sidebar.nav.calendar", icon: Calendar },
    { href: "/benchmark", label: "Benchmark", labelKey: "sidebar.nav.benchmark", icon: Gauge },
    { href: "/config", label: "Konfiguracja", labelKey: "sidebar.nav.config", icon: Settings },
];

export const AUTONOMY_LEVELS = [0, 10, 20, 30, 40];

export const getAutonomyDetails = (level: number) => {
    const detailsMap: Record<number, { name: string; riskKey: string; descriptionKey: string }> = {
        0: { name: "ISOLATED", riskKey: "zero", descriptionKey: "0" },
        10: { name: "CONNECTED", riskKey: "low", descriptionKey: "10" },
        20: { name: "FUNDED", riskKey: "medium", descriptionKey: "20" },
        30: { name: "BUILDER", riskKey: "high", descriptionKey: "30" },
        40: { name: "ROOT", riskKey: "critical", descriptionKey: "40" },
    };
    return detailsMap[level];
};

export type AutonomySnapshot = {
    level: number | null;
    name: string;
    risk: string;
    description: string;
};

export type SidebarStoredState = {
    collapsed: boolean | null;
    autonomySnapshot: AutonomySnapshot | null;
};

export const readSidebarStoredState = (): SidebarStoredState => {
    if (globalThis.window === undefined) {
        return { collapsed: null, autonomySnapshot: null };
    }

    const storedCollapsed = globalThis.window.localStorage.getItem("sidebar-collapsed");
    const storedAutonomy = globalThis.window.localStorage.getItem("sidebar-autonomy");
    let autonomySnapshot: AutonomySnapshot | null = null;

    if (storedAutonomy) {
        try {
            autonomySnapshot = JSON.parse(storedAutonomy) as AutonomySnapshot;
        } catch {
            autonomySnapshot = null;
        }
    }

    return {
        collapsed: storedCollapsed ? storedCollapsed === "true" : null,
        autonomySnapshot,
    };
};

export const persistSidebarWidth = (collapsed: boolean) => {
    if (globalThis.window === undefined) return;
    globalThis.window.localStorage.setItem("sidebar-collapsed", String(collapsed));
    const root = document.documentElement;
    if (!root) return;

    const styles = getComputedStyle(root);
    const expandedWidth = styles.getPropertyValue("--sidebar-width-expanded").trim() || "18rem";
    const collapsedWidth = styles.getPropertyValue("--sidebar-width-collapsed").trim() || "6rem";
    root.style.setProperty("--sidebar-width", collapsed ? collapsedWidth : expandedWidth);
};

export const persistAutonomySnapshot = (snapshot: AutonomySnapshot) => {
    if (globalThis.window === undefined) return;
    globalThis.window.localStorage.setItem("sidebar-autonomy", JSON.stringify(snapshot));
};

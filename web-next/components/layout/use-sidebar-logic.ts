import { useState, useCallback, useEffect, useMemo } from "react";
import {
    useAutonomyLevel,
    useCostMode,
    setAutonomy as apiSetAutonomy,
    setCostMode as apiSetCostMode
} from "@/hooks/use-api";
import {
    readSidebarStoredState,
    persistSidebarWidth,
    persistAutonomySnapshot,
    getAutonomyDetails,
    AutonomySnapshot
} from "./sidebar-helpers";

export function useSidebarLogic(t: (key: string, options?: Record<string, unknown>) => string) {
    const { data: costMode, refresh: refreshCost } = useCostMode(15000);
    const { data: autonomy, refresh: refreshAutonomy } = useAutonomyLevel(20000);

    const [costLoading, setCostLoading] = useState(false);
    const [autonomyLoading, setAutonomyLoading] = useState<number | null>(null);
    const [statusMessage, setStatusMessage] = useState<string | null>(null);
    const [selectedAutonomy, setSelectedAutonomy] = useState<string>("");
    const [localAutonomy, setLocalAutonomy] = useState<AutonomySnapshot | null>(null);
    const [collapsed, setCollapsed] = useState(false);
    const [isSynced, setIsSynced] = useState(false);

    const resolveAutonomyDetails = useCallback(
        (level: number | null) => {
            if (level === null || level === undefined) return null;
            const details = getAutonomyDetails(level);
            if (!details) return null;
            return {
                level,
                name: details.name,
                risk: t(`sidebar.autonomy.risks.${details.riskKey}` as string),
                description: t(`sidebar.autonomy.descriptions.${details.descriptionKey}` as string),
            };
        },
        [t],
    );

    const autonomyInfo = useMemo(() => {
        if (autonomy) {
            return {
                level: autonomy.current_level,
                name: autonomy.current_level_name,
                risk: autonomy.risk_level,
                description: autonomy.description,
            };
        }
        if (localAutonomy) return localAutonomy;

        const fallbackLevel = selectedAutonomy ? Number(selectedAutonomy) : null;
        return (
            resolveAutonomyDetails(fallbackLevel) ?? {
                level: null,
                name: t("sidebar.autonomy.noData"),
                risk: "n/a",
                description: t("sidebar.autonomy.offline"),
            }
        );
    }, [autonomy, localAutonomy, selectedAutonomy, resolveAutonomyDetails, t]);

    const handleCostToggle = async () => {
        const targetState = !(costMode?.enabled ?? false);
        if (
            targetState &&
            typeof globalThis.window !== "undefined" &&
            !globalThis.window.confirm(t("sidebar.messages.costConfirm"))
        ) {
            setStatusMessage(t("sidebar.messages.costCancelled"));
            return;
        }
        setCostLoading(true);
        setStatusMessage(null);
        try {
            await apiSetCostMode(targetState);
            refreshCost();
            setStatusMessage(
                t("sidebar.messages.costSuccess", {
                    mode: targetState ? t("sidebar.cost.pro") : t("sidebar.cost.eco"),
                }),
            );
        } catch (error) {
            setStatusMessage(error instanceof Error ? error.message : t("sidebar.messages.costError"));
        } finally {
            setCostLoading(false);
        }
    };

    const handleAutonomyChange = async (level: number) => {
        if (autonomy?.current_level === level) return;
        setAutonomyLoading(level);
        setStatusMessage(null);
        try {
            await apiSetAutonomy(level);
            refreshAutonomy();
            setStatusMessage(t("sidebar.messages.autonomySuccess", { level }));
        } catch (error) {
            const fallback = resolveAutonomyDetails(level);
            if (fallback) {
                setLocalAutonomy(fallback);
                persistAutonomySnapshot(fallback);
            }
            setStatusMessage(error instanceof Error ? error.message : t("sidebar.messages.autonomyError"));
        } finally {
            setAutonomyLoading(null);
        }
    };

    useEffect(() => {
        const storedState = readSidebarStoredState();
        if (storedState.collapsed !== null) setCollapsed(storedState.collapsed);
        if (storedState.autonomySnapshot) {
            setLocalAutonomy(storedState.autonomySnapshot);
            setSelectedAutonomy(String(storedState.autonomySnapshot.level));
        }
        const timer = setTimeout(() => setIsSynced(true), 100);
        return () => clearTimeout(timer);
    }, []);

    useEffect(() => {
        persistSidebarWidth(collapsed);
    }, [collapsed]);

    useEffect(() => {
        if (!autonomy) return;
        const detailsComp = resolveAutonomyDetails(autonomy.current_level);
        const snapshot: AutonomySnapshot = {
            level: autonomy.current_level,
            name: autonomy.current_level_name,
            risk: autonomy.risk_level,
            description: autonomy.description ?? detailsComp?.description ?? "AutonomyGate",
        };
        setLocalAutonomy(snapshot);
        setSelectedAutonomy(String(autonomy.current_level));
        persistAutonomySnapshot(snapshot);
    }, [autonomy, resolveAutonomyDetails]);

    return {
        collapsed,
        setCollapsed,
        isSynced,
        costMode,
        costLoading,
        handleCostToggle,
        autonomyInfo,
        selectedAutonomy,
        setSelectedAutonomy,
        autonomyLoading,
        handleAutonomyChange,
        statusMessage,
    };
}

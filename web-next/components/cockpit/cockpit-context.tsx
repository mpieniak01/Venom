"use client";

import { createContext, useContext, RefObject } from "react";
import { useCockpitData } from "./hooks/use-cockpit-data";
import { useCockpitLayout } from "./hooks/use-cockpit-layout";
import { useCockpitInteractiveState } from "./hooks/use-cockpit-interactive-state";
import { useCockpitLogic } from "./hooks/use-cockpit-logic";

export type CockpitData = ReturnType<typeof useCockpitData>;
export type CockpitLayout = ReturnType<typeof useCockpitLayout>;
export type CockpitInteractive = ReturnType<typeof useCockpitInteractiveState>;
export type CockpitLogic = ReturnType<typeof useCockpitLogic>;

export interface CockpitContextValue {
    data: CockpitData;
    layout: CockpitLayout;
    interactive: CockpitInteractive;
    logic: CockpitLogic;
    chatScrollRef: RefObject<HTMLDivElement>;
}

export const CockpitContext = createContext<CockpitContextValue | null>(null);

export function useCockpitContext() {
    const context = useContext(CockpitContext);
    if (!context) {
        throw new Error("useCockpitContext must be used within a CockpitProvider");
    }
    return context;
}

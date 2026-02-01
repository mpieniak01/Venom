"use client";

import { useRef, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { CockpitContext } from "./cockpit-context";
export { useCockpitContext } from "./cockpit-context";
import type { CockpitInitialData } from "@/lib/server-data";
import { useCockpitData } from "./hooks/use-cockpit-data";
import { useCockpitLayout } from "./hooks/use-cockpit-layout";
import { useCockpitInteractiveState } from "./hooks/use-cockpit-interactive-state";
import { useCockpitLogic } from "./hooks/use-cockpit-logic";

interface CockpitProviderProps {
    initialData: CockpitInitialData;
    variant?: "reference" | "home";
    children: ReactNode;
}

export function CockpitProvider({ initialData, variant = "reference", children }: CockpitProviderProps) {

    // 1. Layout State
    const layout = useCockpitLayout(variant);

    // 2. Data State
    const data = useCockpitData(initialData);

    // 3. Interactive State
    const interactive = useCockpitInteractiveState();

    // 4. Logic & Effects
    const chatScrollRef = useRef<HTMLDivElement>(null!);
    const logic = useCockpitLogic({ data, interactive, layout, chatScrollRef });


    return (
        <CockpitContext.Provider value={{ data, layout, interactive, logic, chatScrollRef }}>
            {children}
        </CockpitContext.Provider>
    );
}

"use client";

import { useState, useCallback, useEffect } from "react";

export function useCockpitLayout(variant: "reference" | "home" = "reference") {
    const [showArtifacts, setShowArtifacts] = useState(true);
    const [labMode, setLabMode] = useState(false);
    const [detailOpen, setDetailOpen] = useState(false);
    const [quickActionsOpen, setQuickActionsOpen] = useState(false);
    const [exportingPinned, setExportingPinned] = useState(false);
    const [tuningOpen, setTuningOpen] = useState(false);
    const [chatFullscreen, setChatFullscreen] = useState(false);

    // Derived state
    const showReferenceSections = variant === "reference";
    const showSharedSections = variant === "reference" || variant === "home";

    // Effects
    useEffect(() => {
        setShowArtifacts(true);
    }, [showReferenceSections]);

    return {
        showArtifacts,
        setShowArtifacts,
        labMode,
        setLabMode,
        detailOpen,
        setDetailOpen,
        quickActionsOpen,
        setQuickActionsOpen,
        exportingPinned,
        setExportingPinned,
        tuningOpen,
        setTuningOpen,
        chatFullscreen,
        setChatFullscreen,
        showReferenceSections,
        showSharedSections,
    };
}

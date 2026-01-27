"use client";

import type { ReactNode } from "react";

type CockpitSidebarProps = {
  chatFullscreen: boolean;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  referencePanel: ReactNode;
  fallbackPanels: ReactNode;
};

export function CockpitSidebar({
  chatFullscreen,
  showArtifacts,
  showReferenceSections,
  referencePanel,
  fallbackPanels,
}: CockpitSidebarProps) {
  if (chatFullscreen || !showArtifacts) return null;

  return (
    <div className="space-y-6">
      {showReferenceSections ? referencePanel : fallbackPanels}
    </div>
  );
}

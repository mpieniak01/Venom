"use client";

import type { ReactNode } from "react";

import { motion } from "framer-motion";

type CockpitSidebarProps = Readonly<{
  chatFullscreen: boolean;
  showArtifacts: boolean;
  showReferenceSections: boolean;
  referencePanel: ReactNode;
  fallbackPanels: ReactNode;
  skipEntrance?: boolean;
}>;

export function CockpitSidebar({
  chatFullscreen,
  showArtifacts,
  showReferenceSections,
  referencePanel,
  fallbackPanels,
  skipEntrance = false,
}: CockpitSidebarProps) {
  if (chatFullscreen || !showArtifacts) return null;

  return (
    <motion.div
      initial={skipEntrance ? false : { opacity: 0, x: -20, width: 0, marginRight: 0 }}
      animate={{ opacity: 1, x: 0, width: "auto", marginRight: 0 }}
      exit={{ opacity: 0, x: -20, width: 0, marginRight: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className="space-y-6 overflow-hidden"
    >
      {showReferenceSections ? referencePanel : fallbackPanels}
    </motion.div>
  );
}

"use client";

import { useMemo } from "react";
import type { CockpitInitialData } from "@/lib/server-data";
import { CockpitHeader } from "@/components/cockpit/cockpit-header";
import { CockpitPrimarySection } from "@/components/cockpit/cockpit-primary-section";
import { CockpitRuntimeSection } from "@/components/cockpit/cockpit-runtime-section";
import { useCockpitSectionProps } from "@/components/cockpit/cockpit-section-props";
import { CockpitProvider, useCockpitContext } from "./cockpit-provider";

export function CockpitHome({
  initialData,
  variant = "reference",
}: {
  initialData: CockpitInitialData;
  variant?: "reference" | "home";
}) {
  return (
    <CockpitProvider initialData={initialData} variant={variant}>
      <CockpitHomeContent />
    </CockpitProvider>
  );
}

function CockpitHomeContent() {
  const { layout } = useCockpitContext();
  const { primarySectionProps, runtimeSectionProps } = useCockpitSectionProps();

  const headerProps = useMemo(() => ({
    showReferenceSections: layout.showReferenceSections,
    showArtifacts: layout.showArtifacts,
    onToggleArtifacts: () => layout.setShowArtifacts(!layout.showArtifacts),
  }), [layout]);

  return (
    <div className="space-y-6 pb-10">
      {/* HEADER */}
      <CockpitHeader {...headerProps} />

      {/* SECTIONS */}
      <CockpitPrimarySection {...primarySectionProps} />
      <CockpitRuntimeSection {...runtimeSectionProps} />
    </div>
  );
}

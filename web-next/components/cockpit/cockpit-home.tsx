"use client";

import type { CockpitInitialData } from "@/lib/server-data";
import { CockpitHeader } from "@/components/cockpit/cockpit-header";
import { CockpitPrimarySection } from "@/components/cockpit/cockpit-primary-section";
import { CockpitRuntimeSection } from "@/components/cockpit/cockpit-runtime-section";
import { useCockpitSectionProps } from "@/components/cockpit/cockpit-section-props";
import { CockpitProvider } from "./cockpit-provider";

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
  const { primarySectionProps, runtimeSectionProps } = useCockpitSectionProps();

  return (
    <div className="space-y-6 pb-10">
      {/* HEADER */}
      <CockpitHeader />

      {/* SECTIONS */}
      <CockpitPrimarySection {...primarySectionProps} />
      <CockpitRuntimeSection {...runtimeSectionProps} />
    </div>
  );
}

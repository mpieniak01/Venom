"use client";

import type { ComponentProps } from "react";
import { CockpitRuntime } from "@/components/cockpit/cockpit-runtime";
import { CockpitRequestDetailDrawer } from "@/components/cockpit/cockpit-request-detail-drawer";
import { CockpitTuningDrawer } from "@/components/cockpit/cockpit-tuning-drawer";

type CockpitRuntimeProps = ComponentProps<typeof CockpitRuntime>;
type CockpitRequestDetailProps = ComponentProps<typeof CockpitRequestDetailDrawer>;
type CockpitTuningDrawerProps = ComponentProps<typeof CockpitTuningDrawer>;

type CockpitRuntimeSectionProps = {
  runtimeProps: CockpitRuntimeProps;
  requestDetailProps: CockpitRequestDetailProps;
  tuningDrawerProps: CockpitTuningDrawerProps;
};

export function CockpitRuntimeSection({
  runtimeProps,
  requestDetailProps,
  tuningDrawerProps,
}: CockpitRuntimeSectionProps) {
  return (
    <>
      <CockpitRuntime {...runtimeProps} />
      <CockpitRequestDetailDrawer {...requestDetailProps} />
      <CockpitTuningDrawer {...tuningDrawerProps} />
    </>
  );
}

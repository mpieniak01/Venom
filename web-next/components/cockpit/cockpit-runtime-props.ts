"use client";

import { useMemo } from "react";
import type { ComponentProps } from "react";
import { CockpitRuntime } from "@/components/cockpit/cockpit-runtime";
import { CockpitRequestDetailDrawer } from "@/components/cockpit/cockpit-request-detail-drawer";
import { CockpitTuningDrawer } from "@/components/cockpit/cockpit-tuning-drawer";

type CockpitRuntimeProps = ComponentProps<typeof CockpitRuntime>;
type CockpitRequestDetailProps = ComponentProps<typeof CockpitRequestDetailDrawer>;
type CockpitTuningDrawerProps = ComponentProps<typeof CockpitTuningDrawer>;

type CockpitRuntimeSectionInputs = {
  runtimeProps: CockpitRuntimeProps;
  requestDetailProps: CockpitRequestDetailProps;
  tuningDrawerProps: CockpitTuningDrawerProps;
};

export function useCockpitRuntimeSectionProps({
  runtimeProps,
  requestDetailProps,
  tuningDrawerProps,
}: CockpitRuntimeSectionInputs) {
  const memoRuntimeProps = useMemo(() => runtimeProps, [runtimeProps]);
  const memoRequestDetailProps = useMemo(() => requestDetailProps, [requestDetailProps]);
  const memoTuningDrawerProps = useMemo(() => tuningDrawerProps, [tuningDrawerProps]);

  return {
    runtimeProps: memoRuntimeProps,
    requestDetailProps: memoRequestDetailProps,
    tuningDrawerProps: memoTuningDrawerProps,
  };
}

"use client";

import { useMemo } from "react";

export type OrbEffectsConfig = {
  // 2D CSS effects (from PR 206B)
  ripple: boolean;
  blob: boolean;
  glow: boolean;
  transitions: boolean;
  frequencyRing: boolean;
  coreTexture: boolean;
  particles: boolean;
  stateLabel: boolean;
  // 3D mode (PR 207) — replaces CSS equivalents when true
  orb3D: boolean;
  bloom: boolean;
  chromaticAberration: boolean;
  iridescence: boolean;
  volumetricLights: boolean;
  // PR 208B — live system metrics bars radiating from orb center
  orbMetricsBars: boolean;
};

const ALL_OFF: OrbEffectsConfig = {
  ripple: false,
  blob: false,
  glow: false,
  transitions: false,
  frequencyRing: false,
  coreTexture: false,
  particles: false,
  stateLabel: false,
  orb3D: false,
  bloom: false,
  chromaticAberration: false,
  iridescence: false,
  volumetricLights: false,
  orbMetricsBars: false,
};

// Next.js replaces NEXT_PUBLIC_* vars at build time only when referenced by
// their full literal name — dynamic process.env[key] is not replaced in the
// browser bundle. Each flag is therefore read with a static reference.
function isOff(v: string | undefined): boolean {
  return v === "false" || v === "0";
}

export function useOrbEffectsConfig(): OrbEffectsConfig {
  return useMemo(() => {
    if (process.env.NEXT_PUBLIC_ORB_EFFECTS === "off") return ALL_OFF;
    return {
      ripple:              !isOff(process.env.NEXT_PUBLIC_ORB_RIPPLE),
      blob:                !isOff(process.env.NEXT_PUBLIC_ORB_BLOB),
      glow:                !isOff(process.env.NEXT_PUBLIC_ORB_GLOW),
      transitions:         !isOff(process.env.NEXT_PUBLIC_ORB_TRANSITIONS),
      frequencyRing:       !isOff(process.env.NEXT_PUBLIC_ORB_FREQUENCY_RING),
      coreTexture:         !isOff(process.env.NEXT_PUBLIC_ORB_CORE_TEXTURE),
      particles:           !isOff(process.env.NEXT_PUBLIC_ORB_PARTICLES),
      stateLabel:          !isOff(process.env.NEXT_PUBLIC_ORB_STATE_LABEL),
      // 3D effects — orb3D defaults to false (opt-in)
      orb3D:               process.env.NEXT_PUBLIC_ORB_3D === "true",
      bloom:               !isOff(process.env.NEXT_PUBLIC_ORB_BLOOM),
      chromaticAberration: !isOff(process.env.NEXT_PUBLIC_ORB_CHROMATIC_ABERRATION),
      iridescence:         !isOff(process.env.NEXT_PUBLIC_ORB_IRIDESCENCE),
      volumetricLights:    !isOff(process.env.NEXT_PUBLIC_ORB_VOLUMETRIC_LIGHTS),
      // PR 208B — metrics bars default to false (opt-in)
      orbMetricsBars:      process.env.NEXT_PUBLIC_ORB_METRICS_BARS === "true",
    };
  }, []);
}

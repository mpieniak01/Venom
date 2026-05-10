"use client";

import { useMemo } from "react";

export type OrbEffectsConfig = {
  ripple: boolean;
  blob: boolean;
  glow: boolean;
  transitions: boolean;
  frequencyRing: boolean;
  coreTexture: boolean;
  particles: boolean;
  stateLabel: boolean;
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
      ripple:       !isOff(process.env.NEXT_PUBLIC_ORB_RIPPLE),
      blob:         !isOff(process.env.NEXT_PUBLIC_ORB_BLOB),
      glow:         !isOff(process.env.NEXT_PUBLIC_ORB_GLOW),
      transitions:  !isOff(process.env.NEXT_PUBLIC_ORB_TRANSITIONS),
      frequencyRing:!isOff(process.env.NEXT_PUBLIC_ORB_FREQUENCY_RING),
      coreTexture:  !isOff(process.env.NEXT_PUBLIC_ORB_CORE_TEXTURE),
      particles:    !isOff(process.env.NEXT_PUBLIC_ORB_PARTICLES),
      stateLabel:   !isOff(process.env.NEXT_PUBLIC_ORB_STATE_LABEL),
    };
  }, []);
}

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

function readFlag(key: string): boolean {
  const v = process.env[key];
  return v !== "false" && v !== "0";
}

export function useOrbEffectsConfig(): OrbEffectsConfig {
  return useMemo(() => {
    if (process.env.NEXT_PUBLIC_ORB_EFFECTS === "off") return ALL_OFF;
    return {
      ripple: readFlag("NEXT_PUBLIC_ORB_RIPPLE"),
      blob: readFlag("NEXT_PUBLIC_ORB_BLOB"),
      glow: readFlag("NEXT_PUBLIC_ORB_GLOW"),
      transitions: readFlag("NEXT_PUBLIC_ORB_TRANSITIONS"),
      frequencyRing: readFlag("NEXT_PUBLIC_ORB_FREQUENCY_RING"),
      coreTexture: readFlag("NEXT_PUBLIC_ORB_CORE_TEXTURE"),
      particles: readFlag("NEXT_PUBLIC_ORB_PARTICLES"),
      stateLabel: readFlag("NEXT_PUBLIC_ORB_STATE_LABEL"),
    };
  }, []);
}

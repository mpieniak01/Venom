"use client";

import { useMemo, useSyncExternalStore } from "react";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import type { VoiceOrbState } from "@/components/voice/voice-orb";

export type VoiceRenderDiagnosticMode =
  | "off"
  | "shell_only"
  | "voice_layout_only"
  | "orb_static_core"
  | "orb_ready_glow"
  | "orb_dialogs_only"
  | "full_ready";

const VALID_MODES = new Set<VoiceRenderDiagnosticMode>([
  "off",
  "shell_only",
  "voice_layout_only",
  "orb_static_core",
  "orb_ready_glow",
  "orb_dialogs_only",
  "full_ready",
]);

export type VoiceRenderDiagnostics = Readonly<{
  mode: VoiceRenderDiagnosticMode;
  showOrbZone: boolean;
  showOrb: boolean;
  showDialogs: boolean;
  forceReadyState: boolean;
  plainOrbWrapper: boolean;
  metricsEnabled: boolean;
  effectOverrides: Partial<OrbEffectsConfig>;
}>;

const EFFECT_QUERY_KEYS: Record<keyof OrbEffectsConfig, string> = {
  ripple: "voiceFxRipple",
  blob: "voiceFxBlob",
  glow: "voiceFxGlow",
  transitions: "voiceFxTransitions",
  frequencyRing: "voiceFxFrequencyRing",
  coreTexture: "voiceFxCoreTexture",
  particles: "voiceFxParticles",
  stateLabel: "voiceFxStateLabel",
  orbMetricsBars: "voiceFxMetrics",
};

function normalizeMode(value: string | null | undefined): VoiceRenderDiagnosticMode {
  if (!value) return "off";
  const normalized = value.trim().toLowerCase() as VoiceRenderDiagnosticMode;
  return VALID_MODES.has(normalized) ? normalized : "off";
}

export function parseVoiceRenderDiagnosticMode(urlSearch?: string | null): VoiceRenderDiagnosticMode {
  if (urlSearch) {
    const searchParams = new URLSearchParams(urlSearch);
    const queryValue = searchParams.get("voiceDiag");
    const queryMode = normalizeMode(queryValue);
    if (queryMode !== "off" || queryValue === "off") {
      return queryMode;
    }
  }

  return normalizeMode(process.env.NEXT_PUBLIC_VOICE_RENDER_DIAGNOSTIC_MODE);
}

export function resolveVoiceRenderDiagnostics(
  mode: VoiceRenderDiagnosticMode,
): VoiceRenderDiagnostics {
  switch (mode) {
    case "shell_only":
      return {
        mode,
        showOrbZone: false,
        showOrb: false,
        showDialogs: false,
        forceReadyState: false,
        plainOrbWrapper: true,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "voice_layout_only":
      return {
        mode,
        showOrbZone: true,
        showOrb: false,
        showDialogs: false,
        forceReadyState: false,
        plainOrbWrapper: true,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "orb_static_core":
      return {
        mode,
        showOrbZone: true,
        showOrb: true,
        showDialogs: false,
        forceReadyState: true,
        plainOrbWrapper: true,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "orb_ready_glow":
      return {
        mode,
        showOrbZone: true,
        showOrb: true,
        showDialogs: false,
        forceReadyState: true,
        plainOrbWrapper: true,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "orb_dialogs_only":
      return {
        mode,
        showOrbZone: true,
        showOrb: false,
        showDialogs: true,
        forceReadyState: true,
        plainOrbWrapper: true,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "full_ready":
      return {
        mode,
        showOrbZone: true,
        showOrb: true,
        showDialogs: true,
        forceReadyState: true,
        plainOrbWrapper: false,
        metricsEnabled: false,
        effectOverrides: {},
      };
    case "off":
    default:
      return {
        mode: "off",
        showOrbZone: true,
        showOrb: true,
        showDialogs: true,
        forceReadyState: false,
        plainOrbWrapper: false,
        metricsEnabled: true,
        effectOverrides: {},
      };
  }
}

function parseBooleanOverride(value: string | null): boolean | undefined {
  if (value === null) return undefined;
  const normalized = value.trim().toLowerCase();
  if (normalized === "1" || normalized === "true" || normalized === "on") return true;
  if (normalized === "0" || normalized === "false" || normalized === "off") return false;
  return undefined;
}

export function parseVoiceEffectOverrides(urlSearch?: string | null): Partial<OrbEffectsConfig> {
  if (!urlSearch) return {};
  const searchParams = new URLSearchParams(urlSearch);
  const overrides: Partial<OrbEffectsConfig> = {};
  for (const [effectName, queryKey] of Object.entries(EFFECT_QUERY_KEYS) as Array<
    [keyof OrbEffectsConfig, string]
  >) {
    const override = parseBooleanOverride(searchParams.get(queryKey));
    if (override !== undefined) {
      overrides[effectName] = override;
    }
  }
  return overrides;
}

export function applyOrbDiagnosticProfile(
  config: OrbEffectsConfig,
  diagnostics: Pick<VoiceRenderDiagnostics, "mode" | "effectOverrides">,
): OrbEffectsConfig {
  const { mode, effectOverrides } = diagnostics;
  if (mode === "orb_static_core") {
    return {
      ...config,
      ripple: false,
      blob: false,
      glow: false,
      transitions: false,
      frequencyRing: false,
      coreTexture: false,
      particles: false,
      orbMetricsBars: false,
      ...effectOverrides,
    };
  }

  if (mode === "orb_ready_glow") {
    return {
      ...config,
      ripple: false,
      blob: false,
      glow: true,
      transitions: false,
      frequencyRing: false,
      coreTexture: false,
      particles: false,
      orbMetricsBars: false,
      ...effectOverrides,
    };
  }

  if (mode === "full_ready") {
    return {
      ...config,
      orbMetricsBars: false,
      ...effectOverrides,
    };
  }

  if (Object.keys(effectOverrides).length > 0) {
    return {
      ...config,
      ...effectOverrides,
    };
  }

  return config;
}

export function resolveDiagnosticOrbState(
  state: VoiceOrbState,
  diagnostics: VoiceRenderDiagnostics,
): VoiceOrbState {
  return diagnostics.forceReadyState ? "ready" : state;
}

export function useVoiceRenderDiagnostics(): VoiceRenderDiagnostics {
  const readLocationSearch = () =>
    typeof globalThis.location === "undefined" ? "" : globalThis.location.search;

  const urlSearch = useSyncExternalStore(
    () => () => undefined,
    readLocationSearch,
    readLocationSearch,
  );

  return useMemo(() => {
    const mode = parseVoiceRenderDiagnosticMode(urlSearch);
    return {
      ...resolveVoiceRenderDiagnostics(mode),
      effectOverrides: parseVoiceEffectOverrides(urlSearch),
    };
  }, [urlSearch]);
}

"use client";

import dynamic from "next/dynamic";
import type { RefObject } from "react";
import { VoiceOrb, type VoiceOrbState } from "@/components/voice/voice-orb";
import { OrbDialogWindow } from "@/components/voice/orb-dialog-window";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import type { OrbMetrics } from "@/components/voice/use-orb-metrics";
import { useTranslation } from "@/lib/i18n";

// Lazy-load 3D orb — never included in initial bundle, SSR disabled
const VoiceOrb3D = dynamic(
  () => import("@/components/voice/voice-orb-3d").then((m) => ({ default: m.VoiceOrb3D })),
  { ssr: false, loading: () => <div style={{ width: 200, height: 200 }} /> },
);

function supportsWebGL(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const canvas = document.createElement("canvas");
    return !!(
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")
    );
  } catch {
    return false;
  }
}

type OrbZoneProps = Readonly<{
  transcription: string;
  response: string;
  orbState: VoiceOrbState;
  effectsConfig: OrbEffectsConfig;
  reducedMotion: boolean;
  audioEnabled: boolean;
  micAnalyserRef: RefObject<AnalyserNode | null>;
  ttsAnalyserRef: RefObject<AnalyserNode | null>;
  label?: string;
  metricsRef?: RefObject<OrbMetrics>;
}>;

export function OrbZone({
  transcription,
  response,
  orbState,
  effectsConfig,
  reducedMotion,
  audioEnabled,
  micAnalyserRef,
  ttsAnalyserRef,
  label,
  metricsRef,
}: OrbZoneProps) {
  const t = useTranslation();
  const use3D = effectsConfig.orb3D && !reducedMotion && supportsWebGL();
  const orbLabel = label ?? t(`voice.orb.stateLabel.${orbState}`);

  return (
    <div className="flex flex-col gap-3 w-full" style={{ minHeight: "520px" }}>
      {/* User bubble — above orb, full width */}
      <OrbDialogWindow
        role="user"
        text={transcription}
        orbState={orbState}
        reducedMotion={reducedMotion}
        emptyLabel={t("voice.status.waitingForVoiceCommand")}
      />

      {/* Orb — centered, takes remaining vertical space */}
      <div className="flex flex-1 items-center justify-center">
        {use3D ? (
          <VoiceOrb3D
            state={orbState}
            effectsConfig={effectsConfig}
            reducedMotion={reducedMotion}
            micAnalyserRef={micAnalyserRef}
            ttsAnalyserRef={ttsAnalyserRef}
            disabled={!audioEnabled}
            size={240}
            metricsRef={metricsRef}
          />
        ) : (
          <div className="flex justify-center rounded-2xl box-muted py-8 px-10">
            <VoiceOrb
              state={orbState}
              disabled={!audioEnabled}
              reducedMotion={reducedMotion}
              label={orbLabel}
              effectsConfig={effectsConfig}
              micAnalyserRef={micAnalyserRef}
              ttsAnalyserRef={ttsAnalyserRef}
              metricsRef={metricsRef}
            />
          </div>
        )}
      </div>

      {/* Assistant bubble — below orb, full width */}
      <OrbDialogWindow
        role="assistant"
        text={response}
        orbState={orbState}
        reducedMotion={reducedMotion}
        emptyLabel={t("voice.status.noResponseYet")}
      />
    </div>
  );
}

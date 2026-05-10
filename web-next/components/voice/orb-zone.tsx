"use client";

import dynamic from "next/dynamic";
import type { RefObject } from "react";
import { VoiceOrb, type VoiceOrbState } from "@/components/voice/voice-orb";
import { OrbDialogWindow } from "@/components/voice/orb-dialog-window";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
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
}: OrbZoneProps) {
  const t = useTranslation();
  const use3D = effectsConfig.orb3D && !reducedMotion && supportsWebGL();
  const orbLabel = label ?? t(`voice.orb.stateLabel.${orbState}`);

  return (
    <div
      className="flex flex-col items-center gap-2 w-full"
      style={{ minHeight: "520px" }}
    >
      {/* User bubble — above orb */}
      <OrbDialogWindow
        role="user"
        text={transcription}
        orbState={orbState}
        reducedMotion={reducedMotion}
        emptyLabel={t("voice.status.waitingForVoiceCommand")}
      />

      {/* Orb — 2D CSS or 3D Three.js */}
      <div className="flex items-center justify-center">
        {use3D ? (
          <VoiceOrb3D
            state={orbState}
            effectsConfig={effectsConfig}
            reducedMotion={reducedMotion}
            micAnalyserRef={micAnalyserRef}
            ttsAnalyserRef={ttsAnalyserRef}
            disabled={!audioEnabled}
            size={200}
          />
        ) : (
          <div className="flex justify-center rounded-2xl box-muted py-6 px-8">
            <VoiceOrb
              state={orbState}
              disabled={!audioEnabled}
              reducedMotion={reducedMotion}
              label={orbLabel}
              effectsConfig={effectsConfig}
              micAnalyserRef={micAnalyserRef}
              ttsAnalyserRef={ttsAnalyserRef}
            />
          </div>
        )}
      </div>

      {/* Assistant bubble — below orb */}
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

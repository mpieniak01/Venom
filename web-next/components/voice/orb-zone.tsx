"use client";

import dynamic from "next/dynamic";
import type { RefObject } from "react";
import { VoiceOrb, type VoiceOrbState } from "@/components/voice/voice-orb";
import { OrbDialogWindow } from "@/components/voice/orb-dialog-window";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import type { OrbMetrics } from "@/components/voice/use-orb-metrics";
import type { VoiceRenderDiagnosticMode } from "@/components/voice/voice-render-diagnostics";
import { useTranslation } from "@/lib/i18n";

const ORB_3D_SIZE = 240;

// Lazy-load 3D orb — never included in initial bundle, SSR disabled
const VoiceOrb3D = dynamic(
  () => import("@/components/voice/voice-orb-3d").then((m) => ({ default: m.VoiceOrb3D })),
  { ssr: false, loading: () => <div style={{ width: ORB_3D_SIZE, height: ORB_3D_SIZE }} /> },
);

function supportsWebGL(): boolean {
  if (globalThis.window === undefined) return false;
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
  calmIdle: boolean;
  pageVisible: boolean;
  audioEnabled: boolean;
  micAnalyserRef: RefObject<AnalyserNode | null>;
  ttsAnalyserRef: RefObject<AnalyserNode | null>;
  label?: string;
  metricsRef?: RefObject<OrbMetrics>;
  showOrb?: boolean;
  showDialogs?: boolean;
  plainOrbWrapper?: boolean;
  diagnosticMode?: VoiceRenderDiagnosticMode;
}>;

export function OrbZone({
  transcription,
  response,
  orbState,
  effectsConfig,
  reducedMotion,
  calmIdle,
  pageVisible,
  audioEnabled,
  micAnalyserRef,
  ttsAnalyserRef,
  label,
  metricsRef,
  showOrb = true,
  showDialogs = true,
  plainOrbWrapper = false,
  diagnosticMode = "off",
}: OrbZoneProps) {
  const t = useTranslation();
  const use3D = effectsConfig.orb3D && !reducedMotion && !calmIdle && pageVisible && supportsWebGL();
  const orbLabel = label ?? t(`voice.orb.stateLabel.${orbState}`);
  const orbWrapperClass = plainOrbWrapper
    ? "flex justify-center rounded-2xl border border-dashed border-white/10 bg-transparent py-8 px-10"
    : "flex justify-center rounded-2xl box-muted py-8 px-10";
  const diagnosticLabel =
    diagnosticMode !== "off" ? (
      <div className="mt-3 text-center text-[10px] uppercase tracking-[0.28em] text-zinc-500">
        {diagnosticMode}
      </div>
    ) : null;

  return (
    <div className="flex flex-col gap-3 w-full" style={{ minHeight: "520px" }}>
      {/* User bubble — above orb, full width */}
      {showDialogs && (
        <OrbDialogWindow
          role="user"
          text={transcription}
          orbState={orbState}
          reducedMotion={reducedMotion}
          emptyLabel={t("voice.status.waitingForVoiceCommand")}
        />
      )}

      {/* Orb — centered, takes remaining vertical space */}
      <div className="flex flex-1 items-center justify-center">
        {showOrb ? (
          use3D ? (
            <div className="flex flex-col items-center">
              <VoiceOrb3D
                state={orbState}
                effectsConfig={effectsConfig}
                reducedMotion={reducedMotion}
                micAnalyserRef={micAnalyserRef}
                ttsAnalyserRef={ttsAnalyserRef}
                disabled={!audioEnabled}
                size={ORB_3D_SIZE}
                metricsRef={metricsRef}
              />
              {diagnosticLabel}
            </div>
          ) : (
            <div className={orbWrapperClass}>
              <div className="flex flex-col items-center">
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
                {diagnosticLabel}
              </div>
            </div>
          )
        ) : (
          <div className={orbWrapperClass}>
            <div className="flex min-h-[180px] min-w-[240px] items-center justify-center text-xs uppercase tracking-[0.28em] text-zinc-500">
              orb hidden
            </div>
          </div>
        )}
      </div>

      {/* Assistant bubble — below orb, full width */}
      {showDialogs && (
        <OrbDialogWindow
          role="assistant"
          text={response}
          orbState={orbState}
          reducedMotion={reducedMotion}
          emptyLabel={t("voice.status.noResponseYet")}
        />
      )}
    </div>
  );
}

"use client";

import type { RefObject } from "react";
import { VoiceOrb, type VoiceOrbState } from "@/components/voice/voice-orb";
import { OrbDialogWindow } from "@/components/voice/orb-dialog-window";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import type { OrbMetrics } from "@/components/voice/use-orb-metrics";
import type { VoiceRenderDiagnosticMode } from "@/components/voice/voice-render-diagnostics";
import { useTranslation } from "@/lib/i18n";

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
  const orbLabel = label ?? t(`voice.orb.stateLabel.${orbState}`);
  const orbWrapperClass = plainOrbWrapper
    ? "flex w-[360px] max-w-full aspect-square items-center justify-center rounded-2xl border border-dashed border-white/10 bg-transparent py-8 px-10 overflow-visible"
    : "flex w-[360px] max-w-full aspect-square items-center justify-center rounded-2xl box-muted py-8 px-10 overflow-visible";
  const diagnosticLabel =
    diagnosticMode !== "off" ? (
      <div className="mt-3 text-center text-[10px] uppercase tracking-[0.28em] text-zinc-500">
        {diagnosticMode}
      </div>
    ) : null;

  return (
    <div className="relative flex w-full flex-col overflow-visible" style={{ minHeight: "620px" }}>
      {/* User bubble — above orb, full width */}
      {showDialogs && (
        <div className="absolute left-0 right-0 top-0 z-20 px-0">
          <OrbDialogWindow
            role="user"
            text={transcription}
            orbState={orbState}
            reducedMotion={reducedMotion}
            emptyLabel={t("voice.status.waitingForVoiceCommand")}
          />
        </div>
      )}

      {/* Orb — centered, takes remaining vertical space */}
      <div className="flex flex-1 items-center justify-center py-24">
        {showOrb ? (
          <div className={orbWrapperClass}>
            <div className="relative z-10 flex flex-col items-center">
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
        ) : (
          <div className={orbWrapperClass}>
            <div className="flex min-h-[260px] min-w-[260px] items-center justify-center text-xs uppercase tracking-[0.28em] text-zinc-500">
              orb hidden
            </div>
          </div>
        )}
      </div>

      {/* Assistant bubble — below orb, full width */}
      {showDialogs && (
        <div className="absolute left-0 right-0 bottom-0 z-20 px-0">
          <OrbDialogWindow
            role="assistant"
            text={response}
            orbState={orbState}
            reducedMotion={reducedMotion}
            emptyLabel={t("voice.status.noResponseYet")}
          />
        </div>
      )}
    </div>
  );
}

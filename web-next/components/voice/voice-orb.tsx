"use client";

import { useMemo } from "react";

export type VoiceOrbState =
  | "offline"
  | "ready"
  | "recording"
  | "stt"
  | "thinking"
  | "tts"
  | "complete"
  | "error";

type OrbVisual = {
  coreColor: string;
  glowColor: string;
  ringAnimation: string;
  coreAnimation: string;
};

const ORB_VISUALS: Record<VoiceOrbState, OrbVisual> = {
  offline: {
    coreColor: "bg-zinc-700",
    glowColor: "bg-zinc-600/20",
    ringAnimation: "",
    coreAnimation: "",
  },
  ready: {
    coreColor: "bg-indigo-600",
    glowColor: "bg-indigo-500/20",
    ringAnimation: "animate-pulse-signal",
    coreAnimation: "",
  },
  recording: {
    coreColor: "bg-emerald-500",
    glowColor: "bg-emerald-400/30",
    ringAnimation: "",
    coreAnimation: "",
  },
  stt: {
    coreColor: "bg-amber-500",
    glowColor: "bg-amber-400/25",
    ringAnimation: "animate-spin",
    coreAnimation: "animate-pulse",
  },
  thinking: {
    coreColor: "bg-violet-600",
    glowColor: "bg-violet-500/25",
    ringAnimation: "animate-orb-thinking",
    coreAnimation: "",
  },
  tts: {
    coreColor: "bg-cyan-500",
    glowColor: "bg-cyan-400/30",
    ringAnimation: "",
    coreAnimation: "",
  },
  complete: {
    coreColor: "bg-teal-500",
    glowColor: "bg-teal-400/20",
    ringAnimation: "animate-pulse",
    coreAnimation: "",
  },
  error: {
    coreColor: "bg-rose-600",
    glowColor: "bg-rose-500/20",
    ringAnimation: "",
    coreAnimation: "",
  },
};

type VoiceOrbProps = Readonly<{
  state: VoiceOrbState;
  inputLevel: number;
  outputLevel: number;
  disabled?: boolean;
  reducedMotion?: boolean;
  label?: string;
}>;

export function VoiceOrb({
  state,
  inputLevel,
  outputLevel,
  disabled = false,
  reducedMotion = false,
  label,
}: VoiceOrbProps) {
  const effectiveState: VoiceOrbState = disabled ? "offline" : state;
  const visual = ORB_VISUALS[effectiveState];

  const coreScale = useMemo(() => {
    if (reducedMotion) return 1;
    if (effectiveState === "recording") return 1 + Math.min(1, inputLevel) * 0.35;
    if (effectiveState === "tts") return 1 + Math.min(1, outputLevel) * 0.35;
    return 1;
  }, [effectiveState, inputLevel, outputLevel, reducedMotion]);

  const ringAnimation = reducedMotion ? "" : visual.ringAnimation;
  const coreAnimation = reducedMotion ? "" : visual.coreAnimation;
  const hasMotion = coreScale !== 1;

  return (
    <div
      role="img"
      aria-label={label ?? effectiveState}
      data-orb-state={effectiveState}
      className="flex flex-col items-center gap-3 py-2"
      style={{ minHeight: "160px" }}
    >
      <div
        className="relative flex items-center justify-center"
        style={{ width: 120, height: 120 }}
      >
        {/* Outer glow ring */}
        <div
          className={`absolute inset-0 rounded-full blur-2xl transition-colors duration-500 ${visual.glowColor} ${ringAnimation}`}
        />
        {/* Secondary ring for stt spin indicator */}
        {effectiveState === "stt" && !reducedMotion && (
          <div className="absolute inset-4 rounded-full border-2 border-amber-400/40 border-t-amber-400 animate-spin" />
        )}
        {/* Core orb */}
        <div
          data-testid="voice-orb-core"
          className={`relative rounded-full shadow-lg transition-colors duration-300 ${visual.coreColor} ${coreAnimation}`}
          style={{
            width: 72,
            height: 72,
            transform: `scale(${coreScale})`,
            willChange: hasMotion ? "transform" : undefined,
            transition: reducedMotion
              ? "background-color 300ms"
              : `transform 80ms linear, background-color 300ms`,
          }}
        />
      </div>
      <p className="text-xs text-zinc-400 tabular-nums">{label ?? effectiveState}</p>
    </div>
  );
}

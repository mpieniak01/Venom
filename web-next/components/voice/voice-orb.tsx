"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

import { OrbFrequencyRing } from "@/components/voice/orb-frequency-ring";
import { useAudioLevel } from "@/components/voice/use-audio-level";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";

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
  offline: { coreColor: "bg-zinc-700", glowColor: "bg-zinc-600/20", ringAnimation: "", coreAnimation: "" },
  ready: { coreColor: "bg-indigo-600", glowColor: "bg-indigo-500/20", ringAnimation: "animate-pulse-signal", coreAnimation: "" },
  recording: { coreColor: "bg-emerald-500", glowColor: "bg-emerald-400/30", ringAnimation: "", coreAnimation: "" },
  stt: { coreColor: "bg-amber-500", glowColor: "bg-amber-400/25", ringAnimation: "animate-spin", coreAnimation: "animate-pulse" },
  thinking: { coreColor: "bg-violet-600", glowColor: "bg-violet-500/25", ringAnimation: "animate-orb-thinking", coreAnimation: "" },
  tts: { coreColor: "bg-cyan-500", glowColor: "bg-cyan-400/30", ringAnimation: "", coreAnimation: "" },
  complete: { coreColor: "bg-teal-500", glowColor: "bg-teal-400/20", ringAnimation: "animate-pulse", coreAnimation: "" },
  error: { coreColor: "bg-rose-600", glowColor: "bg-rose-500/20", ringAnimation: "", coreAnimation: "" },
};

// Three-layer ambient glow: [inner, mid, outer] RGBA strings.
const ORB_GLOW: Record<VoiceOrbState, [string, string, string]> = {
  offline: ["rgba(113,113,122,0.08)", "rgba(113,113,122,0.03)", "transparent"],
  ready: ["rgba(99,102,241,0.38)", "rgba(99,102,241,0.13)", "rgba(99,102,241,0.04)"],
  recording: ["rgba(52,211,153,0.48)", "rgba(52,211,153,0.18)", "rgba(52,211,153,0.06)"],
  stt: ["rgba(251,191,36,0.38)", "rgba(251,191,36,0.13)", "rgba(251,191,36,0.04)"],
  thinking: ["rgba(139,92,246,0.48)", "rgba(139,92,246,0.18)", "rgba(139,92,246,0.06)"],
  tts: ["rgba(34,211,238,0.48)", "rgba(34,211,238,0.18)", "rgba(34,211,238,0.06)"],
  complete: ["rgba(20,184,166,0.38)", "rgba(20,184,166,0.13)", "rgba(20,184,166,0.04)"],
  error: ["rgba(225,29,72,0.38)", "rgba(225,29,72,0.13)", "rgba(225,29,72,0.04)"],
};

const FFT_RING_COLOR: Partial<Record<VoiceOrbState, string>> = {
  recording: "rgba(52,211,153,0.8)",
  tts: "rgba(34,211,238,0.8)",
};

const RIPPLE_COLORS: Partial<Record<VoiceOrbState, [string, string, string]>> = {
  recording: ["bg-emerald-400/25", "bg-emerald-400/18", "bg-emerald-400/10"],
  tts: ["bg-cyan-400/25", "bg-cyan-400/18", "bg-cyan-400/10"],
};

const PARTICLE_COLORS: Partial<Record<VoiceOrbState, string>> = {
  recording: "rgba(52,211,153,0.72)",
  tts: "rgba(34,211,238,0.72)",
};

const ORB_PARTICLE_COUNT = 9;
const ORB_PARTICLE_RANDOMS_PER_PARTICLE = 5;
const ORB_PARTICLE_RANDOM_FALLBACK = 0x80000000;
const ORB_PARTICLE_RANDOM_DENOMINATOR = 0x100000000;

const ORB_SIZE = 120;
const CORE_SIZE = 72;

type Particle = {
  id: number;
  angle: number;
  duration: number;
  delay: number;
  offset: number;
  size: number;
};

function getFlashClass(state: VoiceOrbState): string {
  return state === "recording" || state === "complete" ? "animate-orb-flash" : "";
}

function isOrbActive(state: VoiceOrbState): boolean {
  return state === "recording" || state === "tts";
}

function getOrbAudioLevel(state: VoiceOrbState, inputLevel: number, outputLevel: number): number {
  if (state === "recording") return inputLevel;
  if (state === "tts") return outputLevel;
  return 0;
}

function getOrbAnalyser(
  state: VoiceOrbState,
  micAnalyserRef: RefObject<AnalyserNode | null> | undefined,
  ttsAnalyserRef: RefObject<AnalyserNode | null> | undefined,
): RefObject<AnalyserNode | null> | undefined {
  if (state === "recording") return micAnalyserRef;
  if (state === "tts") return ttsAnalyserRef;
  return undefined;
}

function getOrbGlowShadow(
  enabled: boolean,
  noAnim: boolean,
  state: VoiceOrbState,
  audioLevel: number,
): string | undefined {
  if (!enabled || noAnim || state === "offline") return undefined;

  const [c1, c2, c3] = ORB_GLOW[state];
  const level = Math.min(1, audioLevel);
  const r1 = (16 + level * 18).toFixed(0);
  const r2 = (30 + level * 32).toFixed(0);
  const r3 = (52 + level * 62).toFixed(0);
  return `0 0 ${r1}px ${c1}, 0 0 ${r2}px ${c2}, 0 0 ${r3}px ${c3}`;
}

function shouldShowOrbEffect(enabled: boolean, noAnim: boolean, active: boolean): boolean {
  return enabled && !noAnim && active;
}

function getMotionClass(noAnim: boolean, className: string): string {
  return noAnim ? "" : className;
}

function formatCoreScale(scale: number): string {
  return scale === 1 ? "1" : scale.toFixed(4);
}

function randomUnitValues(count: number): number[] {
  const values = new Uint32Array(count);
  const crypto = globalThis.crypto;

  if (crypto) {
    crypto.getRandomValues(values);
  } else {
    values.fill(ORB_PARTICLE_RANDOM_FALLBACK);
  }

  return Array.from(values, (value) => value / ORB_PARTICLE_RANDOM_DENOMINATOR);
}

function createOrbParticles(): Particle[] {
  const randomValues = randomUnitValues(ORB_PARTICLE_COUNT * ORB_PARTICLE_RANDOMS_PER_PARTICLE);

  return Array.from({ length: ORB_PARTICLE_COUNT }, (_, index) => {
    const base = index * ORB_PARTICLE_RANDOMS_PER_PARTICLE;
    const angleJitter = randomValues[base] ?? 0.5;
    const durationJitter = randomValues[base + 1] ?? 0.5;
    const delayJitter = randomValues[base + 2] ?? 0.5;
    const offsetJitter = randomValues[base + 3] ?? 0.5;
    const sizeJitter = randomValues[base + 4] ?? 0.5;

    return {
      id: index,
      angle: (360 / ORB_PARTICLE_COUNT) * index + angleJitter * 20 - 10,
      duration: 1.6 + durationJitter * 0.9,
      delay: delayJitter * 1.1,
      offset: 30 + offsetJitter * 8,
      size: 2 + sizeJitter * 2,
    };
  });
}

function useOrbTransitionEffects(state: VoiceOrbState, enabled: boolean, noAnim: boolean) {
  const [flashClass, setFlashClass] = useState("");
  const [showBurst, setShowBurst] = useState(false);
  const [burstKey, setBurstKey] = useState(0);
  const prevStateRef = useRef<VoiceOrbState>(state);

  useEffect(() => {
    if (!enabled || noAnim || prevStateRef.current === state) return;

    prevStateRef.current = state;
    const cls = getFlashClass(state);
    if (!cls) return;

    let clearId: ReturnType<typeof setTimeout> | undefined;
    const startId = setTimeout(() => {
      setFlashClass(cls);
      clearId = setTimeout(() => setFlashClass(""), 350);
    }, 0);

    return () => {
      clearTimeout(startId);
      if (clearId !== undefined) {
        clearTimeout(clearId);
      }
    };
  }, [enabled, noAnim, state]);

  useEffect(() => {
    if (!enabled || noAnim || state !== "complete") return;

    let hideId: ReturnType<typeof setTimeout> | undefined;
    const startId = setTimeout(() => {
      setBurstKey((current) => current + 1);
      setShowBurst(true);
      hideId = setTimeout(() => setShowBurst(false), 650);
    }, 0);

    return () => {
      clearTimeout(startId);
      if (hideId !== undefined) {
        clearTimeout(hideId);
      }
    };
  }, [enabled, noAnim, state]);

  return { flashClass, showBurst, burstKey };
}

function useOrbParticles() {
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    const id = setTimeout(() => {
      setParticles(createOrbParticles());
    }, 0);

    return () => clearTimeout(id);
  }, []);

  return particles;
}

type VoiceOrbProps = Readonly<{
  state: VoiceOrbState;
  /** Override audio level - used in tests; omit in production (computed internally). */
  inputLevel?: number;
  outputLevel?: number;
  disabled?: boolean;
  reducedMotion?: boolean;
  label?: string;
  effectsConfig?: OrbEffectsConfig;
  micAnalyserRef?: RefObject<AnalyserNode | null>;
  ttsAnalyserRef?: RefObject<AnalyserNode | null>;
}>;

export function VoiceOrb({
  state,
  inputLevel: inputLevelProp,
  outputLevel: outputLevelProp,
  disabled = false,
  reducedMotion = false,
  label,
  effectsConfig,
  micAnalyserRef,
  ttsAnalyserRef,
}: VoiceOrbProps) {
  const effectiveState: VoiceOrbState = disabled ? "offline" : state;
  const visual = ORB_VISUALS[effectiveState];
  const noAnim = reducedMotion;
  const cfg = effectsConfig ?? {
    ripple: true,
    blob: true,
    glow: true,
    transitions: true,
    frequencyRing: true,
    coreTexture: true,
    particles: true,
    stateLabel: true,
  };

  // Audio level is computed here so the parent does not re-render at 60fps.
  const fallbackRef = useRef<AnalyserNode | null>(null);
  const inputLevelHook = useAudioLevel(micAnalyserRef ?? fallbackRef, effectiveState === "recording");
  const outputLevelHook = useAudioLevel(ttsAnalyserRef ?? fallbackRef, effectiveState === "tts");
  const inputLevel = inputLevelProp ?? inputLevelHook;
  const outputLevel = outputLevelProp ?? outputLevelHook;

  const audioLevel = getOrbAudioLevel(effectiveState, inputLevel, outputLevel);
  const activeAnalyser = getOrbAnalyser(effectiveState, micAnalyserRef, ttsAnalyserRef);
  const showParticles = shouldShowOrbEffect(cfg.particles, noAnim, isOrbActive(effectiveState));
  const showRipple = shouldShowOrbEffect(cfg.ripple, noAnim, isOrbActive(effectiveState));
  const showBlob = shouldShowOrbEffect(cfg.blob, noAnim, isOrbActive(effectiveState));
  const showFreqRing = shouldShowOrbEffect(cfg.frequencyRing, noAnim, activeAnalyser !== undefined);
  const particles = useOrbParticles();
  const { flashClass, showBurst, burstKey } = useOrbTransitionEffects(effectiveState, cfg.transitions, noAnim);

  const coreScale = noAnim ? 1 : 1 + Math.min(1, audioLevel) * 0.35;
  const hasMotion = coreScale !== 1;
  const glowShadow = getOrbGlowShadow(cfg.glow, noAnim, effectiveState, audioLevel);
  const ringAnimation = getMotionClass(noAnim, visual.ringAnimation);
  const coreAnimation = getMotionClass(noAnim, visual.coreAnimation);
  const blobClass = showBlob ? "animate-orb-blob" : "";
  const rippleColors = RIPPLE_COLORS[effectiveState];
  const particleColor = PARTICLE_COLORS[effectiveState] ?? "rgba(255,255,255,0.5)";
  const fftColor = FFT_RING_COLOR[effectiveState] ?? "transparent";

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
        style={{
          width: ORB_SIZE,
          height: ORB_SIZE,
          borderRadius: "50%",
          boxShadow: glowShadow,
          transition: "box-shadow 220ms ease",
        }}
      >
        {showRipple && rippleColors && (
          <>
            <div className={`absolute inset-0 rounded-full ${rippleColors[0]} animate-orb-ripple`} style={{ animationDelay: "0s" }} />
            <div className={`absolute inset-0 rounded-full ${rippleColors[1]} animate-orb-ripple`} style={{ animationDelay: "0.48s" }} />
            <div className={`absolute inset-0 rounded-full ${rippleColors[2]} animate-orb-ripple`} style={{ animationDelay: "0.96s" }} />
          </>
        )}

        <div className={`absolute inset-0 rounded-full blur-2xl transition-colors duration-500 ${visual.glowColor} ${ringAnimation}`} />

        {showFreqRing && activeAnalyser && (
          <OrbFrequencyRing analyserRef={activeAnalyser} active={showFreqRing} color={fftColor} size={ORB_SIZE} />
        )}

        {effectiveState === "stt" && !noAnim && (
          <div className="absolute inset-4 rounded-full border-2 border-amber-400/40 border-t-amber-400 animate-spin" />
        )}

        {showBurst && (
          <div
            key={burstKey}
            className="absolute inset-0 rounded-full border-2 border-teal-400/70 animate-orb-burst"
            style={{ pointerEvents: "none" }}
          />
        )}

        <div
          data-testid="voice-orb-core"
          className={`relative overflow-hidden rounded-full shadow-lg transition-colors duration-300 ${visual.coreColor} ${coreAnimation} ${blobClass} ${flashClass}`}
          style={{
            width: CORE_SIZE,
            height: CORE_SIZE,
            transform: `scale(${formatCoreScale(coreScale)})`,
            willChange: hasMotion ? "transform" : undefined,
            transition: noAnim
              ? "background-color 300ms, border-radius 400ms"
              : "transform 80ms linear, background-color 300ms, border-radius 400ms ease-in-out",
          }}
        >
          {cfg.coreTexture && (
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                background: "radial-gradient(circle at 33% 28%, rgba(255,255,255,0.22) 0%, transparent 58%)",
              }}
            />
          )}

          {cfg.coreTexture && !noAnim && (
            <>
              <div
                className="animate-orb-plasma-slow pointer-events-none absolute rounded-full opacity-[0.18]"
                style={{
                  width: "58%",
                  height: "58%",
                  top: "21%",
                  left: "21%",
                  border: "1px solid rgba(255,255,255,0.5)",
                }}
              />
              <div
                className="animate-orb-plasma-fast pointer-events-none absolute rounded-full opacity-[0.13]"
                style={{
                  width: "80%",
                  height: "80%",
                  top: "10%",
                  left: "10%",
                  border: "1px solid rgba(255,255,255,0.3)",
                }}
              />
            </>
          )}
        </div>

        {showParticles &&
          particles.map((particle) => {
            const rad = (particle.angle * Math.PI) / 180;
            const x = ORB_SIZE / 2 + particle.offset * Math.cos(rad);
            const y = ORB_SIZE / 2 + particle.offset * Math.sin(rad);
            return (
              <div
                key={particle.id}
                className="pointer-events-none absolute rounded-full animate-orb-particle-rise"
                style={{
                  width: particle.size,
                  height: particle.size,
                  left: x - particle.size / 2,
                  top: y - particle.size / 2,
                  backgroundColor: particleColor,
                  animationDuration: `${particle.duration.toFixed(2)}s`,
                  animationDelay: `${particle.delay.toFixed(2)}s`,
                }}
              />
            );
          })}
      </div>

      {cfg.stateLabel && (
        <p
          key={effectiveState}
          className="animate-fade-in text-xs text-zinc-400 tabular-nums transition-opacity duration-300"
        >
          {label ?? effectiveState}
        </p>
      )}
    </div>
  );
}

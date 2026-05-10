"use client";

import { RefObject, useEffect, useRef, useState } from "react";

import { useAudioLevel } from "@/components/voice/use-audio-level";
import { OrbFrequencyRing } from "@/components/voice/orb-frequency-ring";
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
  offline:   { coreColor: "bg-zinc-700",    glowColor: "bg-zinc-600/20",    ringAnimation: "",                    coreAnimation: "" },
  ready:     { coreColor: "bg-indigo-600",  glowColor: "bg-indigo-500/20",  ringAnimation: "animate-pulse-signal", coreAnimation: "" },
  recording: { coreColor: "bg-emerald-500", glowColor: "bg-emerald-400/30", ringAnimation: "",                    coreAnimation: "" },
  stt:       { coreColor: "bg-amber-500",   glowColor: "bg-amber-400/25",   ringAnimation: "animate-spin",        coreAnimation: "animate-pulse" },
  thinking:  { coreColor: "bg-violet-600",  glowColor: "bg-violet-500/25",  ringAnimation: "animate-orb-thinking", coreAnimation: "" },
  tts:       { coreColor: "bg-cyan-500",    glowColor: "bg-cyan-400/30",    ringAnimation: "",                    coreAnimation: "" },
  complete:  { coreColor: "bg-teal-500",    glowColor: "bg-teal-400/20",    ringAnimation: "animate-pulse",       coreAnimation: "" },
  error:     { coreColor: "bg-rose-600",    glowColor: "bg-rose-500/20",    ringAnimation: "",                    coreAnimation: "" },
};

// Three-layer ambient glow: [inner, mid, outer] RGBA strings
const ORB_GLOW: Record<VoiceOrbState, [string, string, string]> = {
  offline:   ["rgba(113,113,122,0.08)", "rgba(113,113,122,0.03)", "transparent"],
  ready:     ["rgba(99,102,241,0.38)",  "rgba(99,102,241,0.13)", "rgba(99,102,241,0.04)"],
  recording: ["rgba(52,211,153,0.48)",  "rgba(52,211,153,0.18)", "rgba(52,211,153,0.06)"],
  stt:       ["rgba(251,191,36,0.38)",  "rgba(251,191,36,0.13)", "rgba(251,191,36,0.04)"],
  thinking:  ["rgba(139,92,246,0.48)",  "rgba(139,92,246,0.18)", "rgba(139,92,246,0.06)"],
  tts:       ["rgba(34,211,238,0.48)",  "rgba(34,211,238,0.18)", "rgba(34,211,238,0.06)"],
  complete:  ["rgba(20,184,166,0.38)",  "rgba(20,184,166,0.13)", "rgba(20,184,166,0.04)"],
  error:     ["rgba(225,29,72,0.38)",   "rgba(225,29,72,0.13)",  "rgba(225,29,72,0.04)"],
};

const FFT_RING_COLOR: Partial<Record<VoiceOrbState, string>> = {
  recording: "rgba(52,211,153,0.8)",
  tts:       "rgba(34,211,238,0.8)",
};

const RIPPLE_COLORS: Partial<Record<VoiceOrbState, [string, string, string]>> = {
  recording: ["bg-emerald-400/25", "bg-emerald-400/18", "bg-emerald-400/10"],
  tts:       ["bg-cyan-400/25",    "bg-cyan-400/18",    "bg-cyan-400/10"],
};

const PARTICLE_COLORS: Partial<Record<VoiceOrbState, string>> = {
  recording: "rgba(52,211,153,0.72)",
  tts:       "rgba(34,211,238,0.72)",
};

type Particle = {
  id: number;
  angle: number;
  duration: number;
  delay: number;
  offset: number;
  size: number;
};

const DEFAULT_EFFECTS: OrbEffectsConfig = {
  ripple: true, blob: true, glow: true, transitions: true,
  frequencyRing: true, coreTexture: true, particles: true, stateLabel: true,
};

const ORB_SIZE = 120;
const CORE_SIZE = 72;

type VoiceOrbProps = Readonly<{
  state: VoiceOrbState;
  /** Override audio level — used in tests; omit in production (computed internally). */
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
  const cfg = effectsConfig ?? DEFAULT_EFFECTS;
  const effectiveState: VoiceOrbState = disabled ? "offline" : state;
  const visual = ORB_VISUALS[effectiveState];
  const noAnim = reducedMotion;

  // ── Audio level (computed here to avoid 60fps re-renders in parent) ──
  // inputLevelProp / outputLevelProp are accepted as test overrides; in
  // production the parent passes analyserRefs instead and omits these.
  const fallbackRef = useRef<AnalyserNode | null>(null);
  const inputLevelHook  = useAudioLevel(micAnalyserRef ?? fallbackRef, effectiveState === "recording");
  const outputLevelHook = useAudioLevel(ttsAnalyserRef ?? fallbackRef, effectiveState === "tts");
  const inputLevel  = inputLevelProp  ?? inputLevelHook;
  const outputLevel = outputLevelProp ?? outputLevelHook;

  const audioLevel =
    effectiveState === "recording" ? inputLevel
    : effectiveState === "tts"     ? outputLevel
    : 0;

  // ── Transition flash on state change ─────────────────────────────────
  const [flashClass, setFlashClass] = useState("");
  const prevStateRef = useRef<VoiceOrbState>(effectiveState);

  useEffect(() => {
    if (!cfg.transitions || noAnim) return;
    if (prevStateRef.current === effectiveState) return;
    prevStateRef.current = effectiveState;

    const cls =
      effectiveState === "recording" || effectiveState === "complete"
        ? "animate-orb-flash"
        : "";
    if (!cls) return;

    let clearId: ReturnType<typeof setTimeout>;
    const startId = setTimeout(() => {
      setFlashClass(cls);
      clearId = setTimeout(() => setFlashClass(""), 350);
    }, 0);
    return () => { clearTimeout(startId); clearTimeout(clearId); };
  }, [effectiveState, cfg.transitions, noAnim]);

  // ── Complete burst (one-shot ring that expands then vanishes) ─────────
  const [showBurst, setShowBurst] = useState(false);
  const [burstKey, setBurstKey] = useState(0);

  useEffect(() => {
    if (!cfg.transitions || noAnim || effectiveState !== "complete") return;
    let hideId: ReturnType<typeof setTimeout>;
    const startId = setTimeout(() => {
      setBurstKey((k) => k + 1);
      setShowBurst(true);
      hideId = setTimeout(() => setShowBurst(false), 650);
    }, 0);
    return () => { clearTimeout(startId); clearTimeout(hideId); };
  }, [effectiveState, cfg.transitions, noAnim]);

  // ── Particles (generated client-side to avoid SSR mismatch) ──────────
  const [particles, setParticles] = useState<Particle[]>([]);

  useEffect(() => {
    const id = setTimeout(() => {
      setParticles(
        Array.from({ length: 9 }, (_, i) => ({
          id: i,
          angle: (360 / 9) * i + Math.random() * 20 - 10,
          duration: 1.6 + Math.random() * 0.9,
          delay: Math.random() * 1.1,
          offset: 30 + Math.random() * 8,
          size: 2 + Math.random() * 2,
        }))
      );
    }, 0);
    return () => clearTimeout(id);
  }, []);

  const showParticles =
    !noAnim && cfg.particles &&
    (effectiveState === "recording" || effectiveState === "tts");

  // ── Derived booleans ─────────────────────────────────────────────────
  const showRipple =
    !noAnim && cfg.ripple &&
    (effectiveState === "recording" || effectiveState === "tts");

  const showBlob =
    !noAnim && cfg.blob &&
    (effectiveState === "recording" || effectiveState === "tts");

  const activeAnalyser =
    effectiveState === "recording" ? micAnalyserRef
    : effectiveState === "tts"     ? ttsAnalyserRef
    : undefined;

  const showFreqRing =
    !noAnim && cfg.frequencyRing && !!activeAnalyser &&
    (effectiveState === "recording" || effectiveState === "tts");

  // ── Core scale ───────────────────────────────────────────────────────
  const coreScale = noAnim ? 1 : 1 + Math.min(1, audioLevel) * 0.35;
  const hasMotion = coreScale !== 1;

  // ── Ambient glow box-shadow (3 layers, audio-reactive) ───────────────
  // Not memoized: depends on audioLevel which updates every animation frame,
  // so memo overhead exceeds any benefit.
  let glowShadow: string | undefined;
  if (cfg.glow && !noAnim && effectiveState !== "offline") {
    const [c1, c2, c3] = ORB_GLOW[effectiveState];
    const l = Math.min(1, audioLevel);
    const r1 = (16 + l * 18).toFixed(0);
    const r2 = (30 + l * 32).toFixed(0);
    const r3 = (52 + l * 62).toFixed(0);
    glowShadow = `0 0 ${r1}px ${c1}, 0 0 ${r2}px ${c2}, 0 0 ${r3}px ${c3}`;
  }

  const ringAnimation = noAnim ? "" : visual.ringAnimation;
  const coreAnimation = noAnim ? "" : visual.coreAnimation;
  const blobClass     = showBlob ? "animate-orb-blob" : "";
  const rippleColors  = RIPPLE_COLORS[effectiveState];
  const particleColor = PARTICLE_COLORS[effectiveState] ?? "rgba(255,255,255,0.5)";
  const fftColor      = FFT_RING_COLOR[effectiveState] ?? "transparent";

  return (
    <div
      role="img"
      aria-label={label ?? effectiveState}
      data-orb-state={effectiveState}
      className="flex flex-col items-center gap-3 py-2"
      style={{ minHeight: "160px" }}
    >
      {/* ── Container ── */}
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
        {/* ── Ripple rings ── */}
        {showRipple && rippleColors && (
          <>
            <div className={`absolute inset-0 rounded-full ${rippleColors[0]} animate-orb-ripple`} style={{ animationDelay: "0s" }} />
            <div className={`absolute inset-0 rounded-full ${rippleColors[1]} animate-orb-ripple`} style={{ animationDelay: "0.48s" }} />
            <div className={`absolute inset-0 rounded-full ${rippleColors[2]} animate-orb-ripple`} style={{ animationDelay: "0.96s" }} />
          </>
        )}

        {/* ── Base glow ring ── */}
        <div
          className={`absolute inset-0 rounded-full blur-2xl transition-colors duration-500 ${visual.glowColor} ${ringAnimation}`}
        />

        {/* ── FFT frequency ring ── */}
        {showFreqRing && activeAnalyser && (
          <OrbFrequencyRing
            analyserRef={activeAnalyser}
            active={showFreqRing}
            color={fftColor}
            size={ORB_SIZE}
          />
        )}

        {/* ── STT spinning border ── */}
        {effectiveState === "stt" && !noAnim && (
          <div className="absolute inset-4 rounded-full border-2 border-amber-400/40 border-t-amber-400 animate-spin" />
        )}

        {/* ── Complete burst ring (one-shot) ── */}
        {showBurst && (
          <div
            key={burstKey}
            className="absolute inset-0 rounded-full border-2 border-teal-400/70 animate-orb-burst"
            style={{ pointerEvents: "none" }}
          />
        )}

        {/* ── Core orb ── */}
        <div
          data-testid="voice-orb-core"
          className={`relative overflow-hidden rounded-full shadow-lg transition-colors duration-300 ${visual.coreColor} ${coreAnimation} ${blobClass} ${flashClass}`}
          style={{
            width: CORE_SIZE,
            height: CORE_SIZE,
            transform: `scale(${parseFloat(coreScale.toFixed(4))})`,
            willChange: hasMotion ? "transform" : undefined,
            transition: noAnim
              ? "background-color 300ms, border-radius 400ms"
              : "transform 80ms linear, background-color 300ms, border-radius 400ms ease-in-out",
          }}
        >
          {/* Specular highlight (3D gloss effect) */}
          {cfg.coreTexture && (
            <div
              className="pointer-events-none absolute inset-0"
              style={{
                background:
                  "radial-gradient(circle at 33% 28%, rgba(255,255,255,0.22) 0%, transparent 58%)",
              }}
            />
          )}
          {/* Plasma inner rings */}
          {cfg.coreTexture && !noAnim && (
            <>
              <div
                className="animate-orb-plasma-slow pointer-events-none absolute rounded-full opacity-[0.18]"
                style={{
                  width: "58%", height: "58%",
                  top: "21%", left: "21%",
                  border: "1px solid rgba(255,255,255,0.5)",
                }}
              />
              <div
                className="animate-orb-plasma-fast pointer-events-none absolute rounded-full opacity-[0.13]"
                style={{
                  width: "80%", height: "80%",
                  top: "10%", left: "10%",
                  border: "1px solid rgba(255,255,255,0.3)",
                }}
              />
            </>
          )}
        </div>

        {/* ── Particles ── */}
        {showParticles && particles.map((p) => {
          const rad = (p.angle * Math.PI) / 180;
          const x = ORB_SIZE / 2 + p.offset * Math.cos(rad);
          const y = ORB_SIZE / 2 + p.offset * Math.sin(rad);
          return (
            <div
              key={p.id}
              className="pointer-events-none absolute rounded-full animate-orb-particle-rise"
              style={{
                width: p.size,
                height: p.size,
                left: x - p.size / 2,
                top: y - p.size / 2,
                backgroundColor: particleColor,
                animationDuration: `${p.duration.toFixed(2)}s`,
                animationDelay: `${p.delay.toFixed(2)}s`,
              }}
            />
          );
        })}
      </div>

      {/* ── State label ── */}
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

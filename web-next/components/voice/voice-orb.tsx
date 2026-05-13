"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

import { OrbFrequencyRing } from "@/components/voice/orb-frequency-ring";
import { shouldRenderOrbMetricsBars } from "@/components/voice/orb-visibility";
import { useAudioLevel } from "@/components/voice/use-audio-level";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import type { OrbMetrics } from "@/components/voice/use-orb-metrics";

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
  ready: { coreColor: "bg-indigo-600", glowColor: "bg-indigo-500/12", ringAnimation: "", coreAnimation: "" },
  recording: { coreColor: "bg-emerald-500", glowColor: "bg-emerald-400/30", ringAnimation: "", coreAnimation: "" },
  stt: { coreColor: "bg-amber-500", glowColor: "bg-amber-400/25", ringAnimation: "animate-spin", coreAnimation: "animate-pulse" },
  thinking: { coreColor: "bg-violet-600", glowColor: "bg-violet-500/25", ringAnimation: "animate-orb-thinking", coreAnimation: "" },
  tts: { coreColor: "bg-cyan-500", glowColor: "bg-cyan-400/30", ringAnimation: "", coreAnimation: "" },
  complete: { coreColor: "bg-teal-500", glowColor: "bg-teal-400/12", ringAnimation: "animate-pulse", coreAnimation: "" },
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
  const calm = state === "ready" || state === "complete";
  const base1 = calm ? 8 : 16;
  const base2 = calm ? 16 : 30;
  const base3 = calm ? 0 : 52;
  const scale1 = calm ? 8 : 18;
  const scale2 = calm ? 16 : 32;
  const scale3 = calm ? 0 : 62;
  const r1 = (base1 + level * scale1).toFixed(0);
  const r2 = (base2 + level * scale2).toFixed(0);
  if (calm) {
    return `0 0 ${r1}px ${c1}, 0 0 ${r2}px ${c2}`;
  }
  const r3 = (base3 + level * scale3).toFixed(0);
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

// ─── Metrics arcs — 4 quarter-circle arcs floating outward from the orb ──────

const ARC_DEFS = [
  { key: "cpu" as keyof OrbMetrics, color: "#f97316", startDeg:  45, endDeg: 135 }, // top
  { key: "gpu" as keyof OrbMetrics, color: "#a855f7", startDeg: -45, endDeg:  45 }, // right
  { key: "vram" as keyof OrbMetrics, color: "#22d3ee", startDeg: 135, endDeg: 225 }, // left
  { key: "ram" as keyof OrbMetrics, color: "#4ade80", startDeg: 225, endDeg: 315 }, // bottom
] as const;

const MONO_METRIC_COLOR = "#6b7280";

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number): string {
  const s  = (startDeg * Math.PI) / 180;
  const e  = (endDeg   * Math.PI) / 180;
  const x1 = cx + r * Math.cos(s);
  const y1 = cy - r * Math.sin(s);
  const x2 = cx + r * Math.cos(e);
  const y2 = cy - r * Math.sin(e);
  // sweep-flag=0: counter-clockwise in SVG, draws the short arc through the quadrant centre
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r.toFixed(2)} ${r.toFixed(2)} 0 0 0 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

function sectorPath(
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
  startDeg: number,
  endDeg: number,
): string {
  const s = (startDeg * Math.PI) / 180;
  const e = (endDeg * Math.PI) / 180;
  const x1 = cx + outerR * Math.cos(s);
  const y1 = cy - outerR * Math.sin(s);
  const x2 = cx + outerR * Math.cos(e);
  const y2 = cy - outerR * Math.sin(e);
  const ix2 = cx + innerR * Math.cos(e);
  const iy2 = cy - innerR * Math.sin(e);
  const ix1 = cx + innerR * Math.cos(s);
  const iy1 = cy - innerR * Math.sin(s);
  return [
    `M ${cx.toFixed(2)} ${cy.toFixed(2)}`,
    `L ${x1.toFixed(2)} ${y1.toFixed(2)}`,
    `A ${outerR.toFixed(2)} ${outerR.toFixed(2)} 0 0 0 ${x2.toFixed(2)} ${y2.toFixed(2)}`,
    `L ${ix2.toFixed(2)} ${iy2.toFixed(2)}`,
    `A ${innerR.toFixed(2)} ${innerR.toFixed(2)} 0 0 1 ${ix1.toFixed(2)} ${iy1.toFixed(2)}`,
    "Z",
  ].join(" ");
}

type OrbMetricsBars2DProps = Readonly<{
  metricsRef: RefObject<OrbMetrics>;
  orbSize: number;
  colorMode: boolean;
}>;

function OrbMetricsBars2D({ metricsRef, orbSize, colorMode }: OrbMetricsBars2DProps) {
  const sectorRefs = useRef<Array<SVGPathElement | null>>([null, null, null, null]);
  const coreRefs   = useRef<Array<SVGPathElement | null>>([null, null, null, null]);
  const glowRefs   = useRef<Array<SVGPathElement | null>>([null, null, null, null]);
  const rippleRefs = useRef<Array<SVGPathElement | null>>([null, null, null, null]);
  const currents   = useRef([0, 0, 0, 0]);
  const prevRadii  = useRef<number[]>([]);
  const rippleSt   = useRef([0, 0, 0, 0]);
  const lastTickRef = useRef(0);

  useEffect(() => {
    const cx     = orbSize / 2;
    const cy     = orbSize / 2;
    const ORB_R  = orbSize / 2;
    const SECTOR_INNER_R = ORB_R * 0.84;
    const MIN_R  = ORB_R * 1.08; // just outside the orb edge
    const MAX_R  = ORB_R * 1.95; // fully loaded: arcs nearly double the orb radius
    const PHASES = [0, Math.PI * 0.5, Math.PI, Math.PI * 1.5]; // 90° stagger per arc
    const TICK_MS = 40;

    currents.current  = [MIN_R, MIN_R, MIN_R, MIN_R];
    prevRadii.current = [MIN_R, MIN_R, MIN_R, MIN_R];
    lastTickRef.current = 0;

    let rafId = 0;

    const tick = (now: number) => {
      if (now - lastTickRef.current < TICK_MS) {
        rafId = requestAnimationFrame(tick);
        return;
      }
      lastTickRef.current = now;

      const t    = now / 1000;
      const m    = metricsRef.current;
      const vals = [m.cpu, m.gpu, m.vram, m.ram];

      currents.current = currents.current.map((c, i) => {
        const pct = Number.isFinite(vals[i] ?? Number.NaN) ? (vals[i] as number) : 0;
        const tgt = MIN_R + (pct / 100) * (MAX_R - MIN_R);
        return c + (tgt - c) * 0.12;
      });

      currents.current.forEach((r, i) => {
        const def = ARC_DEFS[i];
        if (!def) return;
        const pctValue = Number.isFinite(vals[i] ?? Number.NaN) ? (vals[i] as number) : 0;
        const loadPct = Math.max(0, Math.min(1, pctValue / 100));
        const pct = Math.max(0, Math.min(1, (r - MIN_R) / (MAX_R - MIN_R)));
        const breathPhase = t * 2.1 + (PHASES[i] ?? 0);
        const breathe = Math.sin(breathPhase);
        const effR = r + breathe * orbSize * 0.012;
        const sw = 1.8 + 3.8 * pct + breathe * (0.8 + 1.2 * pct);
        const opa = 0.35 + 0.65 * Math.max(pct, loadPct);
        const d = arcPath(cx, cy, Math.max(MIN_R * 0.95, effR), def.startDeg, def.endDeg);
        const sectorOuter = Math.max(MIN_R * 0.98, effR + orbSize * 0.02);
        const sectorOpacity = 0.14 + 0.18 * Math.max(pct, loadPct);
        const sector = sectorRefs.current[i];
        if (sector) {
          sector.setAttribute("d", sectorPath(cx, cy, SECTOR_INNER_R, sectorOuter, def.startDeg, def.endDeg));
          sector.setAttribute("fill", colorMode ? def.color : MONO_METRIC_COLOR);
          sector.setAttribute("fill-opacity", String(sectorOpacity.toFixed(3)));
          sector.setAttribute("stroke", "none");
        }

        const core = coreRefs.current[i];
        if (core) {
          core.setAttribute("d",            d);
          core.setAttribute("stroke-width", String(Math.max(1.2, sw).toFixed(2)));
          core.setAttribute("opacity",      String(opa.toFixed(3)));
        }

        const glow = glowRefs.current[i];
        if (glow) {
          glow.setAttribute("d",            d);
          glow.setAttribute("stroke-width", String(Math.max(4, sw * 3.5).toFixed(2)));
          glow.setAttribute("opacity",      String((0.1 + 0.22 * Math.max(pct, loadPct)).toFixed(3)));
        }

        // Ripple arc: spawns when radius spikes (load surge)
        const prev = prevRadii.current[i] ?? MIN_R;
        const rp   = rippleSt.current[i] ?? 0;
        if (r - prev > (MAX_R - MIN_R) * 0.06 && Math.max(pct, loadPct) > 0.15 && rp === 0) {
          rippleSt.current[i] = 1;
        }
        prevRadii.current[i] = r;

        const ripple = rippleRefs.current[i];
        if (ripple) {
          if (rp > 0) {
            const rOuter = effR + (1 - rp) * orbSize * 0.28;
            ripple.setAttribute("d",            arcPath(cx, cy, Math.max(MIN_R, rOuter), def.startDeg, def.endDeg));
            ripple.setAttribute("stroke-width", "2");
            ripple.setAttribute("opacity",      String((rp * 0.65).toFixed(3)));
            rippleSt.current[i] = Math.max(0, rp - 0.05);
          } else {
            ripple.setAttribute("opacity", "0");
          }
        }
      });

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      globalThis.cancelAnimationFrame(rafId);
    };
  }, [colorMode, metricsRef, orbSize]);

  return (
    <svg
      style={{
        position: "absolute",
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -50%)",
        pointerEvents: "none",
        overflow: "visible",
      }}
      width={orbSize}
      height={orbSize}
      aria-hidden="true"
    >
      <defs>
        <filter id="orb-arc-glow" x="-200%" y="-200%" width="500%" height="500%">
          <feGaussianBlur stdDeviation="3.0" in="SourceGraphic" />
        </filter>
      </defs>

      {/* Filled quarter sectors — translucent outer layer */}
      {ARC_DEFS.map(({ key, color }, i) => (
        <path
          key={`s-${key}`}
          ref={(el) => { sectorRefs.current[i] = el; }}
          fill={colorMode ? color : MONO}
          fillOpacity={0.14}
          stroke="none"
        />
      ))}

      {/* Glow bloom — wide blurred arc copies */}
      {ARC_DEFS.map(({ key, color }, i) => (
        <path
          key={`g-${key}`}
          ref={(el) => { glowRefs.current[i] = el; }}
          fill="none"
        stroke={colorMode ? color : MONO_METRIC_COLOR}
          strokeLinecap="round"
          filter="url(#orb-arc-glow)"
        />
      ))}

      {/* Core arcs */}
      {ARC_DEFS.map(({ key, color }, i) => (
        <path
          key={`c-${key}`}
          ref={(el) => { coreRefs.current[i] = el; }}
          fill="none"
        stroke={colorMode ? color : MONO_METRIC_COLOR}
          strokeLinecap="round"
        />
      ))}

      {/* Ripple arcs that expand outward on load surge */}
      {ARC_DEFS.map(({ key, color }, i) => (
        <path
          key={`r-${key}`}
          ref={(el) => { rippleRefs.current[i] = el; }}
          fill="none"
        stroke={colorMode ? color : MONO_METRIC_COLOR}
          strokeLinecap="round"
          opacity={0}
        />
      ))}
    </svg>
  );
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
  metricsRef?: RefObject<OrbMetrics>;
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
  metricsRef,
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
    orbMetricsBars: false,
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
  const showMetricsBars = shouldRenderOrbMetricsBars(Boolean(cfg.orbMetricsBars && metricsRef), effectiveState, noAnim);
  const showAmbientMotion = !noAnim && effectiveState !== "ready" && effectiveState !== "offline";

  const coreScale = noAnim ? 1 : 1 + Math.min(1, audioLevel) * 0.35;
  const hasMotion = coreScale !== 1;
  const glowShadow = getOrbGlowShadow(cfg.glow, noAnim, effectiveState, audioLevel);
  const ringAnimation = showAmbientMotion ? getMotionClass(noAnim, visual.ringAnimation) : "";
  const coreAnimation = getMotionClass(noAnim, visual.coreAnimation);
  const blobClass = showBlob ? "animate-orb-blob" : "";
  const rippleColors = RIPPLE_COLORS[effectiveState];
  const particleColor = PARTICLE_COLORS[effectiveState] ?? "rgba(255,255,255,0.5)";
  const fftColor = FFT_RING_COLOR[effectiveState] ?? "transparent";
  const glowClassName = effectiveState === "ready" || effectiveState === "complete" ? "blur-lg" : "blur-2xl";

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

        {cfg.glow && (
          <div className={`absolute inset-0 rounded-full ${glowClassName} transition-colors duration-500 ${visual.glowColor} ${ringAnimation}`} />
        )}

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

          {cfg.coreTexture && showAmbientMotion && (
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

        {showMetricsBars && (
          <OrbMetricsBars2D metricsRef={metricsRef} orbSize={ORB_SIZE} colorMode />
        )}
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

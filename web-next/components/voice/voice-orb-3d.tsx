"use client";

import { useEffect, useMemo, useRef } from "react";
import type { MutableRefObject, RefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment } from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";
import type { VoiceOrbState } from "@/components/voice/voice-orb";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import { useAudioLevel } from "@/components/voice/use-audio-level";
import type { OrbMetrics } from "@/components/voice/use-orb-metrics";

// ─── State color palette (matches CSS orb palette) ──────────────────────────

type StateColors = { base: THREE.Color; emission: THREE.Color };

const STATE_COLORS: Record<VoiceOrbState, StateColors> = {
  offline:   { base: new THREE.Color("#3f3f46"), emission: new THREE.Color("#3f3f46") },
  ready:     { base: new THREE.Color("#4f46e5"), emission: new THREE.Color("#6366f1") },
  recording: { base: new THREE.Color("#059669"), emission: new THREE.Color("#10b981") },
  stt:       { base: new THREE.Color("#d97706"), emission: new THREE.Color("#f59e0b") },
  thinking:  { base: new THREE.Color("#6d28d9"), emission: new THREE.Color("#7c3aed") },
  tts:       { base: new THREE.Color("#0891b2"), emission: new THREE.Color("#06b6d4") },
  complete:  { base: new THREE.Color("#0f766e"), emission: new THREE.Color("#14b8a6") },
  error:     { base: new THREE.Color("#be123c"), emission: new THREE.Color("#e11d48") },
};

// ─── GLSL shaders ───────────────────────────────────────────────────────────

const vertexShader = /* glsl */ `
  uniform sampler2D fftTexture;
  uniform float audioLevel;
  uniform float time;
  uniform float blobEnabled;
  uniform float fftEnabled;

  varying vec3 vNormal;
  varying vec3 vWorldPos;

  void main() {
    vec3 pos = position;

    // Organic blob morphing via multi-frequency sine waves
    if (blobEnabled > 0.5) {
      float w1 = sin(position.y * 4.0 + time * 1.2) * 0.5 + 0.5;
      float w2 = sin(position.x * 3.0 + time * 0.85) * 0.5 + 0.5;
      float w3 = cos(position.z * 5.0 + time * 1.55) * 0.5 + 0.5;
      float blob = w1 * 0.4 + w2 * 0.35 + w3 * 0.25;
      pos += normal * blob * audioLevel * 0.18;
    }

    // FFT-driven radial displacement
    if (fftEnabled > 0.5) {
      float azimuth = atan(position.y, position.x);
      float u = (azimuth + 3.14159265) / (2.0 * 3.14159265);
      float fftVal = texture2D(fftTexture, vec2(u, 0.5)).r;
      pos += normal * fftVal * audioLevel * 0.22;
    }

    vNormal = normalize(normalMatrix * normal);
    vec4 worldPos4 = modelMatrix * vec4(pos, 1.0);
    vWorldPos = worldPos4.xyz;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
  }
`;

const fragmentShader = /* glsl */ `
  uniform vec3 baseColor;
  uniform vec3 emissionColor;
  uniform float emissionIntensity;
  uniform float iridescenceEnabled;

  varying vec3 vNormal;
  varying vec3 vWorldPos;

  void main() {
    vec3 viewDir = normalize(cameraPosition - vWorldPos);
    float NdotV = max(dot(vNormal, viewDir), 0.0);
    float fresnel = pow(1.0 - NdotV, 3.0);

    vec3 color = baseColor;

    // Iridescence: channel-rotate based on Fresnel angle
    if (iridescenceEnabled > 0.5) {
      float t = fresnel * 0.5;
      vec3 shifted = vec3(
        mix(color.r, color.b, t),
        mix(color.g, color.r, t * 0.7),
        mix(color.b, color.g, t * 0.5)
      );
      color = mix(color, shifted, fresnel * 0.55);
    }

    // Emission + rim
    color += emissionColor * emissionIntensity;
    color += emissionColor * fresnel * 0.35;

    // Specular highlight (fake top-left)
    float spec = pow(max(dot(vNormal, normalize(vec3(0.6, 0.8, 1.0))), 0.0), 28.0);
    color += vec3(spec * 0.25);

    gl_FragColor = vec4(color, 1.0);
  }
`;

// ─── Metrics bars 3D ────────────────────────────────────────────────────────

const MAX_BAR_RADIUS = 2.2;  // extends visibly beyond orb sphere (radius ~0.62)
const MIN_BAR_SCALE = 0.08;
const BAR_LERP_ALPHA = 0.07;

const BAR_DEFS: Array<{
  key: keyof OrbMetrics;
  color: string;
  rotation: [number, number, number];
}> = [
  { key: "cpu", color: "#f97316", rotation: [0, 0, 0] },              // UP   (+Y)
  { key: "gpu", color: "#a855f7", rotation: [0, 0, -Math.PI / 2] },   // RIGHT (+X)
  { key: "net", color: "#4ade80", rotation: [0, 0, Math.PI] },        // DOWN  (-Y)
  { key: "ram", color: "#22d3ee", rotation: [0, 0, Math.PI / 2] },    // LEFT  (-X)
];

// BoxGeometry with translate(0, 0.5, 0): bottom at Y=0 → scales grow outward.
function makeBarGeometry() {
  const geo = new THREE.BoxGeometry(0.055, 1, 0.055);
  geo.translate(0, 0.5, 0);
  return geo;
}

// Wider secondary "glow" geometry
function makeGlowGeometry() {
  const geo = new THREE.BoxGeometry(0.18, 1, 0.055);
  geo.translate(0, 0.5, 0);
  return geo;
}

type OrbMetricsBars3DProps = Readonly<{
  metricsRef: RefObject<OrbMetrics>;
}>;

type OrbMetricBarRefs = Readonly<{
  groupRef: RefObject<THREE.Group | null>;
  coreRef: RefObject<THREE.Mesh | null>;
  glowRef: RefObject<THREE.Mesh | null>;
  coreMaterialRef: RefObject<THREE.MeshStandardMaterial | null>;
  glowMaterialRef: RefObject<THREE.MeshStandardMaterial | null>;
}>;

function syncBarMaterial(
  mat: THREE.MeshStandardMaterial | null,
  color: string,
  emissiveIntensity: number,
  opacity: number,
) {
  if (!mat) return;
  mat.color.set(color);
  mat.emissive.set(color);
  mat.emissiveIntensity = emissiveIntensity;
  mat.transparent = true;
  mat.opacity = opacity;
  mat.depthWrite = false;
}

function syncOrbMetricBarFrame(
  index: number,
  metricsRef: RefObject<OrbMetrics>,
  refs: OrbMetricBarRefs,
) {
  const metrics = metricsRef.current;
  if (!metrics) return;
  const rawValue = [metrics.cpu, metrics.gpu, metrics.net, metrics.ram][index];
  const pct = Number.isFinite(rawValue) ? rawValue : 0;
  const isGpuAbsent = index === 1 && !Number.isFinite(rawValue);
  const target = MIN_BAR_SCALE + (pct / 100) * (MAX_BAR_RADIUS - MIN_BAR_SCALE);

  const core = refs.coreRef.current;
  if (core) {
    core.scale.y += (target - core.scale.y) * BAR_LERP_ALPHA;
    syncBarMaterial(
      refs.coreMaterialRef.current,
      BAR_DEFS[index]?.color ?? "#ffffff",
      isGpuAbsent ? 0.04 : 0.35 + 0.65 * (pct / 100),
      isGpuAbsent ? 0.2 : 0.92,
    );
  }

  const glow = refs.glowRef.current;
  if (glow) {
    glow.scale.y += (target - glow.scale.y) * BAR_LERP_ALPHA;
    syncBarMaterial(
      refs.glowMaterialRef.current,
      BAR_DEFS[index]?.color ?? "#ffffff",
      isGpuAbsent ? 0.02 : 0.15 + 0.35 * (pct / 100),
      isGpuAbsent ? 0.06 : 0.18 + 0.22 * (pct / 100),
    );
  }
}

function OrbMetricBar3D({
  definition,
  index,
  metricsRef,
  barGeo,
  glowGeo,
}: Readonly<{
  definition: (typeof BAR_DEFS)[number];
  index: number;
  metricsRef: RefObject<OrbMetrics>;
  barGeo: THREE.BoxGeometry;
  glowGeo: THREE.BoxGeometry;
}>) {
  const groupRef = useRef<THREE.Group>(null);
  const coreRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);
  const coreMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const glowMaterialRef = useRef<THREE.MeshStandardMaterial>(null);
  const refs = { groupRef, coreRef, glowRef, coreMaterialRef, glowMaterialRef } as const;

  useEffect(() => {
    if (groupRef.current) {
      groupRef.current.rotation.set(definition.rotation[0], definition.rotation[1], definition.rotation[2]);
    }
    if (coreRef.current) {
      coreRef.current.geometry = barGeo;
    }
    if (glowRef.current) {
      glowRef.current.geometry = glowGeo;
    }
  }, [barGeo, definition.rotation, glowGeo]);

  useFrame(() => {
    syncOrbMetricBarFrame(index, metricsRef, refs);
  });

  return (
    <group ref={groupRef}>
      <mesh ref={glowRef} scale={[1, MIN_BAR_SCALE, 1]}>
        <meshStandardMaterial
          ref={glowMaterialRef}
          color={definition.color}
          emissive={definition.color}
          emissiveIntensity={0.15}
          transparent
          opacity={0.12}
          depthWrite={false}
        />
      </mesh>
      <mesh ref={coreRef} scale={[1, MIN_BAR_SCALE, 1]}>
        <meshStandardMaterial
          ref={coreMaterialRef}
          color={definition.color}
          emissive={definition.color}
          emissiveIntensity={0.35}
          transparent
          opacity={0.9}
          depthWrite={false}
        />
      </mesh>
    </group>
  );
}

function OrbMetricsBars3D({ metricsRef }: OrbMetricsBars3DProps) {
  const barGeo = useMemo(() => makeBarGeometry(), []);
  const glowGeo = useMemo(() => makeGlowGeometry(), []);

  return (
    <>
      {BAR_DEFS.map((definition, index) => (
        <OrbMetricBar3D
          key={definition.key}
          definition={definition}
          index={index}
          metricsRef={metricsRef}
          barGeo={barGeo}
          glowGeo={glowGeo}
        />
      ))}
    </>
  );
}

// ─── Particles 3D ───────────────────────────────────────────────────────────

const PARTICLE_COUNT = 40;

function pseudoRandom(seed: number): number {
  const x = Math.sin(seed) * 43758.5453123;
  return x - Math.floor(x);
}

function sampleParticle(seed: number) {
  const theta = pseudoRandom(seed * 1.17 + 1) * Math.PI * 2;
  const phi = pseudoRandom(seed * 1.91 + 2) * (Math.PI / 2);
  const r = 0.65 + pseudoRandom(seed * 2.53 + 3) * 0.15;
  return {
    theta,
    phi,
    r,
    vy: 0.15 + pseudoRandom(seed * 3.11 + 4) * 0.25,
    life: pseudoRandom(seed * 4.07 + 5),
  };
}

type ParticleState = {
  positions: Float32Array;
  velocities: Float32Array;
  lifetimes: Float32Array;
  resetCounts: Uint32Array;
};

function createParticleState(): ParticleState {
  const positions = new Float32Array(PARTICLE_COUNT * 3);
  const velocities = new Float32Array(PARTICLE_COUNT * 3);
  const lifetimes = new Float32Array(PARTICLE_COUNT);
  const resetCounts = new Uint32Array(PARTICLE_COUNT);
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const sample = sampleParticle(i + 1);
    positions[i * 3] = sample.r * Math.sin(sample.phi) * Math.cos(sample.theta);
    positions[i * 3 + 1] = sample.r * Math.cos(sample.phi);
    positions[i * 3 + 2] = sample.r * Math.sin(sample.phi) * Math.sin(sample.theta);
    velocities[i * 3] = (pseudoRandom(i * 5.13 + 6) - 0.5) * 0.02;
    velocities[i * 3 + 1] = sample.vy;
    velocities[i * 3 + 2] = (pseudoRandom(i * 7.41 + 7) - 0.5) * 0.02;
    lifetimes[i] = sample.life;
  }
  return { positions, velocities, lifetimes, resetCounts };
}

const GLOBAL_PARTICLE_STATE = createParticleState();
const GLOBAL_FFT_DATA_ARRAY = new Uint8Array(128 * 4);
const GLOBAL_FFT_TEXTURE = new THREE.DataTexture(GLOBAL_FFT_DATA_ARRAY, 128, 1, THREE.RGBAFormat);
GLOBAL_FFT_TEXTURE.needsUpdate = true;
const GLOBAL_BLOOM_TARGET = { current: 0.3 };
const GLOBAL_CHROMATIC_OFFSET = new THREE.Vector2(0, 0);
const GLOBAL_ORB_SHADER_MATERIAL = new THREE.ShaderMaterial({
  uniforms: {
    fftTexture: { value: GLOBAL_FFT_TEXTURE },
    audioLevel: { value: 0 },
    time: { value: 0 },
    blobEnabled: { value: 1 },
    fftEnabled: { value: 1 },
    iridescenceEnabled: { value: 0 },
    baseColor: { value: STATE_COLORS.ready.base.clone() },
    emissionColor: { value: STATE_COLORS.ready.emission.clone() },
    emissionIntensity: { value: 0.2 },
  },
  vertexShader,
  fragmentShader,
});

function getActiveAnalyser(
  state: VoiceOrbState,
  micAnalyserRef?: RefObject<AnalyserNode | null>,
  ttsAnalyserRef?: RefObject<AnalyserNode | null>,
): AnalyserNode | null {
  if (state === "recording") return micAnalyserRef?.current ?? null;
  if (state === "tts") return ttsAnalyserRef?.current ?? null;
  return null;
}

function getEmissionTarget(state: VoiceOrbState, audioLevel: number, elapsed: number, burst: number): number {
  if (state === "recording") return 0.25 + audioLevel * 0.6;
  if (state === "tts") return 0.3 + audioLevel * 0.9;
  if (state === "thinking") return 0.3 + Math.sin(elapsed * 2.2) * 0.15;
  if (state === "complete") return Math.max(0, burst);
  if (state === "ready") return 0.15 + Math.sin(elapsed * 1.5) * 0.05;
  return 0.1;
}

function getBloomTarget(state: VoiceOrbState, audioLevel: number, elapsed: number, burst: number): number {
  if (state === "recording") return 0.4 + audioLevel * 0.8;
  if (state === "tts") return 0.5 + audioLevel * 1.2;
  if (state === "thinking") return 0.4 + Math.sin(elapsed * 2) * 0.15;
  if (state === "complete") return 1.2 * burst;
  if (state === "ready") return 0.25;
  return 0.1;
}

function updateVolumetricLights(
  light1: THREE.PointLight | null,
  light2: THREE.PointLight | null,
  delta: number,
  audioLevel: number,
  enabled: boolean,
  light1Angle: MutableRefObject<number>,
  light2Angle: MutableRefObject<number>,
) {
  if (!enabled) return;
  light1Angle.current += delta * (Math.PI * 2 / 6);
  light2Angle.current += delta * (Math.PI * 2 / 10);
  if (light1) {
    light1.position.set(
      Math.cos(light1Angle.current) * 2,
      Math.sin(light1Angle.current * 0.7) * 1.2,
      Math.sin(light1Angle.current) * 2,
    );
    light1.intensity = 0.6 + audioLevel;
  }
  if (light2) {
    light2.position.set(
      Math.cos(light2Angle.current + Math.PI) * 2.5,
      Math.sin(light2Angle.current * 0.5) * 1.5,
      Math.sin(light2Angle.current + Math.PI) * 2.5,
    );
    light2.intensity = 0.4 + audioLevel * 0.6;
  }
}

type ShaderUpdateContext = Readonly<{
  mat: THREE.ShaderMaterial | null;
  state: VoiceOrbState;
  colors: StateColors;
  audioLevel: number;
  elapsed: number;
  delta: number;
  effectsConfig: OrbEffectsConfig;
  activeAnalyser: AnalyserNode | null;
  rawFFT: MutableRefObject<Uint8Array>;
  burstProgress: MutableRefObject<number>;
}>;

function updateShaderMaterial({
  mat,
  state,
  colors,
  audioLevel,
  elapsed,
  delta,
  effectsConfig,
  activeAnalyser,
  rawFFT,
  burstProgress,
}: ShaderUpdateContext) {
  if (!mat) return;
  const uniforms = mat.uniforms as Record<string, { value: unknown }>;
  const setUniform = (name: string, value: unknown) => {
    const uniform = uniforms[name];
    if (uniform) {
      uniform.value = value;
      return;
    }
    uniforms[name] = { value };
  };

  if (activeAnalyser) {
    activeAnalyser.getByteFrequencyData(rawFFT.current);
    for (let i = 0; i < 128; i++) {
      const val = rawFFT.current[i] ?? 0;
      GLOBAL_FFT_DATA_ARRAY[i * 4] = val;
      GLOBAL_FFT_DATA_ARRAY[i * 4 + 1] = val;
      GLOBAL_FFT_DATA_ARRAY[i * 4 + 2] = val;
      GLOBAL_FFT_DATA_ARRAY[i * 4 + 3] = 255;
    }
    GLOBAL_FFT_TEXTURE.needsUpdate = true;
  }

  setUniform("fftTexture", GLOBAL_FFT_TEXTURE);
  setUniform("audioLevel", audioLevel);
  setUniform("time", elapsed);
  setUniform("blobEnabled", effectsConfig.blob && (state === "recording" || state === "tts") ? 1 : 0);
  setUniform("fftEnabled", effectsConfig.frequencyRing && !!activeAnalyser ? 1 : 0);
  setUniform("iridescenceEnabled", effectsConfig.iridescence ? 1 : 0);

  const currentBase = (uniforms.baseColor?.value as THREE.Color | undefined) ?? colors.base.clone();
  const currentEmission = (uniforms.emissionColor?.value as THREE.Color | undefined) ?? colors.emission.clone();
  currentBase.lerp(colors.base, delta * 4);
  currentEmission.lerp(colors.emission, delta * 4);
  setUniform("baseColor", currentBase);
  setUniform("emissionColor", currentEmission);

  if (state === "complete" && burstProgress.current > 0) {
    burstProgress.current = Math.max(0, burstProgress.current - delta * 1.8);
  }

  const currentEmissionIntensity = (uniforms.emissionIntensity?.value as number | undefined) ?? 0;
  setUniform(
    "emissionIntensity",
    currentEmissionIntensity +
      (getEmissionTarget(state, audioLevel, elapsed, burstProgress.current) - currentEmissionIntensity) * delta * 5,
  );

  GLOBAL_BLOOM_TARGET.current = getBloomTarget(state, audioLevel, elapsed, burstProgress.current);
}

type OrbParticles3DProps = Readonly<{
  active: boolean;
  color: THREE.Color;
  audioLevel: number;
}>;

function OrbParticles3D({ active, color, audioLevel }: OrbParticles3DProps) {
  const pointsRef = useRef<THREE.Points>(null);
  const geometryRef = useRef<THREE.BufferGeometry | null>(null);
  const materialRef = useRef<THREE.PointsMaterial | null>(null);

  useEffect(() => {
    if (geometryRef.current) {
      geometryRef.current.setAttribute(
        "position",
        new THREE.BufferAttribute(GLOBAL_PARTICLE_STATE.positions, 3),
      );
    }
    if (materialRef.current) {
      materialRef.current.color.set(color);
      materialRef.current.size = 0.035;
      materialRef.current.transparent = true;
      materialRef.current.opacity = 0.55;
      materialRef.current.depthWrite = false;
      materialRef.current.sizeAttenuation = true;
    }
  }, [color]);

  useFrame((_, delta) => {
    if (!active || !pointsRef.current) return;
    const pos = pointsRef.current.geometry.attributes.position?.array as Float32Array | undefined;
    if (!pos) return;
    const v = GLOBAL_PARTICLE_STATE.velocities;
    const l = GLOBAL_PARTICLE_STATE.lifetimes;
    const speed = 0.4 + audioLevel * 0.6;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      pos[i * 3]     += v[i * 3] * delta;
      pos[i * 3 + 1] += v[i * 3 + 1] * speed * delta;
      pos[i * 3 + 2] += v[i * 3 + 2] * delta;
      l[i] -= delta * 0.35;
      if (l[i] <= 0) {
        // Reset particle on sphere surface (upper hemisphere)
        const resetIndex = (GLOBAL_PARTICLE_STATE.resetCounts[i] ?? 0) + 1;
        GLOBAL_PARTICLE_STATE.resetCounts[i] = resetIndex;
        const sample = sampleParticle(i + resetIndex * 17);
        pos[i * 3] = sample.r * Math.sin(sample.phi) * Math.cos(sample.theta);
        pos[i * 3 + 1] = sample.r * Math.cos(sample.phi);
        pos[i * 3 + 2] = sample.r * Math.sin(sample.phi) * Math.sin(sample.theta);
        v[i * 3 + 1] = sample.vy;
        l[i] = 0.5 + sample.life * 0.5;
      }
    }
    (pointsRef.current.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true;
  });

  if (!active) return null;

  return (
    <points ref={pointsRef}>
      <bufferGeometry ref={geometryRef} />
      <pointsMaterial ref={materialRef} />
    </points>
  );
}

// ─── Main orb scene (inside Canvas) ─────────────────────────────────────────

type OrbSceneProps = Readonly<{
  state: VoiceOrbState;
  effectsConfig: OrbEffectsConfig;
  micAnalyserRef?: RefObject<AnalyserNode | null>;
  ttsAnalyserRef?: RefObject<AnalyserNode | null>;
  inputLevel: number;
  outputLevel: number;
  reducedMotion: boolean;
  metricsRef?: RefObject<OrbMetrics>;
}>;

function getOrbAudioLevel(state: VoiceOrbState, inputLevel: number, outputLevel: number): number {
  if (state === "recording") return inputLevel;
  if (state === "tts") return outputLevel;
  return 0;
}

function OrbScene({
  state,
  effectsConfig,
  micAnalyserRef,
  ttsAnalyserRef,
  inputLevel,
  outputLevel,
  reducedMotion,
  metricsRef,
}: OrbSceneProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const ambientLightRef = useRef<THREE.AmbientLight>(null);
  const light1Ref = useRef<THREE.PointLight>(null);
  const light2Ref = useRef<THREE.PointLight>(null);
  const light1Angle = useRef(0);
  const light2Angle = useRef(Math.PI);
  const prevState = useRef(state);
  const burstProgress = useRef(0);
  const rawFFT = useRef(new Uint8Array(128));

  const audioLevel = getOrbAudioLevel(state, inputLevel, outputLevel);
  const isActive = state === "recording" || state === "tts";
  const colors = STATE_COLORS[state];
  const activeAnalyser = getActiveAnalyser(state, micAnalyserRef, ttsAnalyserRef);
  const orbGeometry = useMemo(() => new THREE.SphereGeometry(0.62, 64, 64), []);
  const shaderMaterial = GLOBAL_ORB_SHADER_MATERIAL;

  // Chromatic aberration spike on state change
  useEffect(() => {
    if (!effectsConfig.transitions || !effectsConfig.chromaticAberration || reducedMotion) return;
    if (prevState.current === state) return;
    prevState.current = state;

    const start = performance.now();
    const tick = () => {
      const t = Math.min((performance.now() - start) / 280, 1);
      const ease = Math.sin(t * Math.PI);
      GLOBAL_CHROMATIC_OFFSET.set(ease * 0.007, ease * 0.007);
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [state, effectsConfig.transitions, effectsConfig.chromaticAberration, reducedMotion]);

  // Complete state burst
  useEffect(() => {
    if (state === "complete") {
      burstProgress.current = 1;
    }
  }, [state]);

  useEffect(() => {
    if (meshRef.current) {
      meshRef.current.geometry = orbGeometry;
      meshRef.current.material = shaderMaterial;
    }
    return () => {
      orbGeometry.dispose();
    };
  }, [orbGeometry, shaderMaterial]);

  useEffect(() => {
    const uniforms = shaderMaterial.uniforms as Record<string, { value: unknown }>;
    (uniforms.baseColor.value as THREE.Color).copy(colors.base);
    (uniforms.emissionColor.value as THREE.Color).copy(colors.emission);
    if (uniforms.iridescenceEnabled) {
      uniforms.iridescenceEnabled.value = effectsConfig.iridescence ? 1 : 0;
    }
  }, [colors, effectsConfig.iridescence, shaderMaterial]);

  useEffect(() => {
    if (ambientLightRef.current) {
      ambientLightRef.current.intensity = 0.15;
    }
    if (light1Ref.current) {
      light1Ref.current.color.copy(colors.emission);
      light1Ref.current.distance = 5;
      light1Ref.current.decay = 2;
    }
    if (light2Ref.current) {
      light2Ref.current.color.copy(colors.base);
      light2Ref.current.distance = 5;
      light2Ref.current.decay = 2;
    }
  }, [colors]);

  useFrame((frameState, delta) => {
    const t = frameState.clock.elapsedTime;
    updateShaderMaterial(
      {
        mat: shaderMaterial,
        state,
        colors,
        audioLevel,
        elapsed: t,
        delta,
        effectsConfig,
        activeAnalyser,
        rawFFT,
        burstProgress,
      },
    );
    updateVolumetricLights(
      light1Ref.current,
      light2Ref.current,
      delta,
      audioLevel,
      effectsConfig.volumetricLights,
      light1Angle,
      light2Angle,
    );
  });

  return (
    <>
      <ambientLight ref={ambientLightRef} />

      {effectsConfig.volumetricLights && (
        <>
          <pointLight ref={light1Ref} />
          <pointLight ref={light2Ref} />
        </>
      )}

      <mesh ref={meshRef} />

      {effectsConfig.particles ? (
        <OrbParticles3D active={isActive} color={colors.emission} audioLevel={audioLevel} />
      ) : null}

      {effectsConfig.coreTexture ? (
        <Environment preset="city" background={false} />
      ) : null}

      {effectsConfig.orbMetricsBars && metricsRef && !reducedMotion ? (
        <OrbMetricsBars3D metricsRef={metricsRef} />
      ) : null}

      {effectsConfig.bloom && !reducedMotion ? (
        <EffectComposer>
          <Bloom
            intensity={GLOBAL_BLOOM_TARGET.current}
            luminanceThreshold={0.22}
            luminanceSmoothing={0.9}
            blendFunction={BlendFunction.ADD}
          />
          <ChromaticAberration
            offset={effectsConfig.chromaticAberration && !reducedMotion
              ? GLOBAL_CHROMATIC_OFFSET
              : new THREE.Vector2(0, 0)}
            radialModulation={false}
            modulationOffset={0}
          />
        </EffectComposer>
      ) : null}
    </>
  );
}

// ─── Public component ────────────────────────────────────────────────────────

type VoiceOrb3DProps = Readonly<{
  state: VoiceOrbState;
  effectsConfig: OrbEffectsConfig;
  reducedMotion?: boolean;
  micAnalyserRef?: RefObject<AnalyserNode | null>;
  ttsAnalyserRef?: RefObject<AnalyserNode | null>;
  disabled?: boolean;
  size?: number;
  metricsRef?: RefObject<OrbMetrics>;
}>;

export function VoiceOrb3D({
  state,
  effectsConfig,
  reducedMotion = false,
  micAnalyserRef,
  ttsAnalyserRef,
  disabled = false,
  size = 200,
  metricsRef,
}: VoiceOrb3DProps) {
  const fallbackRef = useRef<AnalyserNode | null>(null);
  const effectiveState: VoiceOrbState = disabled ? "offline" : state;

  const inputLevel = useAudioLevel(micAnalyserRef ?? fallbackRef, effectiveState === "recording");
  const outputLevel = useAudioLevel(ttsAnalyserRef ?? fallbackRef, effectiveState === "tts");

  return (
    <div
      style={{ width: size, height: size }}
      aria-label="Voice orb visualization"
      role="img"
      data-orb-state={effectiveState}
    >
      <Canvas
        camera={{ position: [0, 0, 2.2], fov: 42 }}
        gl={{ antialias: true, alpha: true }}
        style={{ width: size, height: size }}
        dpr={[1, 2]}
      >
        <OrbScene
          state={effectiveState}
          effectsConfig={effectsConfig}
          micAnalyserRef={micAnalyserRef}
          ttsAnalyserRef={ttsAnalyserRef}
          inputLevel={inputLevel}
          outputLevel={outputLevel}
          reducedMotion={reducedMotion}
          metricsRef={metricsRef}
        />
      </Canvas>
    </div>
  );
}

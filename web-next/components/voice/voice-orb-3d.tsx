"use client";

import { useEffect, useMemo, useRef } from "react";
import type { RefObject } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Environment } from "@react-three/drei";
import { EffectComposer, Bloom, ChromaticAberration } from "@react-three/postprocessing";
import { BlendFunction } from "postprocessing";
import * as THREE from "three";
import type { VoiceOrbState } from "@/components/voice/voice-orb";
import type { OrbEffectsConfig } from "@/components/voice/use-orb-effects-config";
import { useAudioLevel } from "@/components/voice/use-audio-level";

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

// ─── Particles 3D ───────────────────────────────────────────────────────────

const PARTICLE_COUNT = 40;

function OrbParticles3D({
  active,
  color,
  audioLevel,
}: {
  active: boolean;
  color: THREE.Color;
  audioLevel: number;
}) {
  const pointsRef = useRef<THREE.Points>(null);
  const velocitiesRef = useRef<Float32Array>(new Float32Array(PARTICLE_COUNT * 3));
  const lifetimesRef = useRef<Float32Array>(new Float32Array(PARTICLE_COUNT));

  const positions = useMemo(() => {
    const arr = new Float32Array(PARTICLE_COUNT * 3);
    const v = velocitiesRef.current;
    const l = lifetimesRef.current;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const theta = Math.random() * Math.PI * 2;
      const phi = (Math.random() * Math.PI) / 2; // upper hemisphere
      const r = 0.65 + Math.random() * 0.15;
      arr[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
      arr[i * 3 + 1] = r * Math.cos(phi);
      arr[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
      v[i * 3]     = (Math.random() - 0.5) * 0.02;
      v[i * 3 + 1] = 0.15 + Math.random() * 0.25;
      v[i * 3 + 2] = (Math.random() - 0.5) * 0.02;
      l[i] = Math.random();
    }
    return arr;
  }, []);

  useFrame((_, delta) => {
    if (!active || !pointsRef.current) return;
    const pos = pointsRef.current.geometry.attributes.position?.array as Float32Array | undefined;
    if (!pos) return;
    const v = velocitiesRef.current;
    const l = lifetimesRef.current;
    const speed = 0.4 + audioLevel * 0.6;
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      pos[i * 3]     += v[i * 3] * delta;
      pos[i * 3 + 1] += v[i * 3 + 1] * speed * delta;
      pos[i * 3 + 2] += v[i * 3 + 2] * delta;
      l[i] -= delta * 0.35;
      if (l[i] <= 0) {
        // Reset particle on sphere surface (upper hemisphere)
        const theta = Math.random() * Math.PI * 2;
        const phi = (Math.random() * Math.PI) / 2;
        const r = 0.65 + Math.random() * 0.1;
        pos[i * 3]     = r * Math.sin(phi) * Math.cos(theta);
        pos[i * 3 + 1] = r * Math.cos(phi);
        pos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
        v[i * 3 + 1] = 0.15 + Math.random() * 0.25;
        l[i] = 0.5 + Math.random() * 0.5;
      }
    }
    (pointsRef.current.geometry.attributes.position as THREE.BufferAttribute).needsUpdate = true;
  });

  if (!active) return null;

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
        />
      </bufferGeometry>
      <pointsMaterial
        size={0.035}
        color={color}
        transparent
        opacity={0.55}
        depthWrite={false}
        sizeAttenuation
      />
    </points>
  );
}

// ─── Main orb scene (inside Canvas) ─────────────────────────────────────────

type OrbSceneProps = {
  state: VoiceOrbState;
  effectsConfig: OrbEffectsConfig;
  micAnalyserRef?: RefObject<AnalyserNode | null>;
  ttsAnalyserRef?: RefObject<AnalyserNode | null>;
  inputLevel: number;
  outputLevel: number;
  reducedMotion: boolean;
};

function OrbScene({
  state,
  effectsConfig,
  micAnalyserRef,
  ttsAnalyserRef,
  inputLevel,
  outputLevel,
  reducedMotion,
}: OrbSceneProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.ShaderMaterial>(null);
  const light1Ref = useRef<THREE.PointLight>(null);
  const light2Ref = useRef<THREE.PointLight>(null);
  const light1Angle = useRef(0);
  const light2Angle = useRef(Math.PI);
  const chromaticOffsetRef = useRef(new THREE.Vector2(0, 0));
  const prevState = useRef(state);
  const burstProgress = useRef(0);
  const { camera } = useThree();

  // DataTexture for FFT data (128 buckets → 128x1 RGBA texture)
  const fftDataArray = useRef(new Uint8Array(128 * 4));
  const fftTexture = useMemo(() => {
    const tex = new THREE.DataTexture(fftDataArray.current, 128, 1, THREE.RGBAFormat);
    tex.needsUpdate = true;
    return tex;
  }, []);

  const rawFFT = useRef(new Uint8Array(128));

  const audioLevel = state === "recording" ? inputLevel : state === "tts" ? outputLevel : 0;
  const isActive = state === "recording" || state === "tts";
  const colors = STATE_COLORS[state];

  // Bloom intensity state
  const bloomTarget = useRef(0.3);

  // Chromatic aberration spike on state change
  useEffect(() => {
    if (!effectsConfig.transitions || !effectsConfig.chromaticAberration || reducedMotion) return;
    if (prevState.current === state) return;
    prevState.current = state;

    const start = performance.now();
    const tick = () => {
      const t = Math.min((performance.now() - start) / 280, 1);
      const ease = Math.sin(t * Math.PI);
      chromaticOffsetRef.current.set(ease * 0.007, ease * 0.007);
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

  useFrame((frameState, delta) => {
    const mat = matRef.current;
    if (!mat) return;

    const t = frameState.clock.elapsedTime;

    // Update FFT texture
    const activeAnalyser =
      state === "recording" ? micAnalyserRef?.current :
      state === "tts" ? ttsAnalyserRef?.current : null;

    if (activeAnalyser) {
      activeAnalyser.getByteFrequencyData(rawFFT.current);
      const fftArr = fftDataArray.current;
      for (let i = 0; i < 128; i++) {
        const val = rawFFT.current[i] ?? 0;
        fftArr[i * 4]     = val;
        fftArr[i * 4 + 1] = val;
        fftArr[i * 4 + 2] = val;
        fftArr[i * 4 + 3] = 255;
      }
      fftTexture.needsUpdate = true;
    }

    // Update material uniforms
    mat.uniforms.fftTexture = { value: fftTexture };
    mat.uniforms.audioLevel = { value: audioLevel };
    mat.uniforms.time = { value: t };
    mat.uniforms.blobEnabled = { value: effectsConfig.blob && isActive ? 1 : 0 };
    mat.uniforms.fftEnabled = { value: effectsConfig.frequencyRing && !!activeAnalyser ? 1 : 0 };
    mat.uniforms.iridescenceEnabled = { value: effectsConfig.iridescence ? 1 : 0 };

    // Lerp colors toward target state
    const currentBase = (mat.uniforms.baseColor?.value as THREE.Color) ?? colors.base.clone();
    const currentEmission = (mat.uniforms.emissionColor?.value as THREE.Color) ?? colors.emission.clone();
    currentBase.lerp(colors.base, delta * 4);
    currentEmission.lerp(colors.emission, delta * 4);
    mat.uniforms.baseColor = { value: currentBase };
    mat.uniforms.emissionColor = { value: currentEmission };

    // Emission intensity per state + audio reactivity
    let emissionTarget = 0.1;
    if (state === "recording") emissionTarget = 0.25 + audioLevel * 0.6;
    else if (state === "tts") emissionTarget = 0.3 + audioLevel * 0.9;
    else if (state === "thinking") emissionTarget = 0.3 + Math.sin(t * 2.2) * 0.15;
    else if (state === "complete") emissionTarget = Math.max(0, burstProgress.current);
    else if (state === "ready") emissionTarget = 0.15 + Math.sin(t * 1.5) * 0.05;

    if (state === "complete" && burstProgress.current > 0) {
      burstProgress.current = Math.max(0, burstProgress.current - delta * 1.8);
    }

    const prevEmission = (mat.uniforms.emissionIntensity?.value as number) ?? 0;
    mat.uniforms.emissionIntensity = { value: prevEmission + (emissionTarget - prevEmission) * delta * 5 };

    // Bloom intensity
    bloomTarget.current =
      state === "recording" ? 0.4 + audioLevel * 0.8 :
      state === "tts" ? 0.5 + audioLevel * 1.2 :
      state === "thinking" ? 0.4 + Math.sin(t * 2) * 0.15 :
      state === "complete" ? 1.2 * burstProgress.current :
      state === "ready" ? 0.25 : 0.1;

    // Volumetric orbiting lights
    if (effectsConfig.volumetricLights) {
      light1Angle.current += delta * (Math.PI * 2 / 6);
      light2Angle.current += delta * (Math.PI * 2 / 10);
      if (light1Ref.current) {
        light1Ref.current.position.set(
          Math.cos(light1Angle.current) * 2,
          Math.sin(light1Angle.current * 0.7) * 1.2,
          Math.sin(light1Angle.current) * 2,
        );
        light1Ref.current.intensity = 0.6 + audioLevel * 1.0;
      }
      if (light2Ref.current) {
        light2Ref.current.position.set(
          Math.cos(light2Angle.current + Math.PI) * 2.5,
          Math.sin(light2Angle.current * 0.5) * 1.5,
          Math.sin(light2Angle.current + Math.PI) * 2.5,
        );
        light2Ref.current.intensity = 0.4 + audioLevel * 0.6;
      }
    }

    // Suppress unused variable warning
    void camera;
  });

  const shaderUniforms = useMemo(() => ({
    fftTexture: { value: fftTexture },
    audioLevel: { value: 0 },
    time: { value: 0 },
    blobEnabled: { value: 1 },
    fftEnabled: { value: 1 },
    iridescenceEnabled: { value: effectsConfig.iridescence ? 1 : 0 },
    baseColor: { value: colors.base.clone() },
    emissionColor: { value: colors.emission.clone() },
    emissionIntensity: { value: 0.2 },
  }), []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <ambientLight intensity={0.15} />

      {effectsConfig.volumetricLights && (
        <>
          <pointLight ref={light1Ref} color={colors.emission} intensity={0.6} distance={5} decay={2} />
          <pointLight ref={light2Ref} color={colors.base} intensity={0.4} distance={5} decay={2} />
        </>
      )}

      <mesh ref={meshRef}>
        <sphereGeometry args={[0.62, 64, 64]} />
        <shaderMaterial
          ref={matRef}
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          uniforms={shaderUniforms}
        />
      </mesh>

      {effectsConfig.particles ? (
        <OrbParticles3D active={isActive} color={colors.emission} audioLevel={audioLevel} />
      ) : null}

      {effectsConfig.coreTexture ? (
        <Environment preset="city" background={false} />
      ) : null}

      {effectsConfig.bloom && !reducedMotion ? (
        <EffectComposer>
          <Bloom
            intensity={bloomTarget.current}
            luminanceThreshold={0.22}
            luminanceSmoothing={0.9}
            blendFunction={BlendFunction.ADD}
          />
          <ChromaticAberration
            offset={effectsConfig.chromaticAberration && !reducedMotion
              ? chromaticOffsetRef.current
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
}>;

export function VoiceOrb3D({
  state,
  effectsConfig,
  reducedMotion = false,
  micAnalyserRef,
  ttsAnalyserRef,
  disabled = false,
  size = 200,
}: VoiceOrb3DProps) {
  const fallbackRef = useRef<AnalyserNode | null>(null);
  const effectiveState: VoiceOrbState = disabled ? "offline" : state;

  const inputLevel = useAudioLevel(micAnalyserRef ?? fallbackRef, effectiveState === "recording");
  const outputLevel = useAudioLevel(ttsAnalyserRef ?? fallbackRef, effectiveState === "tts");

  return (
    <div
      style={{ width: size, height: size }}
      aria-label="Voice orb visualization"
      role="presentation"
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
        />
      </Canvas>
    </div>
  );
}

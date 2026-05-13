import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render } from "@testing-library/react";
import type { OrbEffectsConfig } from "../components/voice/use-orb-effects-config";
import { VoiceOrb, type VoiceOrbState } from "../components/voice/voice-orb";

afterEach(() => cleanup());

const ALL_STATES: VoiceOrbState[] = [
  "offline",
  "ready",
  "recording",
  "stt",
  "thinking",
  "tts",
  "complete",
  "error",
];

const METRICS_ENABLED_CONFIG: OrbEffectsConfig = {
  ripple: false,
  blob: false,
  glow: false,
  transitions: false,
  frequencyRing: false,
  coreTexture: false,
  particles: false,
  stateLabel: false,
  orbMetricsBars: true,
};

const NO_GLOW_CONFIG: OrbEffectsConfig = {
  ripple: false,
  blob: false,
  glow: false,
  transitions: false,
  frequencyRing: false,
  coreTexture: false,
  particles: false,
  stateLabel: true,
  orbMetricsBars: false,
};

const BLOB_ENABLED_CONFIG: OrbEffectsConfig = {
  ripple: false,
  blob: true,
  glow: false,
  transitions: false,
  frequencyRing: false,
  coreTexture: false,
  particles: false,
  stateLabel: false,
  orbMetricsBars: false,
};

const PARTICLES_ENABLED_CONFIG: OrbEffectsConfig = {
  ripple: false,
  blob: false,
  glow: false,
  transitions: false,
  frequencyRing: false,
  coreTexture: false,
  particles: true,
  stateLabel: false,
  orbMetricsBars: false,
};

describe("VoiceOrb", () => {
  for (const state of ALL_STATES) {
    it(`renders state=${state} without crashing`, () => {
      const { container } = render(
        <VoiceOrb state={state} inputLevel={0} outputLevel={0} />,
      );
      assert.ok(container.firstChild, `VoiceOrb state=${state} should render`);
    });
  }

  it("exposes data-orb-state attribute reflecting active state", () => {
    const { getByRole } = render(
      <VoiceOrb state="recording" inputLevel={0.5} outputLevel={0} />,
    );
    const orb = getByRole("img");
    assert.equal(orb.getAttribute("data-orb-state"), "recording");
  });

  it("overrides state to offline when disabled=true", () => {
    const { getByRole } = render(
      <VoiceOrb state="recording" inputLevel={0.8} outputLevel={0} disabled />,
    );
    assert.equal(getByRole("img").getAttribute("data-orb-state"), "offline");
  });

  it("uses the label prop as aria-label", () => {
    const { getByRole } = render(
      <VoiceOrb state="ready" inputLevel={0} outputLevel={0} label="Gotowy" />,
    );
    assert.equal(getByRole("img").getAttribute("aria-label"), "Gotowy");
  });

  it("does not render metrics bars on idle ready state even when enabled", () => {
    const metricsRef = {
      current: { cpu: 12, gpu: 4, vram: 8, ram: 16 },
    } as const;
    const { container } = render(
      <VoiceOrb
        state="ready"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={METRICS_ENABLED_CONFIG}
        metricsRef={metricsRef as never}
      />,
    );

    assert.equal(container.querySelectorAll("svg").length, 0);
  });

  it("keeps the ready state visually calm without ambient motion classes", () => {
    const { container } = render(
      <VoiceOrb state="ready" inputLevel={0} outputLevel={0} />,
    );

    assert.ok(!container.innerHTML.includes("animate-pulse-signal"));
    assert.ok(!container.innerHTML.includes("animate-orb-plasma-slow"));
    assert.ok(!container.innerHTML.includes("animate-orb-plasma-fast"));
  });

  it("does not render the blur glow layer when glow=false", () => {
    const { container } = render(
      <VoiceOrb
        state="complete"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={NO_GLOW_CONFIG}
      />,
    );

    assert.ok(!container.innerHTML.includes("blur-2xl"));
  });

  it("renders blob only in thinking state", () => {
    const recording = render(
      <VoiceOrb
        state="recording"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={BLOB_ENABLED_CONFIG}
      />,
    );
    assert.ok(!recording.container.innerHTML.includes("animate-orb-blob"));
    recording.unmount();

    const thinking = render(
      <VoiceOrb
        state="thinking"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={BLOB_ENABLED_CONFIG}
      />,
    );
    assert.ok(thinking.container.innerHTML.includes("animate-orb-blob"));
  });

  it("renders particles only in thinking state", () => {
    const recording = render(
      <VoiceOrb
        state="recording"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={PARTICLES_ENABLED_CONFIG}
      />,
    );
    assert.ok(!recording.container.innerHTML.includes("animate-orb-particle-rise"));
    recording.unmount();

    const tts = render(
      <VoiceOrb
        state="tts"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={PARTICLES_ENABLED_CONFIG}
      />,
    );
    assert.ok(!tts.container.innerHTML.includes("animate-orb-particle-rise"));
    tts.unmount();

    const thinking = render(
      <VoiceOrb
        state="thinking"
        inputLevel={0}
        outputLevel={0}
        effectsConfig={PARTICLES_ENABLED_CONFIG}
      />,
    );
    assert.ok(thinking.container.innerHTML.includes("animate-orb-particle-rise"));
  });

  it("falls back to state name when no label provided", () => {
    const { getByRole } = render(
      <VoiceOrb state="thinking" inputLevel={0} outputLevel={0} />,
    );
    assert.equal(getByRole("img").getAttribute("aria-label"), "thinking");
  });

  describe("inputLevel → core scale (recording state)", () => {
    it("applies scale > 1 when inputLevel > 0 in recording state", () => {
      const { getByTestId } = render(
        <VoiceOrb state="recording" inputLevel={0.5} outputLevel={0} />,
      );
      const core = getByTestId("voice-orb-core");
      const transform = (core as HTMLElement).style.transform;
      const scaleValue = parseFloat(transform.replace("scale(", "").replace(")", ""));
      assert.ok(scaleValue > 1, `expected scale > 1, got ${scaleValue}`);
    });

    it("keeps scale=1 when inputLevel=0 in recording state", () => {
      const { getByTestId } = render(
        <VoiceOrb state="recording" inputLevel={0} outputLevel={0} />,
      );
      const core = getByTestId("voice-orb-core");
      assert.equal((core as HTMLElement).style.transform, "scale(1)");
    });
  });

  describe("outputLevel → core scale (tts state)", () => {
    it("applies scale > 1 when outputLevel > 0 in tts state", () => {
      const { getByTestId } = render(
        <VoiceOrb state="tts" inputLevel={0} outputLevel={0.7} />,
      );
      const core = getByTestId("voice-orb-core");
      const scaleValue = parseFloat(
        (core as HTMLElement).style.transform.replace("scale(", "").replace(")", ""),
      );
      assert.ok(scaleValue > 1, `expected scale > 1, got ${scaleValue}`);
    });

    it("does NOT use outputLevel when state is not tts", () => {
      const { getByTestId } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0.9} />,
      );
      const core = getByTestId("voice-orb-core");
      assert.equal((core as HTMLElement).style.transform, "scale(1)");
    });
  });

  describe("reducedMotion", () => {
    it("keeps scale=1 even with high inputLevel when reducedMotion=true", () => {
      const { getByTestId } = render(
        <VoiceOrb state="recording" inputLevel={1} outputLevel={0} reducedMotion />,
      );
      const core = getByTestId("voice-orb-core");
      assert.equal((core as HTMLElement).style.transform, "scale(1)");
    });

    it("removes ring animation classes when reducedMotion=true", () => {
      const { container } = render(
        <VoiceOrb state="thinking" inputLevel={0} outputLevel={0} reducedMotion />,
      );
      assert.ok(
        !container.innerHTML.includes("animate-orb-thinking"),
        "should not include animate-orb-thinking when reducedMotion=true",
      );
    });
  });

  describe("container dimensions", () => {
    it("sets minHeight on the container for layout stability", () => {
      const { getByRole } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} />,
      );
      const orb = getByRole("img");
      assert.ok(
        (orb as HTMLElement).style.minHeight,
        "container should have minHeight for layout stability",
      );
    });
  });
});

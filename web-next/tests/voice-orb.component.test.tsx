import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, render, fireEvent } from "@testing-library/react";
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
  parallaxTilt: false,
  interactiveGlow: false,
  clickShockwave: false,
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
  parallaxTilt: false,
  interactiveGlow: false,
  clickShockwave: false,
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
  parallaxTilt: false,
  interactiveGlow: false,
  clickShockwave: false,
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
  parallaxTilt: false,
  interactiveGlow: false,
  clickShockwave: false,
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

  describe("ergonomic enhancements", () => {
    it("applies ambient breath and fluid idle animations in ready state", () => {
      const { container } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} />,
      );
      assert.ok(container.innerHTML.includes("animate-orb-breath"), "should include animate-orb-breath");
      assert.ok(container.innerHTML.includes("animate-orb-fluid-idle"), "should include animate-orb-fluid-idle");
    });

    it("applies inner plasma gradient in thinking state", () => {
      const { container } = render(
        <VoiceOrb state="thinking" inputLevel={0} outputLevel={0} />,
      );
      assert.ok(container.innerHTML.includes("animate-orb-plasma-gradient"), "should include animate-orb-plasma-gradient");
    });

    it("applies dynamic VAD ring scaling during recording state based on input level", () => {
      const active = render(
        <VoiceOrb state="recording" inputLevel={0.15} outputLevel={0} />,
      );
      assert.ok(active.container.innerHTML.includes("border-emerald-400/60"), "should include border active class");
      assert.ok(active.container.innerHTML.includes("scale-[1.04]"), "should scale VAD ring");
      active.unmount();

      const quiet = render(
        <VoiceOrb state="recording" inputLevel={0} outputLevel={0} />,
      );
      assert.ok(!quiet.container.innerHTML.includes("border-emerald-400/60"), "should not include border active class when quiet");
      assert.ok(quiet.container.innerHTML.includes("scale-100"), "should scale to 100 when quiet");
      quiet.unmount();
    });

    it("respects reducedMotion by disabling ready state animations", () => {
      const { container } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} reducedMotion />,
      );
      assert.ok(!container.innerHTML.includes("animate-orb-breath"), "should disable breath animation");
      assert.ok(!container.innerHTML.includes("animate-orb-fluid-idle"), "should disable fluid idle animation");
    });
  });

  describe("PR248A — interactive effects", () => {
    it("registers mouse move and updates CSS variables for tilt when enabled", () => {
      const { getByRole } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} />
      );
      const orb = getByRole("img");
      const wrapper = orb.firstChild as HTMLElement;

      // Initially --mouse-x and --mouse-y are not set on style
      assert.equal(wrapper.style.getPropertyValue("--mouse-x"), "");

      // Trigger mousemove
      fireEvent.mouseMove(wrapper, { clientX: 100, clientY: 100 });

      // Should have set CSS variables (non-empty string)
      const mx = wrapper.style.getPropertyValue("--mouse-x");
      const my = wrapper.style.getPropertyValue("--mouse-y");
      assert.ok(mx !== "", "should set --mouse-x");
      assert.ok(my !== "", "should set --mouse-y");

      // Trigger mouseleave
      fireEvent.mouseLeave(wrapper);
      assert.equal(wrapper.style.getPropertyValue("--mouse-x"), "0");
      assert.equal(wrapper.style.getPropertyValue("--mouse-y"), "0");
    });

    it("does not track mouse or apply transform in offline state", () => {
      const { getByRole } = render(
        <VoiceOrb state="offline" inputLevel={0} outputLevel={0} />
      );
      const orb = getByRole("img");
      const wrapper = orb.firstChild as HTMLElement;

      fireEvent.mouseMove(wrapper, { clientX: 100, clientY: 100 });
      assert.equal(wrapper.style.getPropertyValue("--mouse-x"), "");
      assert.ok(!wrapper.style.transform.includes("perspective"), "should not have 3D perspective transform");
    });

    it("renders spotlight only when interactiveGlow is enabled and state is not offline", () => {
      const glowConfigEnabled: OrbEffectsConfig = {
        ripple: false, blob: false, glow: false, transitions: false,
        frequencyRing: false, coreTexture: true, particles: false,
        stateLabel: false, orbMetricsBars: false,
        parallaxTilt: false, interactiveGlow: true, clickShockwave: false
      };
      const { container, unmount } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} effectsConfig={glowConfigEnabled} />
      );
      assert.ok(container.innerHTML.includes("mix-blend-mode: overlay"), "should render spotlight");
      unmount();

      const offline = render(
        <VoiceOrb state="offline" inputLevel={0} outputLevel={0} effectsConfig={glowConfigEnabled} />
      );
      assert.ok(!offline.container.innerHTML.includes("mix-blend-mode: overlay"), "should not render spotlight in offline");
      offline.unmount();
    });

    it("spawns shockwave on click when clickShockwave is enabled", () => {
      const clickConfigEnabled: OrbEffectsConfig = {
        ripple: false, blob: false, glow: false, transitions: false,
        frequencyRing: false, coreTexture: false, particles: false,
        stateLabel: false, orbMetricsBars: false,
        parallaxTilt: false, interactiveGlow: false, clickShockwave: true
      };
      const { container, getByRole } = render(
        <VoiceOrb state="ready" inputLevel={0} outputLevel={0} effectsConfig={clickConfigEnabled} />
      );
      const orb = getByRole("img");
      const wrapper = orb.firstChild as HTMLElement;

      assert.ok(!container.innerHTML.includes("animate-orb-shockwave"), "no shockwave initially");

      fireEvent.click(wrapper, { clientX: 50, clientY: 50 });
      assert.ok(container.innerHTML.includes("animate-orb-shockwave"), "shockwave rendered after click");
    });
  });
});

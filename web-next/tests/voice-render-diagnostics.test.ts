import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyOrbDiagnosticProfile,
  parseVoiceEffectOverrides,
  parseVoiceRenderDiagnosticMode,
  resolveDiagnosticOrbState,
  resolveVoiceRenderDiagnostics,
} from "../components/voice/voice-render-diagnostics";
import type { OrbEffectsConfig } from "../components/voice/use-orb-effects-config";

const BASE_CONFIG: OrbEffectsConfig = {
  ripple: true,
  blob: true,
  glow: true,
  transitions: true,
  frequencyRing: true,
  coreTexture: true,
  particles: true,
  stateLabel: true,
  orb3D: true,
  bloom: true,
  chromaticAberration: true,
  iridescence: true,
  volumetricLights: true,
  orbMetricsBars: true,
};

describe("voice render diagnostics", () => {
  it("parses query mode when voiceDiag is provided", () => {
    assert.equal(parseVoiceRenderDiagnosticMode("?voiceDiag=orb_static_core"), "orb_static_core");
  });

  it("falls back to off for unknown diagnostic mode", () => {
    assert.equal(parseVoiceRenderDiagnosticMode("?voiceDiag=nope"), "off");
  });

  it("parses explicit per-effect overrides from query params", () => {
    const overrides = parseVoiceEffectOverrides("?voiceFxGlow=1&voiceFxParticles=0&voiceFxMetrics=false");
    assert.deepEqual(overrides, {
      glow: true,
      particles: false,
      orbMetricsBars: false,
    });
  });

  it("resolves shell_only to a zone-free diagnostic profile", () => {
    const diagnostics = resolveVoiceRenderDiagnostics("shell_only");
    assert.equal(diagnostics.showOrbZone, false);
    assert.equal(diagnostics.showOrb, false);
    assert.equal(diagnostics.showDialogs, false);
    assert.equal(diagnostics.metricsEnabled, false);
  });

  it("forces ready state for full_ready and orb_static_core", () => {
    assert.equal(resolveDiagnosticOrbState("thinking", resolveVoiceRenderDiagnostics("full_ready")), "ready");
    assert.equal(resolveDiagnosticOrbState("tts", resolveVoiceRenderDiagnostics("orb_static_core")), "ready");
  });

  it("reduces orb_static_core to the bare minimum visual path", () => {
    const config = applyOrbDiagnosticProfile(BASE_CONFIG, {
      mode: "orb_static_core",
      effectOverrides: {},
    });
    assert.equal(config.glow, false);
    assert.equal(config.coreTexture, false);
    assert.equal(config.particles, false);
    assert.equal(config.orb3D, false);
    assert.equal(config.orbMetricsBars, false);
    assert.equal(config.stateLabel, true);
  });

  it("keeps glow enabled only for orb_ready_glow while disabling 3D and metrics", () => {
    const config = applyOrbDiagnosticProfile(BASE_CONFIG, {
      mode: "orb_ready_glow",
      effectOverrides: {},
    });
    assert.equal(config.glow, true);
    assert.equal(config.frequencyRing, false);
    assert.equal(config.particles, false);
    assert.equal(config.orb3D, false);
    assert.equal(config.orbMetricsBars, false);
  });

  it("applies effect overrides on top of diagnostic profiles", () => {
    const config = applyOrbDiagnosticProfile(BASE_CONFIG, {
      mode: "orb_static_core",
      effectOverrides: {
        glow: true,
        stateLabel: false,
      },
    });
    assert.equal(config.glow, true);
    assert.equal(config.stateLabel, false);
    assert.equal(config.particles, false);
  });
});

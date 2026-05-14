import assert from "node:assert/strict";
import { afterEach, describe, it } from "node:test";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { Gemma4DaemonState } from "../hooks/use-gemma4-daemon";
import type { DaemonStatus } from "../lib/gemma4-daemon-api";
import { Gemma4RuntimeControlInner } from "../components/gemma4/gemma4-runtime-control";

afterEach(() => cleanup());

const noop = async () => { };

function makeStatus(overrides: Partial<DaemonStatus> = {}): DaemonStatus {
  return {
    target_model: "google/gemma-4-E2B-it",
    assistant_model: null,
    mode: "target_only",
    target_loaded: true,
    assistant_loaded: false,
    params: {
      max_new_tokens: 128,
      enable_thinking: false,
      image_token_budget: 280,
      reasoning_summary_enabled: false,
      emotion_detection_enabled: false,
      emotion_response_style_enabled: false,
      cache_implementation: null,
    },
    vram: {
      backend: "cpu",
      allocated_mb: 0,
      reserved_mb: 0,
      total_mb: 0,
      free_mb: 0,
    },
    raw_thinking_available: false,
    reasoning_summary_status: "disabled",
    reasoning_summary: null,
    emotion_label: null,
    emotion_confidence: null,
    emotion_source: null,
    pending_reload: false,
    reload_reason: null,
    supports_image_input: true,
    ...overrides,
  };
}

function makeState(overrides: Partial<Gemma4DaemonState> = {}): Gemma4DaemonState {
  return {
    status: makeStatus(),
    loading: false,
    error: null,
    actionPending: null,
    lastAppliedSignal: null,
    refresh: noop,
    applyConfig: async () => null,
    reload: noop,
    restart: noop,
    fallback: async () => null,
    attachAssistant: async () => { },
    detachAssistant: async () => { },
    ...overrides,
  };
}

function renderControl(
  state: Gemma4DaemonState,
  variant: "cockpit" | "voice" = "voice",
  runtimeSnapshot?: {
    provider?: string | null;
    model_name?: string | null;
    runtime_capabilities?: {
      compatibility_profile?: string | null;
      probe_status?: string | null;
    } | null;
    voice_pipeline?: {
      profile?: string | null;
      tts?: string | null;
    } | null;
  } | null,
  assistantModels: string[] = [],
) {
  return render(
    <Gemma4RuntimeControlInner
      daemon={state}
      variant={variant}
      runtimeSnapshot={runtimeSnapshot ?? null}
      assistantModels={assistantModels}
    />,
  );
}

describe("Gemma4RuntimeControl — loading state", () => {
  it("shows loading message when status is null and loading=true", () => {
    renderControl(makeState({ status: null, loading: true }));
    assert.ok(screen.queryByText(/daemon/i) !== null || screen.queryByText(/łącz/i) !== null);
  });
});

describe("Gemma4RuntimeControl — error state", () => {
  it("shows unavailable message when no status and error present", () => {
    renderControl(makeState({ status: null, loading: false, error: "connection refused" }));
    assert.ok(
      document.body.textContent?.toLowerCase().includes("niedostępny") ||
      document.body.textContent?.toLowerCase().includes("unavailable"),
    );
  });

  it("shows runtime snapshot details when daemon is unavailable", () => {
    renderControl(
      makeState({
        status: null,
        loading: false,
        error: "Failed to fetch",
      }),
      "voice",
      {
        provider: "ollama",
        model_name: "gemma2:2b",
        runtime_capabilities: {
          compatibility_profile: "gemma4_audio_native",
          probe_status: "verified",
        },
        voice_pipeline: {
          profile: "gemma4_audio_native",
          tts: "piper",
        },
      },
    );
    assert.ok(
      document.body.textContent?.toLowerCase().includes("failed to fetch"),
    );
    assert.ok(document.body.textContent?.includes("ollama / gemma2:2b"));
  });
});

describe("Gemma4RuntimeControl — normal state (voice variant)", () => {
  it("renders target model name", () => {
    renderControl(makeState());
    assert.ok(screen.getByText("google/gemma-4-E2B-it"));
  });

  it("renders Gemma 4 Runtime title", () => {
    renderControl(makeState());
    assert.ok(screen.getByText("Gemma 4 Runtime"));
  });

  it("renders Apply button", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("apply-button"));
  });

  it("renders Reload and Restart buttons", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("reload-button"));
    assert.ok(screen.getByTestId("restart-button"));
  });

  it("renders Fallback button", () => {
    renderControl(makeState());
    assert.ok(screen.getByTestId("fallback-button"));
  });

  it("shows CPU / no VRAM when backend=cpu", () => {
    renderControl(makeState());
    assert.ok(document.body.textContent?.includes("CPU"));
  });

  it("shows VRAM bar when backend=cuda", () => {
    renderControl(makeState({
      status: makeStatus({
        vram: {
          backend: "cuda",
          allocated_mb: 4096,
          reserved_mb: 5000,
          total_mb: 8192,
          free_mb: 4096,
        },
      }),
    }));
    const bar = screen.getByTestId("vram-bar");
    assert.ok(bar);
    assert.match(bar.style.width, /\d+%/);
  });
});

describe("Gemma4RuntimeControl — pending reload state", () => {
  it("shows reload banner when pending_reload=true", () => {
    renderControl(makeState({
      status: makeStatus({
        pending_reload: true,
        reload_reason: "cache_implementation changed",
      }),
    }));
    const banner = screen.getByTestId("reload-banner");
    assert.ok(banner);
    assert.ok(banner.textContent?.includes("cache_implementation"));
  });
});

describe("Gemma4RuntimeControl — assistant drafter on/off", () => {
  it("shows assistant model name when attached", () => {
    renderControl(makeState({
      status: makeStatus({
        assistant_model: "google/gemma-4-E2B-it-assistant",
        mode: "target_with_assistant",
        assistant_loaded: true,
      }),
    }));
    assert.ok(screen.getByText("google/gemma-4-E2B-it-assistant"));
  });

  it("shows drafter active badge when assistant attached", () => {
    renderControl(makeState({
      status: makeStatus({
        assistant_model: "google/gemma-4-E2B-it-assistant",
        mode: "target_with_assistant",
        assistant_loaded: true,
      }),
    }));
    assert.ok(
      document.body.textContent?.includes("drafter") ||
      document.body.textContent?.includes("aktywny"),
    );
  });

  it("shows no-drafter placeholder when no assistant", () => {
    renderControl(makeState({ status: makeStatus({ assistant_model: null }) }));
    assert.ok(
      document.body.textContent?.includes("Brak") ||
      document.body.textContent?.includes("None"),
    );
  });

  it("shows assistant preset selector when assistant models are available", () => {
    renderControl(
      makeState({ status: makeStatus({ assistant_model: null }) }),
      "voice",
      null,
      ["google/gemma-4-E2B-it-assistant"],
    );
    const attachButton = screen.queryByRole("button", { name: /drafter/i }) ?? screen.getByText(/drafter/i);
    fireEvent.click(attachButton);
    assert.ok(screen.getByText("google/gemma-4-E2B-it-assistant"));
  });
});

describe("Gemma4RuntimeControl — disabled state while action pending", () => {
  it("Apply button has disabled attribute when actionPending=config", () => {
    renderControl(makeState({ actionPending: "config" }));
    const btn = screen.getByTestId("apply-button") as HTMLButtonElement;
    assert.ok(btn.disabled);
  });

  it("Reload button has disabled attribute when actionPending=reload", () => {
    renderControl(makeState({ actionPending: "reload" }));
    const btn = screen.getByTestId("reload-button") as HTMLButtonElement;
    assert.ok(btn.disabled);
  });
});

describe("Gemma4RuntimeControl — cockpit variant", () => {
  it("renders without crashing in cockpit variant", () => {
    const { container } = renderControl(makeState(), "cockpit");
    assert.ok(container.firstChild);
  });

  it("cockpit variant renders target model", () => {
    renderControl(makeState(), "cockpit");
    assert.ok(screen.getByText("google/gemma-4-E2B-it"));
  });
});

describe("Gemma4RuntimeControl — thinking toggle", () => {
  it("reflects enable_thinking=true in switch state", () => {
    renderControl(makeState({
      status: makeStatus({
        params: {
          max_new_tokens: 128,
          enable_thinking: true,
          image_token_budget: 280,
          reasoning_summary_enabled: false,
          emotion_detection_enabled: false,
          emotion_response_style_enabled: false,
          cache_implementation: null,
        },
      }),
    }));
    const sw = document.querySelector("[role='switch']") as HTMLButtonElement | null;
    assert.ok(sw);
    assert.equal(sw.getAttribute("aria-checked"), "true");
  });
});

describe("Gemma4RuntimeControl — active model detection", () => {
  it("shows target model from status", () => {
    renderControl(makeState({
      status: makeStatus({ target_model: "google/gemma-4-E4B-it" }),
    }));
    assert.ok(screen.getByText("google/gemma-4-E4B-it"));
  });
});

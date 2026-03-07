import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  resolveCockpitActiveRuntimeInfo,
  resolveCockpitRuntimeModelSelection,
} from "../lib/cockpit-runtime-selection";

describe("cockpit runtime model selection", () => {
  it("restores the active model only when it belongs to the current runtime catalog", () => {
    assert.equal(
      resolveCockpitRuntimeModelSelection("gemma3:latest", ["gemma3:latest"]),
      "gemma3:latest",
    );
    assert.equal(
      resolveCockpitRuntimeModelSelection("phi3-mini", ["gemma3:latest"]),
      "",
    );
  });

  it("does not guess a new model when the current selection is empty", () => {
    assert.equal(
      resolveCockpitRuntimeModelSelection("", ["gemma3:latest"]),
      "",
    );
  });

  it("prefers active runtime and model from unified model catalog over fallback endpoint state", () => {
    const resolved = resolveCockpitActiveRuntimeInfo(
      {
        active: {
          runtime_id: "ollama",
          active_model: "gemma3:latest",
        },
        runtimes: [
          {
            runtime_id: "vllm",
            active: false,
            models: [{ name: "phi3:mini", active: true }],
          },
          {
            runtime_id: "ollama",
            active: true,
            source_type: "local-runtime",
            models: [{ name: "gemma3:latest", active: true }],
          },
        ],
      },
      {
        active_server: "vllm",
        active_model: "phi3:mini",
        runtime_id: "vllm",
        config_hash: "cfg-1",
      },
    );

    assert.deepEqual(resolved, {
      active_server: "ollama",
      active_model: "gemma3:latest",
      runtime_id: "ollama",
      source_type: "local-runtime",
      config_hash: "cfg-1",
    });
  });

  it("keeps fallback technical fields while refusing to carry foreign active model across runtimes", () => {
    const resolved = resolveCockpitActiveRuntimeInfo(
      {
        active: {
          runtime_id: "ollama",
        },
        runtimes: [
          {
            runtime_id: "ollama",
            active: true,
            models: [{ name: "gemma3:latest", active: false }],
          },
        ],
      },
      {
        active_server: "vllm",
        active_model: "phi3:mini",
        runtime_id: "vllm",
        last_models: { ollama: "gemma3:latest", vllm: "phi3:mini" },
      },
    );

    assert.deepEqual(resolved, {
      active_server: "ollama",
      active_model: null,
      runtime_id: "ollama",
      last_models: { ollama: "gemma3:latest", vllm: "phi3:mini" },
    });
  });
});

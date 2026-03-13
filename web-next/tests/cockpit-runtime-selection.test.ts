import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { performance } from "node:perf_hooks";

import {
  resolveCockpitActiveRuntimeInfo,
  resolveCockpitRuntimeModelSelection,
} from "../lib/cockpit-runtime-selection";

const runtimePerfIt =
  process.env.VENOM_ENABLE_WEB_RUNTIME_PERF_ASSERT === "1" ? it : it.skip;

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

  it("normalizes runtime_id with endpoint suffix from fallback to plain runtime id", () => {
    const resolved = resolveCockpitActiveRuntimeInfo(
      null,
      {
        active_server: "ollama",
        active_model: "gemma2:2b",
        runtime_id: "ollama@http://localhost:11434/v1",
      },
    );

    assert.deepEqual(resolved, {
      active_server: "ollama",
      active_model: "gemma2:2b",
      runtime_id: "ollama",
    });
  });

  runtimePerfIt("keeps runtime active resolution hot path within baseline tolerance", () => {
    const catalog = {
      active: {
        runtime_id: "ollama",
        active_model: "gemma3:latest",
      },
      runtimes: Array.from({ length: 24 }, (_value, index) => ({
        runtime_id: index === 12 ? "ollama" : `runtime-${index}`,
        active: index === 7,
        source_type: "local-runtime" as const,
        models: [
          { name: `model-${index}-a`, active: false },
          { name: `model-${index}-b`, active: index === 12 },
        ],
      })),
    };
    const fallback = {
      active_server: "vllm",
      active_model: "phi3:mini",
      runtime_id: "vllm",
      config_hash: "cfg-1",
    };

    const baselineResolve = (
      localCatalog: typeof catalog,
      localFallback: typeof fallback,
    ) => {
      const normalizeRuntimeId = (value: string | null | undefined): string => {
        const candidate = (value || "").trim();
        if (!candidate) {
          return "";
        }
        const atIndex = candidate.indexOf("@");
        if (atIndex <= 0) {
          return candidate.toLowerCase();
        }
        return candidate.slice(0, atIndex).trim().toLowerCase();
      };

      const catalogRuntimes = localCatalog?.runtimes ?? [];
      const declaredRuntimeId = normalizeRuntimeId(
        localCatalog?.active?.runtime_id || localCatalog?.active?.active_server,
      );
      const activeRuntime =
        catalogRuntimes.find(
          (runtime) => normalizeRuntimeId(runtime.runtime_id) === declaredRuntimeId,
        ) ??
        catalogRuntimes.find((runtime) => runtime.active) ??
        null;
      const activeRuntimeId =
        declaredRuntimeId ||
        normalizeRuntimeId(activeRuntime?.runtime_id || "") ||
        normalizeRuntimeId(
          localFallback?.active_server || localFallback?.runtime_id || "",
        );

      if (!activeRuntimeId) {
        return localFallback;
      }

      const runtimeModels = activeRuntime?.models ?? [];
      const declaredActiveModel = (localCatalog?.active?.active_model || "").trim();
      const runtimeActiveModel =
        runtimeModels.find((model) => model.active)?.name || "";
      const activeModelFromCatalog = declaredActiveModel || runtimeActiveModel.trim();
      const fallbackMatchesActiveRuntime =
        normalizeRuntimeId(
          localFallback?.active_server || localFallback?.runtime_id || "",
        ) === activeRuntimeId;
      let resolvedActiveModel: string | null = null;
      if (activeModelFromCatalog) {
        resolvedActiveModel = activeModelFromCatalog;
      } else if (fallbackMatchesActiveRuntime) {
        resolvedActiveModel = localFallback?.active_model || null;
      }

      return {
        ...localFallback,
        active_server: activeRuntimeId,
        runtime_id: activeRuntimeId,
        active_model: resolvedActiveModel,
        ...(activeRuntime?.source_type ?? localFallback?.source_type
          ? { source_type: activeRuntime?.source_type ?? localFallback?.source_type }
          : {}),
      };
    };

    const iterations = 15000;
    const measureBestOfRuns = (resolver: (localCatalog: typeof catalog, localFallback: typeof fallback) => unknown): number => {
      const runs: number[] = [];
      for (let runIndex = 0; runIndex < 5; runIndex += 1) {
        const startedAt = performance.now();
        for (let index = 0; index < iterations; index += 1) {
          resolver(catalog, fallback);
        }
        runs.push(performance.now() - startedAt);
      }
      return Math.min(...runs);
    };

    // Warm-up pass to reduce JIT/startup noise in CI runners.
    baselineResolve(catalog, fallback);
    resolveCockpitActiveRuntimeInfo(catalog, fallback);

    const baselineMs = measureBestOfRuns(baselineResolve);
    const optimizedMs = measureBestOfRuns(resolveCockpitActiveRuntimeInfo);

    assert.ok(
      optimizedMs <= baselineMs * 1.3,
      `optimized=${optimizedMs.toFixed(2)}ms baseline=${baselineMs.toFixed(2)}ms`,
    );
  });
});

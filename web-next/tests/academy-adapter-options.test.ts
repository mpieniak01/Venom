import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  buildCockpitAdapterOptions,
  isBlockedCockpitAdapterAudit,
} from "../lib/academy-adapter-options";

describe("academy-adapter-options", () => {
  it("keeps base option first and treats mismatch as informational", () => {
    const options = buildCockpitAdapterOptions({
      adapters: [
        {
          adapter_id: "adapter-ok",
          adapter_path: "/tmp/adapter-ok",
          base_model: "gemma-3-4b-it",
          is_active: false,
          compatible_runtimes: ["ollama"],
        },
        {
          adapter_id: "adapter-blocked",
          adapter_path: "/tmp/adapter-blocked",
          base_model: "unsloth/Phi-3-mini-4k-instruct",
          is_active: false,
          compatible_runtimes: ["ollama"],
        },
      ],
      auditById: {
        "adapter-ok": {
          adapter_id: "adapter-ok",
          adapter_path: "/tmp/adapter-ok",
          base_model: "gemma-3-4b-it",
          canonical_base_model: "gemma-3-4b-it",
          trusted_metadata: true,
          category: "compatible",
          reason_code: null,
          message: "Adapter metadata is consistent",
          is_active: false,
          sources: [],
          manual_repair_hint: null,
        },
        "adapter-blocked": {
          adapter_id: "adapter-blocked",
          adapter_path: "/tmp/adapter-blocked",
          base_model: "unsloth/Phi-3-mini-4k-instruct",
          canonical_base_model: "phi-3-mini-4k-instruct",
          trusted_metadata: true,
          category: "blocked_mismatch",
          reason_code: "ADAPTER_BASE_MODEL_MISMATCH",
          message: "Adapter base model does not match selected runtime model",
          is_active: false,
          sources: [],
          manual_repair_hint: "Switch model before activation",
        },
      },
      adapterDeploySupported: true,
      baseOptionValue: "__base__",
      baseOptionLabel: "Base model",
      compatibleLabel: "compatible",
      blockedLabel: "blocked",
      unknownStatusLabel: "unknown",
    });

    assert.equal(options[0]?.value, "__base__");
    assert.equal(options[1]?.disabled, false);
    assert.match(options[1]?.description ?? "", /compatible/);
    assert.equal(options[2]?.disabled, false);
    assert.match(options[2]?.description ?? "", /compatible/);
  });

  it("treats blocked categories as non-selectable", () => {
    assert.equal(
      isBlockedCockpitAdapterAudit({
        adapter_id: "adapter-blocked",
        adapter_path: "/tmp/adapter-blocked",
        base_model: "gemma-3-4b-it",
        canonical_base_model: "gemma-3-4b-it",
        trusted_metadata: true,
        category: "blocked_unknown_base",
        reason_code: "ADAPTER_BASE_MODEL_UNKNOWN",
        message: "Reliable base model metadata is missing",
        is_active: false,
        sources: [],
        manual_repair_hint: null,
      }),
      true,
    );
    assert.equal(
      isBlockedCockpitAdapterAudit({
        adapter_id: "adapter-mismatch",
        adapter_path: "/tmp/adapter-mismatch",
        base_model: "gemma-2-2b-it",
        canonical_base_model: "gemma-2-2b-it",
        trusted_metadata: true,
        category: "blocked_mismatch",
        reason_code: "ADAPTER_BASE_MODEL_MISMATCH",
        message: "Adapter base model does not match selected runtime model",
        is_active: false,
        sources: [],
        manual_repair_hint: null,
      }),
      false,
    );
    assert.equal(
      isBlockedCockpitAdapterAudit({
        adapter_id: "adapter-ok",
        adapter_path: "/tmp/adapter-ok",
        base_model: "gemma-3-4b-it",
        canonical_base_model: "gemma-3-4b-it",
        trusted_metadata: true,
        category: "compatible",
        reason_code: null,
        message: "Adapter metadata is consistent",
        is_active: false,
        sources: [],
        manual_repair_hint: null,
      }),
      false,
    );
  });
});
